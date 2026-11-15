"""Turns validated MEAD clips into training features for the behaviour model.

For every valid clip in ``/data/mead_v2/manifests/clips.jsonl``:

  video  -> 25 FPS, one fixed face crop per clip (LivePortrait crop from the first
            frame), frozen LivePortrait motion extractor on every frame
            -> expression offsets (63), head pose in degrees (3), translation (3), scale
  audio  -> the track embedded in the video, 16 kHz mono
            -> Ditto's streaming HuBERT encoder (1024-d at 25 FPS, 85 ms look-ahead),
               i.e. exactly the features available at inference time

Output: ``/data/mead_v2/features/<actor>/<clip_id>.npz``. For val/test clips the
cropped 256 px ground-truth video is also kept for metric computation.
The raw MEAD volume is mounted read-only.

    modal run modal/apps/mead_preprocess.py --limit-actors M005 --limit-clips 6   # smoke test
    modal run modal/apps/mead_preprocess.py                                       # everything
"""
from __future__ import annotations

import json

import modal

import _common as C

app = modal.App("emostream-v2-mead-preprocess")
image = C.engine_image()
FEAT = f"{C.DATA}/mead_v2/features"
GT = f"{C.DATA}/mead_v2/gt256"


def _decode(path: str, height: int = 540):
    """25 FPS RGB frames (scaled to ``height``) and 16 kHz mono float audio."""
    import subprocess

    import numpy as np

    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height", "-of", "csv=p=0", path], capture_output=True, text=True)
    w0, h0 = [int(x) for x in probe.stdout.strip().split(",")[:2]]
    w = int(round(w0 * height / h0 / 2)) * 2
    v = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-r", "25", "-vf", f"scale={w}:{height}",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    if v.returncode != 0:
        raise RuntimeError(v.stderr.decode()[-300:])
    frames = np.frombuffer(v.stdout, dtype=np.uint8).reshape(-1, height, w, 3)
    a = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-f",
                        "s16le", "-"], capture_output=True)
    if a.returncode != 0:
        raise RuntimeError(a.stderr.decode()[-300:])
    audio = np.frombuffer(a.stdout, dtype="<i2").astype(np.float32) / 32768.0
    return frames, audio


@app.function(image=image, gpu=["T4", "L4", "A10G"], volumes={C.MODELS: C.models_vol, C.DATA: C.data_vol,
                                                              C.MEAD: C.mead_raw},
              timeout=4 * 3600, max_containers=22, cpu=4)
def process_actor(actor: str, limit_clips: int = 0) -> dict:
    import os
    import subprocess
    import time

    import cv2
    import imageio
    import numpy as np
    import torch

    from emostream.engine.runtime import Runtime

    os.chdir(C.REPO)
    rt = Runtime(C.ensure_checkpoints())
    s2i = rt.sdk.avatar_registrar.source2info
    mot = s2i.motion_extractor.model.eval()
    wav2feat = rt.sdk.wav2feat
    from core.atomic_components.motion_stitch import bin66_to_degree

    rows = [json.loads(line) for line in open(f"{C.DATA}/mead_v2/manifests/clips.jsonl")]
    rows = [r for r in rows if r["valid"] and r["actor"] == actor]
    if limit_clips:
        rows = rows[:: max(1, len(rows) // limit_clips)][:limit_clips]
    os.makedirs(f"{FEAT}/{actor}", exist_ok=True)
    keep_gt = rows and rows[0]["split"] in ("val", "test")
    if keep_gt:
        os.makedirs(f"{GT}/{actor}", exist_ok=True)

    done = skipped = 0
    failed = []
    t_start = time.perf_counter()
    for r in rows:
        out = f"{FEAT}/{actor}/{r['clip_id']}.npz"
        if os.path.exists(out):
            skipped += 1
            continue
        try:
            frames, audio = _decode(r["path"])
            crop0, M_c2o, _ = s2i._crop(frames[0])
            M_o2c = np.linalg.inv(M_c2o)[:2]
            crops = np.stack([cv2.resize(cv2.warpAffine(f, M_o2c, (512, 512), flags=cv2.INTER_LINEAR),
                                         (256, 256), interpolation=cv2.INTER_AREA) for f in frames])
            outs = {k: [] for k in ("pitch", "yaw", "roll", "t", "exp", "scale", "kp")}
            with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
                for i in range(0, len(crops), 64):
                    x = torch.from_numpy(crops[i:i + 64]).to("cuda").permute(0, 3, 1, 2).float() / 255.0
                    pred = mot(x)
                    for k, p in zip(outs, pred):
                        outs[k].append(p.float().cpu().numpy())
            o = {k: np.concatenate(v, 0) for k, v in outs.items()}
            n = len(crops)
            feat = wav2feat.wav2feat(audio, sr=16000)
            T = min(n, len(feat))
            if T < 20:
                raise RuntimeError(f"too short: {T} frames")
            pose = np.stack([bin66_to_degree(o[k]) for k in ("pitch", "yaw", "roll")], 1)
            np.savez(
                out,
                exp=o["exp"].reshape(n, -1)[:T].astype(np.float32),
                pose=pose[:T].astype(np.float32),
                t=o["t"].reshape(n, -1)[:T].astype(np.float32),
                scale=o["scale"].reshape(n)[:T].astype(np.float32),
                kp=o["kp"].reshape(n, -1)[:T].mean(0).astype(np.float32),
                hubert=feat[:T].astype(np.float16),
                n_video_frames=n, n_audio_frames=len(feat),
                emotion=r["emotion"], level=r["level"], actor=actor, split=r["split"],
            )
            if keep_gt:
                tmp = f"/tmp/{r['clip_id']}.mp4"
                w = imageio.get_writer(tmp, fps=25, codec="libx264", quality=8, macro_block_size=1)
                for c in crops[:T]:
                    w.append_data(c)
                w.close()
                wav = f"/tmp/{r['clip_id']}.wav"
                import soundfile as sf

                sf.write(wav, audio[: T * 640], 16000, subtype="PCM_16")
                subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", tmp, "-i", wav, "-c:v", "copy", "-c:a",
                                "aac", f"{GT}/{actor}/{r['clip_id']}.mp4"], check=True)
                os.remove(tmp)
                os.remove(wav)
            done += 1
            if done % 100 == 0:
                C.data_vol.commit()
        except Exception as e:  # noqa: BLE001
            failed.append({"clip_id": r["clip_id"], "error": repr(e)[:200]})
    C.data_vol.commit()
    return {"actor": actor, "clips": len(rows), "done": done, "skipped": skipped, "failed": failed[:10],
            "n_failed": len(failed), "seconds": round(time.perf_counter() - t_start, 1)}


PACK = f"{C.DATA}/mead_v2/packed"


@app.function(image=image, volumes={C.DATA: C.data_vol}, timeout=1800, cpu=4, memory=8192, max_containers=43)
def pack_actor(actor: str) -> dict:
    """Packs one actor's feature files into a single file (reading thousands of small
    files from a network volume is slow, so it is done once, one container per actor)."""
    import os
    from concurrent.futures import ThreadPoolExecutor

    import numpy as np

    rows = [json.loads(line) for line in open(f"{C.DATA}/mead_v2/manifests/clips.jsonl")]
    rows = [r for r in rows if r["valid"] and r["actor"] == actor
            and os.path.exists(f"{FEAT}/{actor}/{r['clip_id']}.npz")]

    def load(r):
        with np.load(f"{FEAT}/{actor}/{r['clip_id']}.npz") as z:
            return {k: z[k] for k in ("exp", "pose", "t", "scale", "hubert")}

    with ThreadPoolExecutor(8) as ex:
        data = list(ex.map(load, rows))
    lengths = np.array([len(d["exp"]) for d in data], dtype=np.int32)
    os.makedirs(PACK, exist_ok=True)
    np.savez(f"{PACK}/{actor}.npz", lengths=lengths, clip_ids=np.array([r["clip_id"] for r in rows]),
             emotions=np.array([r["emotion"] for r in rows]), levels=np.array([r["level"] for r in rows]),
             **{k: np.concatenate([d[k].reshape(len(d["exp"]), -1) for d in data], 0)
                for k in ("exp", "pose", "t", "scale", "hubert")})
    C.data_vol.commit()
    return {"actor": actor, "split": rows[0]["split"] if rows else None, "clips": len(rows),
            "frames": int(lengths.sum())}


@app.function(image=image, volumes={C.DATA: C.data_vol}, timeout=900, cpu=2)
def write_index(packed: list[dict]) -> dict:
    """Records which actor packs exist, per split."""
    import os

    C.data_vol.reload()
    split_of = {}
    for line in open(f"{C.DATA}/mead_v2/manifests/clips.jsonl"):
        r = json.loads(line)
        split_of[r["actor"]] = r["split"]
    out = {"actors": {}, "splits": {}}
    for p in packed:
        a = p["actor"]
        if not os.path.exists(f"{PACK}/{a}.npz"):
            continue
        out["actors"][a] = {"split": split_of[a], "clips": p["clips"], "frames": p["frames"],
                            "pack": f"{PACK}/{a}.npz"}
        s = out["splits"].setdefault(split_of[a], {"actors": [], "clips": 0, "hours": 0.0})
        s["actors"].append(a)
        s["clips"] += p["clips"]
        s["hours"] = round(s["hours"] + p["frames"] / 25 / 3600, 3)
    with open(f"{C.DATA}/mead_v2/manifests/packed.json", "w") as f:
        json.dump(out, f, indent=1)
    C.data_vol.commit()
    return out["splits"]


ALL_ACTORS = [
    "M003", "M005", "M007", "M009", "M011", "M012", "M013", "M019", "M022", "M023", "M024", "M025",
    "M027", "M028", "M029", "M030", "M031", "M033", "M034", "M035", "M037", "M039", "M040", "M041",
    "W009", "W011", "W014", "W015", "W016", "W018", "W019", "W023", "W024", "W025", "W026", "W028",
    "W029", "W033", "W035", "W036", "W037", "W038", "W040",
]


@app.local_entrypoint()
def main(limit_actors: str = "", limit_clips: int = 0, index_only: bool = False):
    if not index_only:
        actors = limit_actors.split(",") if limit_actors else ALL_ACTORS
        for res in process_actor.map(actors, kwargs={"limit_clips": limit_clips}, return_exceptions=True):
            print(res)
    if not limit_clips:
        actors = limit_actors.split(",") if limit_actors else ALL_ACTORS
        packed = [r for r in pack_actor.map(actors, return_exceptions=True) if isinstance(r, dict)]
        print(len(packed), "actors packed")
        print(json.dumps(write_index.remote(packed), indent=1))
