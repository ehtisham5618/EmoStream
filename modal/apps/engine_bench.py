"""Runs the EmoStream streaming engine on a Modal GPU and records speed, latency and memory.

    # real-face inputs from MEAD validation actors (CPU, run once)
    modal run modal/apps/engine_bench.py::prepare

    # paced like a live microphone, 200 ms chunks, 512 px crop output
    modal run modal/apps/engine_bench.py --portrait eval/val/M005/portrait.png \
        --audio eval/val/M005/neutral.wav --tag m005_neutral

    # emotion schedule: "seconds:emotion:intensity,..."
    modal run modal/apps/engine_bench.py --schedule "0:neutral:1,2:happy:1,4:angry:1" --tag switch
"""
from __future__ import annotations

import json
from pathlib import Path

import modal

DITTO_COMMIT = "c3e47ee"
MODELS = "/models"
DATA = "/data"
REPO = "/opt/ditto"
# In the container this file is /root/engine_bench.py; the repo root only exists locally.
ROOT = Path(__file__).resolve().parents[2] if modal.is_local() else Path("/root")

app = modal.App("emostream-v2-engine-bench")
models_vol = modal.Volume.from_name("emostream-v2-models", create_if_missing=True)
data_vol = modal.Volume.from_name("emostream-v2-data", create_if_missing=True)

_NV = "/usr/local/lib/python3.10/site-packages/nvidia"
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "git", "build-essential", "libgl1", "libglib2.0-0")
    .pip_install("torch==2.5.1", "torchvision==0.20.1", "torchaudio==2.5.1",
                 index_url="https://download.pytorch.org/whl/cu121")
    .pip_install(
        "numpy==1.26.4", "onnxruntime-gpu==1.20.2", "mediapipe==0.10.14", "librosa==0.10.2.post1", "tqdm",
        "filetype", "imageio==2.36.1", "imageio-ffmpeg==0.5.1", "opencv-python-headless==4.10.0.84",
        "scikit-image", "cython==3.0.11", "colored", "einops", "scipy", "huggingface_hub", "soundfile",
    )
    .run_commands(f"git clone https://github.com/antgroup/ditto-talkinghead {REPO}",
                  f"cd {REPO} && git checkout {DITTO_COMMIT}")
    .env({
        "LD_LIBRARY_PATH": ":".join(f"{_NV}/{d}/lib" for d in (
            "cudnn", "cublas", "cuda_runtime", "cufft", "curand", "cuda_nvrtc", "nvjitlink", "cusparse", "cusolver")),
        "DITTO_REPO": REPO, "PYTHONPATH": "/root",
    })
    .add_local_file(str(ROOT / "modal" / "apps" / "_bench.py"), "/root/_bench.py")
    .add_local_dir(str(ROOT / "emostream"), "/root/emostream")
)
cpu_image = modal.Image.debian_slim(python_version="3.11").apt_install("ffmpeg")


def ensure_checkpoints() -> str:
    import os

    from huggingface_hub import snapshot_download

    dst = f"{MODELS}/ditto"
    if not os.path.exists(f"{dst}/ditto_pytorch/models/lmdm_v0.4_hubert.pth"):
        snapshot_download("digital-avatar/ditto-talkinghead", local_dir=dst,
                          allow_patterns=["ditto_cfg/*", "ditto_pytorch/**"])
        models_vol.commit()
    return dst


@app.function(image=cpu_image, volumes={DATA: data_vol,
                                        "/mead": modal.Volume.from_name("emostream-mead-raw").read_only()},
              timeout=1800, cpu=4)
def prepare_eval_inputs(split: str = "val", level: int = 3) -> dict:
    """For each actor of a split: a neutral still frame as the portrait, and one clip
    per emotion (16 kHz mono wav + the 25 FPS ground-truth video)."""
    import os
    import subprocess

    rows = [json.loads(line) for line in open(f"{DATA}/mead_v2/manifests/clips.jsonl")]
    rows = [r for r in rows if r["valid"] and r["split"] == split]
    out = {}
    for actor in sorted({r["actor"] for r in rows}):
        d = f"{DATA}/eval/{split}/{actor}"
        os.makedirs(d, exist_ok=True)
        mine = [r for r in rows if r["actor"] == actor]
        neutral = sorted([r for r in mine if r["emotion"] == "neutral"], key=lambda r: r["clip"])
        # portrait: first frame of the first neutral clip (mouth closed, neutral face)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", neutral[0]["path"], "-frames:v", "1",
                        f"{d}/portrait.png"], check=True)
        picks = {"neutral": neutral[5]}  # a different clip than the portrait source
        for emo in ("happy", "sad", "angry", "surprised"):
            c = sorted([r for r in mine if r["emotion"] == emo and r["level"] == level], key=lambda r: r["clip"])
            picks[emo] = c[2]
        for emo, r in picks.items():
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", r["path"], "-vn", "-ac", "1", "-ar",
                            "16000", "-c:a", "pcm_s16le", f"{d}/{emo}.wav"], check=True)
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", r["path"], "-r", "25", "-vf",
                            "scale=-2:540", "-c:v", "libx264", "-crf", "18", "-c:a", "aac", f"{d}/{emo}_gt.mp4"],
                           check=True)
        out[actor] = {e: r["clip_id"] for e, r in picks.items()}
        out[actor]["portrait_from"] = neutral[0]["clip_id"]
    with open(f"{DATA}/eval/{split}/inputs.json", "w") as f:
        json.dump(out, f, indent=1)
    data_vol.commit()
    return out


def _parse_schedule(schedule: str):
    out = []
    for item in filter(None, (s.strip() for s in schedule.split(","))):
        t, emo, inten = item.split(":")
        out.append((float(t), emo, float(inten)))
    return out


@app.function(image=image, gpu=["L4", "A10G", "T4"], volumes={MODELS: models_vol, DATA: data_vol}, timeout=1800)
def bench(portrait: str = "poc/inputs/portrait.png", audio: str = "poc/inputs/audio.wav", tag: str = "run",
          emotion: str = "neutral", intensity: float = 1.0, schedule: str = "", steps: int = 10,
          valid_frames: int = 10, chunk_ms: int = 200, paced: bool = True, size: int = 512,
          full_frame: bool = False, save_video: bool = True, warmup: bool = True,
          behaviour: str = "ditto", run: str = "base", exp_gain: float = 1.0, pose_gain: float = 1.0) -> dict:
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

    os.chdir(REPO)
    ckpt = ensure_checkpoints()
    meter = _bench.SmiMeter()
    t0 = time.perf_counter()
    rt = Runtime(ckpt)
    load_s = time.perf_counter() - t0

    wav, _ = librosa.load(f"{DATA}/{audio}", sr=16000, mono=True)
    t0 = time.perf_counter()
    avatar = rt.register(f"{DATA}/{portrait}")
    register_s = time.perf_counter() - t0

    net = None
    if behaviour == "emostream":
        from emostream.models import BehaviourNet

        models_vol.reload()
        net = BehaviourNet.load(torch.load(f"{MODELS}/emostream/{run}/model.pt", map_location="cpu",
                                           weights_only=False))

    def factory(runtime, av, timeline):
        if behaviour == "emostream":
            from emostream.engine.behaviour_emostream import EmoStreamBehaviour

            return EmoStreamBehaviour(runtime, av, timeline, net, exp_gain=exp_gain, pose_gain=pose_gain)
        if behaviour == "ditto_full":
            from emostream.engine.behaviour_emostream import DittoFullFace

            return DittoFullFace(runtime, av, timeline, sampling_timesteps=steps, valid_frames=valid_frames)
        return DittoBehaviour(runtime, av, timeline, sampling_timesteps=steps, valid_frames=valid_frames)

    def new_session():
        s = AvatarSession(rt, avatar, factory, emotion=emotion, intensity=intensity, size=size,
                          full_frame=full_frame, portrait_consent=True, audio_consent=True)
        for t, emo, inten in _parse_schedule(schedule):
            s.set_emotion(emo, inten, at_seconds=t)
        return s

    if warmup:  # one second of audio, unpaced: cuDNN autotune, lazy allocations
        for _ in stream_file(new_session(), wav[:16000], chunk_ms=chunk_ms, paced=False):
            pass
    torch.cuda.reset_peak_memory_stats()

    out_dir = f"{DATA}/bench/{tag}"
    os.makedirs(out_dir, exist_ok=True)
    tmp = f"/tmp/{tag}.mp4"
    writer = imageio.get_writer(tmp, fps=25, codec="libx264", quality=8, macro_block_size=1) if save_video else None
    session = new_session()
    t0 = time.perf_counter()
    n = 0
    for fr in stream_file(session, wav, chunk_ms=chunk_ms, paced=paced):
        if writer is not None:
            writer.append_data(fr.rgb)
        n += 1
    wall = time.perf_counter() - t0
    if writer is not None:
        writer.close()
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", tmp, "-i", f"{DATA}/{audio}", "-map", "0:v",
                        "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", f"{out_dir}/out.mp4"], check=True)
    stats = session.stats(skip_frames=0)
    lo, hi = session.behaviour.algorithmic_delay_frames
    res = {
        "tag": tag, "gpu": meter.name, "portrait": portrait, "audio": audio, "paced": paced, "chunk_ms": chunk_ms,
        "size": size, "full_frame": full_frame, "behaviour": behaviour, "run": run if behaviour == "emostream" else None,
        "exp_gain": exp_gain, "pose_gain": pose_gain, "sampling_timesteps": steps,
        "valid_frames": valid_frames, "emotion": emotion, "intensity": intensity, "schedule": schedule,
        "model_load_s": round(load_s, 2), "portrait_register_s": round(register_s, 2), "wall_s": round(wall, 2),
        "algorithmic_delay_ms": [lo * 40, hi * 40],
        "device_peak_used_gib": meter.stop(), **stats,
        "note": "latency = arrival of a frame's last audio sample -> rendered frame available; includes video "
                "encoding time inside the loop when save_video is set.",
    }
    with open(f"{out_dir}/stats.json", "w") as f:
        json.dump(res, f, indent=1)
    data_vol.commit()
    return res


@app.local_entrypoint()
def main(portrait: str = "poc/inputs/portrait.png", audio: str = "poc/inputs/audio.wav", tag: str = "run",
         emotion: str = "neutral", intensity: float = 1.0, schedule: str = "", steps: int = 10,
         valid_frames: int = 10, chunk_ms: int = 200, paced: bool = True, size: int = 512,
         full_frame: bool = False, gpu: str = "", behaviour: str = "ditto", run: str = "base",
         exp_gain: float = 1.0, pose_gain: float = 1.0):
    fn = bench.with_options(gpu=gpu) if gpu else bench
    res = fn.remote(portrait=portrait, audio=audio, tag=tag, emotion=emotion, intensity=intensity,
                       schedule=schedule, steps=steps, valid_frames=valid_frames, chunk_ms=chunk_ms, paced=paced,
                    size=size, full_frame=full_frame, behaviour=behaviour, run=run, exp_gain=exp_gain,
                    pose_gain=pose_gain)
    print(json.dumps(res, indent=1))


@app.local_entrypoint()
def prepare(split: str = "val"):
    print(json.dumps(prepare_eval_inputs.remote(split), indent=1))
