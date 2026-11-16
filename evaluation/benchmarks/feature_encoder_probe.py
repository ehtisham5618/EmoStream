"""How much lip-motion information do different speech encoders carry?

For validation clips with real motion (one validation actor's pack plus its 16 kHz audio),
each encoder's hidden states are resampled to the 25 FPS video rate, and a ridge
regression from a window of features (frames t-4 .. t+2, the context the live model has)
to all lip-keypoint coordinates is fitted on half of the clips and scored on the other
half (then swapped). The score is the same per-coordinate correlation the training uses.

Encoders run on whole clips (full context), so this is an upper bound for each encoder,
not its streaming performance. Ditto's streaming HuBERT (the features the model uses now)
is read from the pack.

    python -m evaluation.benchmarks.feature_encoder_probe --pack outputs/local/M005.npz \
        --wav-dir outputs/local/gt_m005
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
import soundfile as sf
import torch

from emostream.training.data import lip_columns, to_delta

ENCODERS = {
    "wav2vec2-base-960h": "facebook/wav2vec2-base-960h",
    "wavlm-base-plus": "microsoft/wavlm-base-plus",
    "whisper-base": "openai/whisper-base",
}


def to_25fps(h: np.ndarray, n: int) -> np.ndarray:
    """(T_enc, D) at ~50 Hz -> (n, D) at 25 Hz by averaging the encoder frames of each video frame."""
    t_enc = np.linspace(0, n, len(h), endpoint=False)
    out = np.zeros((n, h.shape[1]), np.float32)
    cnt = np.zeros(n)
    idx = np.clip(t_enc.astype(int), 0, n - 1)
    np.add.at(out, idx, h)
    np.add.at(cnt, idx, 1)
    empty = cnt == 0
    out[~empty] /= cnt[~empty, None]
    if empty.any():  # nearest filled frame
        filled = np.where(~empty)[0]
        out[empty] = out[filled[np.abs(filled[:, None] - np.where(empty)[0][None]).argmin(0)]]
    return out


def encode(name: str, audios: list[np.ndarray], lengths: list[int]) -> list[list[np.ndarray]]:
    """Per clip, a list of per-layer (n, D) features."""
    from transformers import AutoFeatureExtractor, AutoModel

    repo = ENCODERS[name]
    fe = AutoFeatureExtractor.from_pretrained(repo)
    model = AutoModel.from_pretrained(repo).eval()
    out = []
    for a, n in zip(audios, lengths):
        with torch.no_grad():
            if name.startswith("whisper"):
                inp = fe(a, sampling_rate=16000, return_tensors="pt")
                hs = model.encoder(inp.input_features, output_hidden_states=True).hidden_states
                frames = int(round(len(a) / 16000 * 50))
                layers = [h[0, :frames].numpy() for h in hs]
            else:
                inp = fe(a, sampling_rate=16000, return_tensors="pt")
                hs = model(inp.input_values, output_hidden_states=True).hidden_states
                layers = [h[0].numpy() for h in hs]
        out.append([to_25fps(h, n) for h in layers])
    return out


def encode_streaming(name: str, audios: list[np.ndarray], lengths: list[int], layer: int,
                     past_s: float = 1.0, future_frames: int = 2, block: int = 5) -> list[np.ndarray]:
    """Live conditions: every ``block`` frames the encoder sees only the last ``past_s`` seconds
    plus ``future_frames`` frames after the block, and the block's features are kept.
    This is how Ditto's streaming encoder is used (block 5, 2 future frames)."""
    from transformers import AutoFeatureExtractor, AutoModel

    repo = ENCODERS[name]
    fe = AutoFeatureExtractor.from_pretrained(repo)
    model = AutoModel.from_pretrained(repo).eval()
    out = []
    for a, n in zip(audios, lengths):
        feats = np.zeros((n, model.config.hidden_size if hasattr(model.config, "hidden_size") else model.config.d_model),
                         np.float32)
        for b0 in range(0, n, block):
            b1 = min(n, b0 + block)
            end = min(len(a), (b1 + future_frames) * 640)
            start = max(0, b1 * 640 - int(past_s * 16000))
            seg = a[start:end]
            with torch.no_grad():
                inp = fe(seg, sampling_rate=16000, return_tensors="pt")
                if name.startswith("whisper"):
                    h = model.encoder(inp.input_features, output_hidden_states=True).hidden_states[layer][0]
                    h = h[: int(round(len(seg) / 16000 * 50))].numpy()
                else:
                    h = model(inp.input_values, output_hidden_states=True).hidden_states[layer][0].numpy()
            seg_frames = len(seg) / 640
            f = to_25fps(h, max(1, int(round(seg_frames))))
            first = start // 640
            for t in range(b0, b1):
                feats[t] = f[min(len(f) - 1, t - first)]
        out.append(feats)
    return out


def window(f: np.ndarray, past: int = 4, future: int = 2) -> np.ndarray:
    T = len(f)
    idx = np.arange(T)
    return np.concatenate([f[np.clip(idx + d, 0, T - 1)] for d in range(-past, future + 1)], 1)


def probe(feats: list[np.ndarray], targets: list[np.ndarray], dim: int = 192, lam: float = 100.0) -> float:
    """Two-fold ridge from windowed features to lip coordinates; mean per-coordinate correlation."""
    allf = np.concatenate(feats, 0)
    mu, sd = allf.mean(0), allf.std(0) + 1e-6
    # PCA to a fixed size so every encoder gets the same number of inputs per frame
    z = (allf - mu) / sd
    _, _, vt = np.linalg.svd(z[:: 2], full_matrices=False)
    P = vt[:dim].T
    X = [window(((f - mu) / sd) @ P) for f in feats]
    half = len(X) // 2
    scores = []
    for fit, test in ((slice(0, half), slice(half, None)), (slice(half, None), slice(0, half))):
        Xf = np.concatenate(X[fit], 0)
        Yf = np.concatenate(targets[fit], 0)
        xm, ym = Xf.mean(0), Yf.mean(0)
        A = (Xf - xm).T @ (Xf - xm) + lam * np.eye(Xf.shape[1])
        W = np.linalg.solve(A, (Xf - xm).T @ (Yf - ym))
        cc = []
        for x, y in zip(X[test], targets[test]):
            p = (x - xm) @ W + ym
            moving = y.std(0) > 0.5 * y.std(0).max()
            cc.append(np.mean([np.corrcoef(p[:, j], y[:, j])[0, 1] for j in np.where(moving)[0]]))
        scores.append(float(np.mean(cc)))
    return round(float(np.mean(scores)), 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--wav-dir", required=True)
    ap.add_argument("--encoders", nargs="*", default=list(ENCODERS))
    ap.add_argument("--out", default="")
    ap.add_argument("--streaming", nargs="*", default=[], help="encoder:layer pairs to test under live conditions")
    a = ap.parse_args()

    z = np.load(a.pack)
    ids = z["clip_ids"].tolist()
    ends = np.cumsum(z["lengths"])
    starts = ends - z["lengths"]
    mot = np.concatenate([z["exp"].reshape(len(z["exp"]), -1), z["pose"], z["t"][:, :2], z["scale"].reshape(-1, 1)],
                         1).astype(np.float32)
    neutral = [i for i, e in enumerate(z["emotions"]) if e == "neutral"]
    rest = np.median(np.concatenate([mot[starts[i]:starts[i] + 3] for i in neutral]), 0)
    cols = lip_columns()
    audios, targets, ditto, lengths = [], [], [], []
    for i, cid in enumerate(ids):
        wav = os.path.join(a.wav_dir, cid + ".wav")
        if not os.path.exists(wav):
            continue
        audio, sr = sf.read(wav, dtype="float32")
        assert sr == 16000
        y = to_delta(mot[starts[i]:ends[i]].copy(), rest)[:, cols]
        n = min(len(y), len(audio) // 640)
        audios.append(audio[: n * 640])
        targets.append(y[:n])
        ditto.append(z["hubert"][starts[i]:starts[i] + n].astype(np.float32))
        lengths.append(n)
    res = {"clips": len(audios), "frames": int(sum(lengths)), "probe": {}}
    print(f"{len(audios)} clips, {sum(lengths)} frames", flush=True)
    res["probe"]["ditto_streaming_hubert (current)"] = probe(ditto, targets)
    print("ditto streaming hubert:", res["probe"]["ditto_streaming_hubert (current)"], flush=True)
    if a.streaming:
        for spec in a.streaming:
            parts = spec.split(":")
            name, layer = parts[0], int(parts[1])
            fut = int(parts[2]) if len(parts) > 2 else 2
            blk = int(parts[3]) if len(parts) > 3 else 5
            s = probe(encode_streaming(name, audios, lengths, layer, future_frames=fut, block=blk), targets)
            res["probe"][f"{name} layer {layer}, streaming (1 s past, {fut * 40} ms future, block {blk})"] = s
            print(f"{name} layer {layer} future {fut} block {blk} streaming:", s, flush=True)
        if a.out:
            with open(a.out, "w") as f:
                json.dump(res, f, indent=1)
        return
    for name in a.encoders:
        layers = encode(name, audios, lengths)
        per_layer = {}
        for L in range(len(layers[0])):
            per_layer[L] = probe([c[L] for c in layers], targets)
        best = max(per_layer, key=per_layer.get)
        res["probe"][name] = {"by_layer": per_layer, "best_layer": best, "best": per_layer[best]}
        print(name, "best layer", best, per_layer[best], "| all:", per_layer, flush=True)
    if a.out:
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
