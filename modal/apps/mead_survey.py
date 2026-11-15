"""Independent, read-only survey of the raw MEAD files on the Modal volume.

Walks ``/mead/extracted`` (the original dataset, mounted read-only), counts every
video/audio file per actor / view / emotion / level, pairs audio with video, and
ffprobes a deterministic sample of each to verify that files decode.

Nothing is written to the raw volume. The JSON report is written to the separate
``emostream-v2-data`` volume and printed.

Run:  modal run modal/apps/mead_survey.py
"""
from __future__ import annotations

import json

import modal

app = modal.App("emostream-v2-mead-survey")

raw = modal.Volume.from_name("emostream-mead-raw").read_only()
out = modal.Volume.from_name("emostream-v2-data", create_if_missing=True)
image = modal.Image.debian_slim(python_version="3.11").apt_install("ffmpeg")

RAW = "/mead"
OUT = "/data"


def _probe(path: str) -> dict:
    import subprocess

    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames,sample_rate,channels,duration"
        ":format=duration",
        path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return {"ok": False, "error": r.stderr.strip()[:200]}
        j = json.loads(r.stdout)
        return {"ok": True, "streams": j.get("streams", []), "duration": float(j["format"].get("duration", 0))}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": repr(e)[:200]}


@app.function(image=image, volumes={RAW: raw, OUT: out}, timeout=3600, cpu=8)
def survey(probe_per_actor: int = 12) -> dict:
    import os
    import random
    from collections import Counter, defaultdict
    from concurrent.futures import ThreadPoolExecutor

    root = f"{RAW}/extracted"
    actors = sorted(os.listdir(root))
    videos: dict[tuple, str] = {}
    audios: dict[tuple, str] = {}
    exts = Counter()
    odd = []
    for a in actors:
        for kind in ("video", "audio"):
            base = os.path.join(root, a, kind)
            if not os.path.isdir(base):
                odd.append(f"missing dir {a}/{kind}")
                continue
            for dp, _dn, fns in os.walk(base):
                rel = os.path.relpath(dp, base).split(os.sep)
                for fn in fns:
                    stem, ext = os.path.splitext(fn)
                    exts[(kind, ext.lower())] += 1
                    full = os.path.join(dp, fn)
                    if kind == "video" and len(rel) == 3:  # view/emotion/level
                        videos[(a, rel[0], rel[1], rel[2], stem)] = full
                    elif kind == "audio" and len(rel) == 2:  # emotion/level
                        audios[(a, rel[0], rel[1], stem)] = full
                    else:
                        odd.append(full)

    per_actor = defaultdict(lambda: Counter())
    views, emotions, levels = Counter(), Counter(), Counter()
    emo_level = Counter()
    paired = 0
    video_no_audio = []
    for (a, v, e, l, s) in videos:
        views[v] += 1
        emotions[e] += 1
        levels[l] += 1
        emo_level[f"{e}/{l}"] += 1
        per_actor[a][f"video:{v}"] += 1
        if (a, e, l, s) in audios:
            paired += 1
            per_actor[a]["paired"] += 1
        else:
            video_no_audio.append("/".join((a, v, e, l, s)))
    vkeys = {(a, e, l, s) for (a, _v, e, l, s) in videos}
    audio_no_video = ["/".join(k) for k in audios if k not in vkeys]
    for (a, e, l, s) in audios:
        per_actor[a]["audio"] += 1

    # Deterministic probe sample: N paired clips per actor.
    rng = random.Random(0)
    sample = []
    by_actor = defaultdict(list)
    for k in videos:
        if (k[0], k[2], k[3], k[4]) in audios:
            by_actor[k[0]].append(k)
    for a in actors:
        ks = sorted(by_actor[a])
        rng.shuffle(ks)
        sample += ks[:probe_per_actor]

    def probe_pair(k):
        a, v, e, l, s = k
        pv = _probe(videos[k])
        pa = _probe(audios[(a, e, l, s)])
        return k, pv, pa

    with ThreadPoolExecutor(16) as ex:
        probed = list(ex.map(probe_pair, sample))

    vres, fps, asr, ach, vcodec, acodec = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    video_has_audio_stream = 0
    dur_diffs, vdur = [], []
    failures = []
    for k, pv, pa in probed:
        if not pv["ok"] or not pa["ok"]:
            failures.append({"clip": "/".join(k), "video": pv, "audio": pa})
            continue
        vs = [s for s in pv["streams"] if s.get("codec_type") == "video"]
        if any(s.get("codec_type") == "audio" for s in pv["streams"]):
            video_has_audio_stream += 1
        if vs:
            vres[f"{vs[0].get('width')}x{vs[0].get('height')}"] += 1
            fps[vs[0].get("r_frame_rate")] += 1
            vcodec[vs[0].get("codec_name")] += 1
        as_ = [s for s in pa["streams"] if s.get("codec_type") == "audio"]
        if as_:
            asr[as_[0].get("sample_rate")] += 1
            ach[as_[0].get("channels")] += 1
            acodec[as_[0].get("codec_name")] += 1
        vdur.append(pv["duration"])
        dur_diffs.append(pv["duration"] - pa["duration"])

    def stats(xs):
        if not xs:
            return {}
        xs = sorted(xs)
        n = len(xs)
        return {"n": n, "min": xs[0], "p50": xs[n // 2], "p95": xs[int(n * 0.95)], "max": xs[-1],
                "mean": sum(xs) / n}

    report = {
        "root": root,
        "n_actors": len(actors),
        "actors": actors,
        "n_video_files": len(videos),
        "n_audio_files": len(audios),
        "n_paired": paired,
        "extensions": {f"{k[0]}{k[1]}": v for k, v in exts.items()},
        "views": dict(views),
        "emotions": dict(emotions),
        "levels": dict(levels),
        "emotion_level": dict(sorted(emo_level.items())),
        "per_actor": {a: dict(c) for a, c in sorted(per_actor.items())},
        "n_video_without_audio": len(video_no_audio),
        "video_without_audio_examples": video_no_audio[:20],
        "n_audio_without_video": len(audio_no_video),
        "audio_without_video_examples": audio_no_video[:20],
        "unexpected_paths": odd[:40],
        "n_unexpected_paths": len(odd),
        "probe": {
            "n_sampled": len(sample),
            "n_failed": len(failures),
            "failures": failures[:20],
            "video_resolution": dict(vres),
            "video_fps": dict(fps),
            "video_codec": dict(vcodec),
            "video_files_with_embedded_audio": video_has_audio_stream,
            "audio_sample_rate": dict(asr),
            "audio_channels": {str(k): v for k, v in ach.items()},
            "audio_codec": dict(acodec),
            "video_duration_s": stats(vdur),
            "video_minus_audio_duration_s": stats(dur_diffs),
        },
    }
    os.makedirs(f"{OUT}/mead_survey", exist_ok=True)
    with open(f"{OUT}/mead_survey/survey.json", "w") as f:
        json.dump(report, f, indent=1)
    out.commit()
    return report


@app.function(image=image, volumes={RAW: raw, OUT: out}, timeout=3600, cpu=4)
def archive_contents(actors: list[str]) -> dict:
    """Lists the original tar archives (read-only) to see which views and intensity
    levels they contain, compared with what was extracted."""
    import os
    import tarfile
    from collections import Counter

    res = {}
    for a in actors:
        p = f"{RAW}/archives/{a}/video.tar"
        if not os.path.exists(p):
            res[a] = {"error": "missing"}
            continue
        c = Counter()
        n = 0
        with tarfile.open(p) as tf:
            for m in tf:
                if not m.isfile():
                    continue
                n += 1
                parts = m.name.strip("./").split("/")
                # .../<view>/<emotion>/<level>/<clip>.mp4
                if len(parts) >= 4:
                    c["/".join(parts[-4:-1])] += 1
                else:
                    c["other:" + m.name] += 1
        views = Counter(k.split("/")[0] for k in c)
        levels = Counter(k.split("/")[-1] for k in c)
        res[a] = {"size_gib": round(os.path.getsize(p) / 2**30, 2), "n_files": n,
                  "views": sorted(views), "levels": sorted(levels), "by_view_emotion_level": dict(sorted(c.items()))}
    os.makedirs(f"{OUT}/mead_survey", exist_ok=True)
    with open(f"{OUT}/mead_survey/archive_contents.json", "w") as f:
        json.dump(res, f, indent=1)
    out.commit()
    return res


@app.local_entrypoint()
def main(probe_per_actor: int = 12, archives: str = ""):
    if archives:
        rep = archive_contents.remote(archives.split(","))
        for a, r in rep.items():
            print(a, {k: v for k, v in r.items() if k != "by_view_emotion_level"})
            fl = {k: v for k, v in r.get("by_view_emotion_level", {}).items() if k.startswith("front/")}
            print("  front:", fl)
        return
    rep = survey.remote(probe_per_actor)
    print(json.dumps(rep, indent=1))
