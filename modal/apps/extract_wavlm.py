"""Computes streaming WavLM features for the MEAD train and validation clips.

Input:  /data/mead_v2/packed/<actor>.npz   (clip order and frame counts of the motion targets)
        /data/mead_v2/audio/<actor>/<emotion>/level_<l>/<nnn>.m4a   (MEAD audio; identical to
        the video's audio track, checked on M005: 0 ms offset, correlation 1.00)
Output: /data/mead_v2/wavlm/<actor>.npz    clip_ids, lengths, wavlm (float16, frames x 768),
        config (the extractor settings, so serving can reproduce them)

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


@app.function(image=image, gpu=["A10G", "L4", "T4"], volumes={C.DATA: C.data_vol}, timeout=3600, cpu=4,
              memory=16384, max_containers=6)
def actor_features(actor: str, layer: int = LAYER, future: int = FUTURE) -> dict:
    import os
    import subprocess
    import time

    import numpy as np
    import torch

    from emostream.audio.wavlm import WavLMFeatures

    assert actor not in TEST_ACTORS, "test actors are never processed"
    t0 = time.time()
    z = np.load(f"{C.DATA}/mead_v2/packed/{actor}.npz")
    x = WavLMFeatures(layer=layer, past_s=PAST_S, future_frames=future, device="cuda")
    audios, lengths, missing, short = [], [], [], 0
    for cid, n in zip(z["clip_ids"].tolist(), z["lengths"].tolist()):
        _, emo, lv, num = cid.split("_")
        path = f"{C.DATA}/mead_v2/audio/{actor}/{emo}/level_{lv[1:]}/{num}.m4a"
        lengths.append(int(n))
        if not os.path.exists(path):
            missing.append(cid)
            audios.append(np.zeros(0, np.float32))
            continue
        pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                             capture_output=True, check=True).stdout
        audio = np.frombuffer(pcm, "<i2").astype(np.float32) / 32768.0
        if len(audio) < n * 640:
            short += 1
        audios.append(audio)
    assert not missing, f"audio missing for {len(missing)} clips, e.g. {missing[:3]}"
    feats = [f.astype(np.float16) for f in x.frames_many(audios, lengths, batch=96)]
    os.makedirs(f"{C.DATA}/mead_v2/wavlm", exist_ok=True)
    np.savez(f"{C.DATA}/mead_v2/wavlm/{actor}.npz", clip_ids=z["clip_ids"], lengths=z["lengths"],
             wavlm=np.concatenate(feats, 0), config=json.dumps(x.config))
    C.data_vol.commit()
    return {"actor": actor, "clips": len(feats), "missing_audio": len(missing), "audio_shorter_than_video": short,
            "frames": int(z["lengths"].sum()), "minutes": round((time.time() - t0) / 60, 1),
            "gpu": torch.cuda.get_device_name(0)}


@app.local_entrypoint()
def main(actors: str = ""):
    if actors:
        todo = actors.split(",")
    else:
        packed = json.load(open(C.ROOT / "outputs" / "local" / "packed.json"))
        todo = packed["splits"]["train"]["actors"] + packed["splits"]["val"]["actors"]
    todo = [a for a in todo if a not in TEST_ACTORS]
    for r in actor_features.map(todo):
        print(json.dumps(r), flush=True)
