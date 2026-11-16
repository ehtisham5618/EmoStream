"""Does the behaviour model articulate less on browser-microphone audio than on MEAD audio?

Runs the live configuration (per-frame features, the chosen checkpoint, neutral emotion)
on the audio of saved browser sessions and on MEAD validation clips, and compares the
predicted mouth motion: how much the lip keypoints move while the person is speaking.
Also reports the loudness and spectral balance of each source, since browser capture
applies noise suppression and automatic gain control that studio recordings do not have.

    python -m evaluation.benchmarks.mic_domain_check --onnx outputs/local/aux/hubert.onnx \
        --checkpoint outputs/local/it_ccc_la2.pt --mead-dir outputs/local/gt_m005 --sessions s2.webm s3.webm
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import tempfile

import numpy as np
import soundfile as sf
import torch

from emostream.audio.features import StreamingHubert
from emostream.constants import LIP_KEYPOINTS
from emostream.models import BehaviourNet
from emostream.training.data import emotion_vector, shift_features

FRAME = 640


def load_audio(path: str) -> np.ndarray:
    if path.endswith(".wav"):
        a, sr = sf.read(path, dtype="float32")
        if a.ndim > 1:
            a = a.mean(1)
        if sr != 16000:
            raise ValueError(f"{path}: expected 16 kHz")
        return a
    tmp = os.path.join(tempfile.mkdtemp(), "a.wav")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000", tmp], check=True)
    a, _ = sf.read(tmp, dtype="float32")
    return a


def frame_rms(a: np.ndarray) -> np.ndarray:
    n = len(a) // FRAME
    return np.sqrt((a[: n * FRAME].reshape(n, FRAME) ** 2).mean(1) + 1e-12)


def speech_mask(rms: np.ndarray) -> np.ndarray:
    """Frames louder than 20 dB below the 95th-percentile level count as speech."""
    db = 20 * np.log10(rms)
    return db > np.percentile(db, 95) - 20


def high_band_ratio(a: np.ndarray) -> float:
    """Energy above 4 kHz relative to 300 Hz–4 kHz (speech frames only)."""
    spec = np.abs(np.fft.rfft(a[: len(a) // 512 * 512].reshape(-1, 512) * np.hanning(512), axis=1)) ** 2
    f = np.fft.rfftfreq(512, 1 / 16000)
    hi = spec[:, f > 4000].sum(1)
    mid = spec[:, (f > 300) & (f <= 4000)].sum(1)
    loud = mid > np.percentile(mid, 50)
    return float(hi[loud].sum() / max(mid[loud].sum(), 1e-12))


def predict(net, hub, audio, lookahead):
    feats = hub.features_per_frame(audio, 4)
    x = torch.from_numpy(shift_features(feats, lookahead)[None]).float()
    emo = torch.from_numpy(np.repeat(emotion_vector("neutral", 1.0)[None, None], x.shape[1], 1)).float()
    with torch.no_grad():
        out = net(x, emo)
    out = out[0] if isinstance(out, tuple) else out
    return out[0].numpy()


def lip_activity(motion: np.ndarray, mask: np.ndarray) -> dict:
    lip = np.zeros((21, 3), bool)
    lip[list(LIP_KEYPOINTS)] = True
    exp = motion[:, :63][:, lip.reshape(-1)]
    n = min(len(exp), len(mask))
    exp, mask = exp[:n], mask[:n]
    vel = np.abs(np.diff(exp, axis=0)).mean(1)
    return {"lip_std_speech": float(exp[mask].std(0).mean()) if mask.sum() > 10 else None,
            "lip_speed_speech": float(vel[mask[1:]].mean()) if mask[1:].sum() > 10 else None,
            "speech_frames": int(mask.sum()), "frames": int(n)}


def describe(name, audio, net, hub, la):
    rms = frame_rms(audio)
    mask = speech_mask(rms)
    m = predict(net, hub, audio, la)
    out = {"source": name, "seconds": round(len(audio) / 16000, 1),
           "speech_level_dbfs": round(float(20 * np.log10(np.median(rms[mask]))), 1) if mask.any() else None,
           "high_band_ratio": round(high_band_ratio(audio), 4)}
    out.update({k: (round(v, 5) if isinstance(v, float) else v) for k, v in lip_activity(m, mask).items()})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onnx", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--mead-dir", required=True)
    ap.add_argument("--sessions", nargs="*", default=[])
    ap.add_argument("--max-mead", type=int, default=12)
    ap.add_argument("--normalise-db", type=float, default=None,
                    help="also rerun each session with its speech level set to this dBFS")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    ck = torch.load(a.checkpoint, map_location="cpu", weights_only=False)
    net = BehaviourNet.load(ck).eval()
    la = int(getattr(net.cfg, "lookahead", 0))
    hub = StreamingHubert(a.onnx)
    rows = []
    for w in sorted(glob.glob(os.path.join(a.mead_dir, "*.wav")))[: a.max_mead]:
        rows.append(describe("MEAD " + os.path.basename(w), load_audio(w), net, hub, la))
    for s in a.sessions:
        audio = load_audio(s)
        rows.append(describe("browser " + os.path.basename(s), audio, net, hub, la))
        if a.normalise_db is not None:
            rms = frame_rms(audio)
            mask = speech_mask(rms)
            gain = 10 ** ((a.normalise_db - 20 * np.log10(np.median(rms[mask]))) / 20)
            rows.append(describe(f"browser {os.path.basename(s)} at {a.normalise_db} dBFS",
                                 np.clip(audio * gain, -1, 1), net, hub, la))
    for r in rows:
        print(json.dumps(r))
    mead = [r["lip_std_speech"] for r in rows if r["source"].startswith("MEAD") and r["lip_std_speech"]]
    print("MEAD mean lip std during speech:", round(float(np.mean(mead)), 5) if mead else None)
    if a.out:
        with open(a.out, "w") as f:
            json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main()
