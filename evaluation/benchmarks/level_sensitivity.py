"""Does the live model's mouth motion depend on how loud the input voice is?

MEAD validation clips are rescaled so that their speech sits at a range of levels (dBFS,
median over speech frames), passed through the checkpoint's own speech features, and the
predicted lip motion is compared with the prediction at the clip's original level:
  lip_std_ratio   lip-keypoint motion during speech, relative to the original level
  corr_to_ref     correlation of the predicted lip trajectory with the original-level one

    python -m evaluation.benchmarks.level_sensitivity --checkpoint outputs/local/wl_base.pt \
        --wav-dir outputs/local/gt_m005 --levels -20 -30 -40 -47 -55
"""
from __future__ import annotations

import argparse
import glob
import json
import os

import numpy as np
import soundfile as sf
import torch

from emostream.models import BehaviourNet
from emostream.training.data import emotion_vector, lip_columns, shift_features


def speech_db(a):
    fr = np.sqrt((a[: len(a) // 640 * 640].reshape(-1, 640) ** 2).mean(1)) + 1e-9
    db = 20 * np.log10(fr)
    m = db > np.percentile(db, 95) - 20
    return float(np.median(db[m])), m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--wav-dir", required=True)
    ap.add_argument("--clips", type=int, default=6)
    ap.add_argument("--levels", type=float, nargs="+", default=[-20, -30, -40, -47, -55])
    ap.add_argument("--hubert-onnx", default="outputs/local/aux/hubert.onnx")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    net = BehaviourNet.load(torch.load(a.checkpoint, map_location="cpu", weights_only=False)).eval()
    la = int(getattr(net.cfg, "lookahead", 0))
    if getattr(net.cfg, "features", "ditto_hubert") == "wavlm":
        from emostream.audio.wavlm import WavLMFeatures

        fc = net.cfg.feature_config or {}
        x = WavLMFeatures(layer=fc.get("layer", 6), past_s=fc.get("past_samples", 16000) / 16000,
                          future_frames=fc.get("future_frames", 2))
        feats = lambda audio, n: x.frames(audio, n, batch=48)
    else:
        from emostream.audio.features import StreamingHubert

        hub = StreamingHubert(a.hubert_onnx)
        feats = lambda audio, n: hub.features_per_frame(audio, 4)[:n]
    cols = lip_columns()
    rows = []
    for w in sorted(glob.glob(os.path.join(a.wav_dir, "*neutral*.wav")))[: a.clips]:
        audio, _ = sf.read(w, dtype="float32")
        n = len(audio) // 640
        base_db, mask = speech_db(audio)
        preds = {}
        for lv in [None] + a.levels:
            g = 1.0 if lv is None else 10 ** ((lv - base_db) / 20)
            f = feats(np.clip(audio * g, -1, 1), n)
            xin = torch.from_numpy(shift_features(f, la)[None]).float()
            e = torch.from_numpy(np.repeat(emotion_vector("neutral", 1)[None, None], n, 1)).float()
            with torch.no_grad():
                p = net(xin, e)[0][0].numpy()[:, :63][:, cols]
            preds[lv] = p
        ref = preds[None]
        m = mask[: len(ref)]
        for lv in a.levels:
            p = preds[lv]
            rows.append({"clip": os.path.basename(w), "original_db": round(base_db, 1), "level_db": lv,
                         "lip_std_ratio": float(p[m].std(0).mean() / (ref[m].std(0).mean() + 1e-12)),
                         "corr_to_ref": float(np.mean([np.corrcoef(p[:, j], ref[:, j])[0, 1] for j in range(p.shape[1])
                                                       if ref[:, j].std() > 1e-9]))})
        print(rows[-1]["clip"], "done", flush=True)
    summary = {}
    for lv in a.levels:
        r = [x for x in rows if x["level_db"] == lv]
        summary[lv] = {"lip_std_ratio": round(float(np.mean([x["lip_std_ratio"] for x in r])), 3),
                       "corr_to_ref": round(float(np.mean([x["corr_to_ref"] for x in r])), 3)}
    print(json.dumps({"checkpoint": os.path.basename(a.checkpoint), "original_db_mean": round(float(np.mean([x["original_db"] for x in rows])), 1),
                      "by_level": summary}, indent=1))
    if a.out:
        with open(a.out, "w") as f:
            json.dump({"rows": rows, "summary": summary}, f, indent=1)


if __name__ == "__main__":
    main()
