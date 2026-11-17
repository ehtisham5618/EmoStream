"""Computes streaming WavLM features for the MEAD train and validation clips.

Input:  /data/mead_v2/packed/<actor>.npz   (clip order and frame counts of the motion targets)
        /data/mead_v2/audio/<actor>/<emotion>/level_<l>/<nnn>.m4a   (MEAD audio; identical to
        the video's audio track, checked on M005: 0 ms offset, correlation 1.00)
        /data/mead_v2/manifests/audio_map.json   clip -> audio file, verified by content
        (evaluation/benchmarks/mead_audio_match.py: for some actors video and audio files are
        numbered differently, so "same number" can be a different sentence)
Output: /data/mead_v2/wavlm/<actor>.npz    clip_ids, lengths, wavlm (float16, frames x 768),
        valid (clip has verified audio), config (extractor settings, so serving can reproduce them)

Test actors are refused. The raw MEAD volume is not mounted.

    MODAL_PROFILE=abdulmat40 modal run modal/apps/extract_wavlm.py
"""
from __future__ import annotations

import json

import modal

import _common as C

TEST_ACTORS = {"M023", "M029", "M039", "W009", "W024", "W036"}
LAYER, PAST_S, FUTURE = 6, 1.0, 2

app = modal.App("emostream-v2-extract-wavlm")
image = C.engine_image(extra_pip=("transformers==4.46.3",))


def degrade(audio, seed: int):
    """A reproducible random 'real microphone' version of a clean studio clip: gain, noise,
    band limit (phone/laptop microphones, codecs) and room echo."""
    import numpy as np
    from scipy.signal import butter, fftconvolve, sosfilt

    rng = np.random.default_rng(seed)
    a = audio.astype(np.float64)
    if rng.random() < 0.5:                                    # band limit
        sos = butter(6, rng.uniform(3400, 7000), btype="low", fs=16000, output="sos")
        a = sosfilt(sos, a)
    if rng.random() < 0.3:                                    # room echo
        rt60 = rng.uniform(0.2, 0.6)
        n = int(rt60 * 16000)
        ir = rng.standard_normal(n) * np.exp(-6.9 * np.arange(n) / n)
        ir[0] = 1.0
        wet = fftconvolve(a, ir / np.abs(ir).sum() * 4)[: len(a)]
        mix = rng.uniform(0.2, 0.5)
        a = (1 - mix) * a + mix * wet
    speech = np.sqrt(np.mean(a ** 2)) + 1e-9
    snr = rng.uniform(15, 40)
    noise = rng.standard_normal(len(a))
    if rng.random() < 0.5:                                    # pink-ish noise
        noise = np.cumsum(noise)
        noise -= np.convolve(noise, np.ones(400) / 400, mode="same")
    noise *= speech / (np.sqrt(np.mean(noise ** 2)) + 1e-9) / 10 ** (snr / 20)
    a = (a + noise) * 10 ** (rng.uniform(-18, 6) / 20)
    return np.clip(a, -1, 1).astype(np.float32)


@app.function(image=image, gpu=["A10G", "L4", "T4"], volumes={C.DATA: C.data_vol}, timeout=3600, cpu=4,
              memory=16384, max_containers=10)
def actor_features(actor: str, layer: int = LAYER, future: int = FUTURE, augment: bool = False) -> dict:
    import os
    import subprocess
    import time

    import numpy as np
    import torch

    from emostream.audio.wavlm import WavLMFeatures

    assert actor not in TEST_ACTORS, "test actors are never processed"
    t0 = time.time()
    z = np.load(f"{C.DATA}/mead_v2/packed/{actor}.npz")
    amap = json.load(open(f"{C.DATA}/mead_v2/manifests/audio_map.json"))["mapping"].get(actor, {})
    x = WavLMFeatures(layer=layer, past_s=PAST_S, future_frames=future, device="cuda")
    audios, lengths, missing, short = [], [], [], 0
    for cid, n in zip(z["clip_ids"].tolist(), z["lengths"].tolist()):
        lengths.append(int(n))
        rel = amap.get(cid)
        path = f"{C.DATA}/mead_v2/audio/{actor}/{rel}" if rel else ""
        if not rel or not os.path.exists(path):
            missing.append(cid)
            audios.append(np.zeros(0, np.float32))
            continue
        pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                             capture_output=True, check=True).stdout
        audio = np.frombuffer(pcm, "<i2").astype(np.float32) / 32768.0
        if len(audio) < n * 640:
            short += 1
        if augment:
            import zlib

            audio = degrade(audio, zlib.crc32(cid.encode()))
        audios.append(audio)
    keep = [i for i, a in enumerate(audios) if len(a)]
    got = x.frames_many([audios[i] for i in keep], [lengths[i] for i in keep], batch=96)
    feats = [np.zeros((n, x.dim), np.float16) for n in lengths]
    for i, f in zip(keep, got):
        feats[i] = f.astype(np.float16)
    valid = np.array([bool(len(a)) for a in audios])
    sub = "wavlm_aug" if augment else "wavlm"
    os.makedirs(f"{C.DATA}/mead_v2/{sub}", exist_ok=True)
    np.savez(f"{C.DATA}/mead_v2/{sub}/{actor}.npz", clip_ids=z["clip_ids"], lengths=z["lengths"],
             wavlm=np.concatenate(feats, 0), valid=valid, config=json.dumps(x.config))
    C.data_vol.commit()
    return {"actor": actor, "clips": len(feats), "valid": int(valid.sum()), "unpaired": len(missing), "audio_shorter_than_video": short,
            "frames": int(z["lengths"].sum()), "minutes": round((time.time() - t0) / 60, 1),
            "gpu": torch.cuda.get_device_name(0)}


@app.local_entrypoint()
def main(actors: str = "", augment: bool = False):
    if actors:
        todo = actors.split(",")
    else:
        packed = json.load(open(C.ROOT / "outputs" / "local" / "packed.json"))
        todo = packed["splits"]["train"]["actors"] + packed["splits"]["val"]["actors"]
    todo = [a for a in todo if a not in TEST_ACTORS]
    # One call per actor, collected one by one: ``.map`` iteration ended early with a
    # client-side StopAsyncIteration under Python 3.14, abandoning actors still queued.
    calls = [(a, actor_features.spawn(a, augment=augment)) for a in todo]
    for a, call in calls:
        try:
            print(json.dumps(call.get()), flush=True)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"actor": a, "error": f"{type(e).__name__}: {e}"}), flush=True)
