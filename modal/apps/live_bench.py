"""Real-time benchmark of the full engine with audio fed at microphone pace.

Reports frames per second, audio-to-frame latency (p50 / p95), per-stage time and
peak GPU memory, for either behaviour model and either renderer back end.

    modal run modal/apps/live_bench.py --behaviour emostream --run base --tensorrt --gpu A10G
    modal run modal/apps/live_bench.py --behaviour emostream --run base --gpu T4
    modal run modal/apps/live_bench.py --behaviour ditto --tensorrt --gpu A10G
    modal run modal/apps/live_bench.py --seconds 300 --tensorrt     # five-minute stability run
"""
from __future__ import annotations

import json

import modal

import _common as C

app = modal.App("emostream-v2-live-bench")
VOLS = {C.MODELS: C.models_vol, C.DATA: C.data_vol}


def _run(tensorrt: bool, behaviour: str, run: str, portrait: str, audio: str, seconds: float, size: int,
         chunk_ms: int, emotion: str, intensity: float, schedule: str, max_latency_ms: float, tag: str,
         save_video: bool, emotion_gain: float = 1.0, close_mouth: bool = True, hop: int = 5,
         lip_target: float = -1.0, lip_strength: float = 1.0) -> dict:
    import os
    import subprocess
    import time

    import imageio
    import librosa
    import numpy as np
    import torch

    import _bench
    from emostream.engine.behaviour import DittoBehaviour
    from emostream.engine.runtime import Runtime
    from emostream.engine.session import AvatarSession, stream_file

    os.chdir(C.REPO)
    meter = _bench.SmiMeter()
    t0 = time.perf_counter()
    rt = Runtime(C.ensure_checkpoints(tensorrt=tensorrt), tensorrt=tensorrt)
    load_s = time.perf_counter() - t0
    net = None
    if behaviour == "emostream":
        from emostream.models import BehaviourNet

        net = BehaviourNet.load(torch.load(f"{C.MODELS}/emostream/{run}/model.pt", map_location="cpu",
                                           weights_only=False))

    def factory(runtime, av, timeline):
        if behaviour == "emostream":
            from emostream.engine.behaviour_emostream import EmoStreamBehaviour

            return EmoStreamBehaviour(runtime, av, timeline, net, emotion_gain=emotion_gain, hop=hop)
        return DittoBehaviour(runtime, av, timeline, sampling_timesteps=10, valid_frames=10)

    wav, _ = librosa.load(f"{C.DATA}/{audio}", sr=16000, mono=True)
    if seconds > 0:  # loop the recording to the requested length
        wav = np.tile(wav, int(np.ceil(seconds * 16000 / len(wav))))[: int(seconds * 16000)]
    t0 = time.perf_counter()
    avatar = rt.register(f"{C.DATA}/{portrait}", close_open_mouth=close_mouth,
                         lip_target=None if lip_target < 0 else lip_target,
                         lip_strength=lip_strength)
    register_s = time.perf_counter() - t0

    def new_session(limit):
        s = AvatarSession(rt, avatar, factory, emotion=emotion, intensity=intensity, size=size,
                          portrait_consent=True, audio_consent=True,
                          max_latency_ms=limit if limit > 0 else None)
        for item in filter(None, (x.strip() for x in schedule.split(","))):
            t, emo, inten = item.split(":")
            s.set_emotion(emo, float(inten), at_seconds=float(t))
        return s

    for _ in stream_file(new_session(0), wav[:32000], chunk_ms=chunk_ms, paced=False):  # warm-up
        pass
    torch.cuda.reset_peak_memory_stats()

    out_dir = f"{C.DATA}/bench/{tag}"
    os.makedirs(out_dir, exist_ok=True)
    writer = None
    if save_video:
        writer = imageio.get_writer(f"/tmp/{tag}.mp4", fps=25, codec="libx264", quality=7, macro_block_size=1)
    session = new_session(max_latency_ms)
    per_minute, last = [], None
    t0 = time.perf_counter()
    for fr in stream_file(session, wav, chunk_ms=chunk_ms, paced=True):
        if fr.rgb is not None:
            last = fr.rgb
            m = int(fr.time_s // 60)
            while len(per_minute) <= m:
                per_minute.append([])
            per_minute[m].append(fr.latency_ms)
        if writer is not None and last is not None:
            writer.append_data(last)  # a skipped frame repeats the previous image, as a viewer sees it
    wall = time.perf_counter() - t0
    if writer is not None:
        writer.close()
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", f"/tmp/{tag}.mp4", "-i", f"{C.DATA}/{audio}",
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest",
                        f"{out_dir}/out.mp4"], check=False)
    st = session.stats(skip_frames=25)   # drop the first second (stream start-up)
    lo, hi = session.behaviour.algorithmic_delay_frames
    res = {
        "tag": tag, "gpu": meter.name, "renderer": "tensorrt_fp16" if tensorrt else "pytorch_fp16",
        "behaviour": behaviour, "run": run if behaviour == "emostream" else None, "portrait": portrait,
        "audio": audio, "size": size, "chunk_ms": chunk_ms, "paced": True, "max_latency_ms": max_latency_ms,
        "portrait_lip_open_ratio": round(float(avatar.lip_ratio), 4), "portrait_mouth_open": bool(avatar.mouth_open),
        "mouth_closed_automatically": avatar.lip_delta is not None, "emotion_gain": emotion_gain, "hop": hop,
        "model_load_s": round(load_s, 2), "portrait_register_s": round(register_s, 2), "wall_s": round(wall, 2),
        "delivered_fps": round(st["frames_rendered"] / wall, 2), "algorithmic_delay_ms": [lo * 40, hi * 40],
        "device_peak_used_gib": meter.stop(),
        "latency_p50_by_minute_ms": [round(float(np.median(x)), 1) for x in per_minute if x],
        "frames_rendered_by_minute": [len(x) for x in per_minute if x],
        **st,
    }
    with open(f"{out_dir}/stats.json", "w") as f:
        json.dump(res, f, indent=1)
    C.data_vol.commit()
    return res


@app.function(image=C.engine_image(extra_pip=("transformers==4.46.3",), env={"HF_HOME": f"{C.MODELS}/hf"}),
              gpu="A10G", volumes=VOLS, timeout=1800)
def bench_pytorch(**kw) -> dict:
    return _run(False, **kw)


@app.function(image=C.engine_image(extra_pip=("transformers==4.46.3",), tensorrt=True,
                                   env={"HF_HOME": f"{C.MODELS}/hf"}), gpu="A10G", volumes=VOLS, timeout=1800)
def bench_tensorrt(**kw) -> dict:
    return _run(True, **kw)


@app.local_entrypoint()
def main(behaviour: str = "emostream", run: str = "base", tensorrt: bool = False, gpu: str = "A10G",
         portrait: str = "eval/val/M005/portrait.png", audio: str = "poc/inputs/audio.wav", seconds: float = 0,
         size: int = 512, chunk_ms: int = 200, emotion: str = "neutral", intensity: float = 1.0,
         schedule: str = "", max_latency_ms: float = 0, tag: str = "", save_video: bool = True,
         emotion_gain: float = 1.0, close_mouth: bool = True, hop: int = 5, lip_target: float = -1.0,
         lip_strength: float = 1.0):
    tag = tag or f"live_{behaviour}_{'trt' if tensorrt else 'pt'}_{gpu}"
    fn = (bench_tensorrt if tensorrt else bench_pytorch).with_options(gpu=gpu)
    res = fn.remote(behaviour=behaviour, run=run, portrait=portrait, audio=audio, seconds=seconds, size=size,
                    chunk_ms=chunk_ms, emotion=emotion, intensity=intensity, schedule=schedule,
                    max_latency_ms=max_latency_ms, tag=tag, save_video=save_video, emotion_gain=emotion_gain,
                    close_mouth=close_mouth, hop=hop, lip_target=lip_target, lip_strength=lip_strength)
    print(json.dumps(res, indent=1))
