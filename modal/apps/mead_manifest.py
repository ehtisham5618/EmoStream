"""Builds a validated manifest of the MEAD clips EmoStream uses, with actor-disjoint splits.

Sources (both read-only):
  * ``/mead/extracted/<actor>/video/front/<emotion>/level_1/*.mp4``  (already extracted)
  * ``/mead/archives/<actor>/video.tar``  for front-view level_2 / level_3 clips, which
    were never extracted. Those clips are copied out of the tar into the *new* volume
    (``/data/mead_v2/raw_l23/...``); the original volume is not modified.

Every clip is ffprobed. A clip is valid when it has exactly one video and at least one
audio stream, decodes its header, is between 1 s and 20 s long, and its embedded audio
and video durations differ by less than 0.5 s. The audio used downstream is the track
embedded in the video file (the separate ``audio/`` folder is incomplete and has
mismatched durations; see docs/experiments/mead_validation.md).

    modal run modal/apps/mead_manifest.py                 # extract l2/l3 + build manifest
    modal run modal/apps/mead_manifest.py --skip-extract  # manifest from what exists
"""
from __future__ import annotations

import json

import modal

app = modal.App("emostream-v2-mead-manifest")
raw = modal.Volume.from_name("emostream-mead-raw").read_only()
out = modal.Volume.from_name("emostream-v2-data", create_if_missing=True)
image = modal.Image.debian_slim(python_version="3.11").apt_install("ffmpeg")

RAW = "/mead"
OUT = "/data"
EMOTIONS = ["neutral", "happy", "sad", "angry", "surprised"]
L23 = f"{OUT}/mead_v2/raw_l23"

# Actor-disjoint split, fixed once and never tuned on results.
# Chosen by a seeded shuffle within gender (seed 20261114); see _make_split().
SPLIT_SEED = 20261114
N_TEST = (3, 3)  # (men, women)
N_VAL = (2, 2)


def _make_split(actors: list[str]) -> dict[str, str]:
    import random

    rng = random.Random(SPLIT_SEED)
    men = sorted(a for a in actors if a.startswith("M"))
    women = sorted(a for a in actors if a.startswith("W"))
    rng.shuffle(men)
    rng.shuffle(women)
    split = {}
    for group, n_test, n_val in ((men, N_TEST[0], N_VAL[0]), (women, N_TEST[1], N_VAL[1])):
        for i, a in enumerate(group):
            split[a] = "test" if i < n_test else "val" if i < n_test + n_val else "train"
    return split


@app.function(image=image, volumes={RAW: raw, OUT: out}, timeout=7200, cpu=2, max_containers=24)
def extract_l23(actor: str) -> dict:
    """Copies front-view level_2/level_3 clips of the five target emotions out of the tar."""
    import os
    import tarfile

    done = f"{L23}/{actor}/.done"
    if os.path.exists(done):
        return {"actor": actor, "skipped": True}
    tar_path = f"{RAW}/archives/{actor}/video.tar"
    n = 0
    with tarfile.open(tar_path) as tf:
        for m in tf:
            if not m.isfile() or not m.name.endswith(".mp4"):
                continue
            parts = m.name.strip("./").split("/")
            if len(parts) < 4:
                continue
            view, emo, level, fn = parts[-4:]
            if view != "front" or emo not in EMOTIONS or level not in ("level_2", "level_3"):
                continue
            dst = f"{L23}/{actor}/front/{emo}/{level}/{fn}"
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            src = tf.extractfile(m)
            with open(dst, "wb") as f:
                while True:
                    buf = src.read(1 << 20)
                    if not buf:
                        break
                    f.write(buf)
            n += 1
    open(done, "w").write(str(n))
    out.commit()
    return {"actor": actor, "extracted": n}


def _probe(path: str) -> dict:
    import subprocess

    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_entries",
         "stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,sample_rate,channels,duration,nb_frames"
         ":format=duration,size", path],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        return {"error": r.stderr.strip()[:200] or "ffprobe failed"}
    try:
        return json.loads(r.stdout)
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)[:200]}


@app.function(image=image, volumes={RAW: raw, OUT: out}, timeout=7200, cpu=8)
def build_manifest() -> dict:
    import os
    from collections import Counter, defaultdict
    from concurrent.futures import ThreadPoolExecutor

    out.reload()
    actors = sorted(os.listdir(f"{RAW}/extracted"))
    split = _make_split(actors)
    todo = []
    for a in actors:
        for emo in EMOTIONS:
            for level, base in (("level_1", f"{RAW}/extracted/{a}/video/front"),
                                ("level_2", f"{L23}/{a}/front"), ("level_3", f"{L23}/{a}/front")):
                d = f"{base}/{emo}/{level}"
                if not os.path.isdir(d):
                    continue
                for fn in sorted(os.listdir(d)):
                    if fn.endswith(".mp4"):
                        todo.append((a, emo, int(level[-1]), fn[:-4], f"{d}/{fn}"))

    def one(t):
        a, emo, level, clip, path = t
        p = _probe(path)
        row = {"clip_id": f"{a}_{emo}_L{level}_{clip}", "actor": a, "gender": a[0], "emotion": emo,
               "level": level, "clip": clip, "split": split[a], "path": path, "valid": False, "reason": ""}
        if "error" in p:
            row["reason"] = "probe_error: " + p["error"]
            return row
        vs = [s for s in p.get("streams", []) if s.get("codec_type") == "video"]
        aus = [s for s in p.get("streams", []) if s.get("codec_type") == "audio"]
        if len(vs) != 1:
            row["reason"] = f"video_streams={len(vs)}"
            return row
        if not aus:
            row["reason"] = "no_audio_stream"
            return row
        v, au = vs[0], aus[0]
        num, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1").split("/")
        fps = float(num) / float(den) if float(den) else 0.0
        dur = float(p["format"].get("duration", 0) or 0)
        vdur = float(v.get("duration", dur) or dur)
        adur = float(au.get("duration", dur) or dur)
        row.update({"width": v.get("width"), "height": v.get("height"), "fps": round(fps, 3),
                    "duration_s": round(dur, 3), "video_s": round(vdur, 3), "audio_s": round(adur, 3),
                    "audio_sr": int(au.get("sample_rate", 0) or 0), "vcodec": v.get("codec_name"),
                    "bytes": int(p["format"].get("size", 0) or 0)})
        if not (1.0 <= dur <= 20.0):
            row["reason"] = f"duration={dur:.2f}"
        elif abs(vdur - adur) > 0.5:
            row["reason"] = f"av_duration_gap={vdur - adur:.2f}"
        elif fps < 20 or fps > 61:
            row["reason"] = f"fps={fps:.2f}"
        else:
            row["valid"] = True
        return row

    with ThreadPoolExecutor(32) as ex:
        rows = list(ex.map(one, todo))

    os.makedirs(f"{OUT}/mead_v2/manifests", exist_ok=True)
    with open(f"{OUT}/mead_v2/manifests/clips.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    valid = [r for r in rows if r["valid"]]
    by_split = defaultdict(lambda: {"actors": set(), "clips": 0, "hours": 0.0, "emotion_level": Counter()})
    for r in valid:
        s = by_split[r["split"]]
        s["actors"].add(r["actor"])
        s["clips"] += 1
        s["hours"] += r["duration_s"] / 3600
        s["emotion_level"][f"{r['emotion']}/L{r['level']}"] += 1
    reasons = Counter(r["reason"].split("=")[0].split(":")[0] for r in rows if not r["valid"])
    summary = {
        "n_clips_found": len(rows), "n_valid": len(valid), "invalid_reasons": dict(reasons),
        "split_seed": SPLIT_SEED,
        "split_actors": {k: sorted(a for a, s in split.items() if s == k) for k in ("train", "val", "test")},
        "splits": {k: {"n_actors": len(v["actors"]), "clips": v["clips"], "hours": round(v["hours"], 2),
                       "emotion_level": dict(sorted(v["emotion_level"].items()))} for k, v in by_split.items()},
        "fps": dict(Counter(str(round(r["fps"])) for r in valid)),
        "resolution": dict(Counter(f"{r['width']}x{r['height']}" for r in valid)),
        "invalid_examples": [{"clip_id": r["clip_id"], "reason": r["reason"]} for r in rows if not r["valid"]][:30],
    }
    # Leakage check: no actor may appear in two splits.
    seen = {}
    for r in rows:
        assert seen.setdefault(r["actor"], r["split"]) == r["split"], "actor leaked across splits"
    with open(f"{OUT}/mead_v2/manifests/summary.json", "w") as f:
        json.dump(summary, f, indent=1)
    out.commit()
    return summary


@app.local_entrypoint()
def main(skip_extract: bool = False):
    if not skip_extract:
        import subprocess  # noqa: F401

        actors = [
            "M003", "M005", "M007", "M009", "M011", "M012", "M013", "M019", "M022", "M023", "M024", "M025",
            "M027", "M028", "M029", "M030", "M031", "M033", "M034", "M035", "M037", "M039", "M040", "M041",
            "W009", "W011", "W014", "W015", "W016", "W018", "W019", "W023", "W024", "W025", "W026", "W028",
            "W029", "W033", "W035", "W036", "W037", "W038", "W040",
        ]
        for r in extract_l23.map(actors, return_exceptions=True):
            print(r)
    print(json.dumps(build_manifest.remote(), indent=1))
