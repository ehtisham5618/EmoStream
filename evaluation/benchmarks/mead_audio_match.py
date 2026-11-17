"""Pairs every motion clip with its MEAD audio file, verified by content.

1. Same emotion, level and number with a duration within 120 ms: accepted (the normal case).
2. Otherwise, within the same emotion and level folder, video and audio clips are paired by
   duration (minimum-cost assignment; the .m4a is about 19 ms shorter than its video). A pair
   is accepted only if its duration error is under 60 ms and no other audio file of that
   folder is within 60 ms of the same video (unambiguous).
3. Content check: Ditto's streaming HuBERT is run on the .m4a and correlated with the HuBERT
   features stored in the pack, which were computed from the video's own audio track. The
   right audio gives a correlation near 1. Every pair from step 2 is checked, plus a sample
   from step 1; pairs below ``--min-corr`` are dropped.

Clips without an accepted pair are left out of WavLM training (listed in the output).

    python -m evaluation.benchmarks.mead_audio_match --packs outputs/local/packed \
        --audio outputs/local/mead_tar --onnx outputs/local/aux/hubert.onnx --out outputs/local/mead_audio_map.json
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import defaultdict

import numpy as np

from emostream.audio.features import StreamingHubert


def load_m4a(path: str) -> np.ndarray | None:
    r = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                       capture_output=True)
    if r.returncode != 0 or not r.stdout:
        return None
    return np.frombuffer(r.stdout, "<i2").astype(np.float32) / 32768.0


def content_corr(hub: StreamingHubert, audio: np.ndarray, stored: np.ndarray) -> float:
    f = hub.features(audio)
    n = min(len(f), len(stored)) - 2          # the last frames differ (shorter .m4a tail)
    if n < 10:
        return float("nan")
    a, b = f[:n].ravel(), stored[:n].astype(np.float32).ravel()
    return float(np.corrcoef(a, b)[0, 1])


def assign(costs: np.ndarray):
    from scipy.optimize import linear_sum_assignment

    return linear_sum_assignment(costs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packs", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--onnx", required=True)
    ap.add_argument("--min-corr", type=float, default=0.9)
    ap.add_argument("--sample-consistent", type=int, default=3, help="content-check this many normal pairs per actor")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    hub = StreamingHubert(a.onnx)
    rng = np.random.default_rng(0)
    result = {"mapping": {}, "dropped": {}, "summary": []}
    for actor in sorted(f[:-4] for f in os.listdir(a.packs) if f.endswith(".npz")):
        root = os.path.join(a.audio, actor, "audio")
        if not os.path.isdir(root):
            continue
        z = np.load(os.path.join(a.packs, f"{actor}.npz"))
        ids, lengths = z["clip_ids"].tolist(), z["lengths"].tolist()
        starts = np.cumsum([0] + lengths[:-1])
        hub_all = z["hubert"]                # read once: each z[...] access decompresses the whole array
        stored = {cid: hub_all[s:s + n] for cid, s, n in zip(ids, starts, lengths)}
        vid_s = {cid: n * 0.04 for cid, n in zip(ids, lengths)}
        dur_cache: dict[str, float] = {}

        def adur(rel):
            if rel not in dur_cache:
                x = load_m4a(os.path.join(root, rel))
                dur_cache[rel] = float("nan") if x is None else len(x) / 16000
            return dur_cache[rel]

        mapping, by_folder = {}, defaultdict(list)
        for cid in ids:
            _, emo, lv, num = cid.split("_")
            folder = f"{emo}/level_{lv[1:]}"
            rel = f"{folder}/{num}.m4a"
            if os.path.exists(os.path.join(root, rel)) and abs(vid_s[cid] - adur(rel)) <= 0.12:
                mapping[cid] = (rel, "number")
            else:
                by_folder[folder].append(cid)
        # step 2: duration assignment within each folder for the rest
        for folder, cids in by_folder.items():
            used = {r for r, _ in mapping.values()}
            files = sorted(f"{folder}/{f}" for f in os.listdir(os.path.join(root, folder))
                           if f.endswith(".m4a") and f"{folder}/{f}" not in used) if os.path.isdir(
                os.path.join(root, folder)) else []
            files = [f for f in files if adur(f) == adur(f)]
            if not files:
                continue
            target = np.array([vid_s[c] - 0.019 for c in cids])
            have = np.array([adur(f) for f in files])
            cost = np.abs(target[:, None] - have[None, :])
            rows, cols = assign(cost)
            for r, c in zip(rows, cols):
                second = np.sort(cost[r])[1] if cost.shape[1] > 1 else 9.0
                if cost[r, c] < 0.06 and second > 0.06:
                    mapping[cids[r]] = (files[c], "duration")
        # step 3: content check
        checked, dropped = 0, []
        normal = [c for c, (_, how) in mapping.items() if how == "number"]
        to_check = [c for c, (_, how) in mapping.items() if how == "duration"]
        to_check += list(rng.choice(normal, size=min(a.sample_consistent, len(normal)), replace=False)) if normal else []
        corrs = []
        for cid in to_check:
            x = load_m4a(os.path.join(root, mapping[cid][0]))
            cc = content_corr(hub, x, stored[cid]) if x is not None else float("nan")
            corrs.append((cid, mapping[cid][1], cc))
            checked += 1
            if not (cc >= a.min_corr):
                dropped.append(cid)
                del mapping[cid]
        missing = [c for c in ids if c not in mapping]
        result["mapping"][actor] = {c: r for c, (r, _) in mapping.items()}
        result["dropped"][actor] = missing
        s = {"actor": actor, "clips": len(ids), "by_number": sum(1 for _, h in mapping.values() if h == "number"),
             "by_duration": sum(1 for _, h in mapping.values() if h == "duration"), "unpaired": len(missing),
             "content_checked": checked,
             "content_corr_min_kept": round(min([c for _, _, c in corrs if c >= a.min_corr], default=float("nan")), 3),
             "content_failed": len(dropped)}
        result["summary"].append(s)
        print(json.dumps(s), flush=True)
        with open(a.out, "w") as f:
            json.dump(result, f, indent=1)


if __name__ == "__main__":
    main()
