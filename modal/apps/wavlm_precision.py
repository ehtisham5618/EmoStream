"""How much do TF32 matmuls change WavLM features, and how fast is a live frame on each GPU?

    MODAL_PROFILE=abdulmat40 modal run modal/apps/wavlm_precision.py --gpu A100-40GB
"""
from __future__ import annotations

import json

import modal

import _common as C

app = modal.App("emostream-v2-wavlm-precision")
image = C.engine_image(extra_pip=("transformers==4.46.3",), env={"HF_HOME": f"{C.MODELS}/hf"})


def _run() -> dict:
    import time

    import numpy as np
    import torch

    from emostream.audio.wavlm import FRAME, WavLMFeatures

    rng = np.random.default_rng(0)
    import soundfile as sf

    audio, _ = sf.read(f"{C.DATA}/eval/val/M005/happy.wav", dtype="float32")
    n = min(200, len(audio) // FRAME - 3)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    x32 = WavLMFeatures(device="cuda", tf32=False)
    f32 = x32.frames(audio, n)
    x = WavLMFeatures(device="cuda", tf32=True, model=x32.model, extractor=x32.fe)
    ftf = x.frames(audio, n)
    cos = (f32 * ftf).sum(1) / (np.linalg.norm(f32, axis=1) * np.linalg.norm(ftf, axis=1))
    rel = np.linalg.norm(f32 - ftf, axis=1) / np.linalg.norm(f32, axis=1)
    out = {"gpu": torch.cuda.get_device_name(0), "frames": n, "cosine_min": float(cos.min()),
           "relative_error_mean": float(rel.mean()), "relative_error_max": float(rel.max())}
    for name, tf in (("fp32", False), ("tf32", True)):
        torch.backends.cuda.matmul.allow_tf32 = tf
        torch.backends.cudnn.allow_tf32 = tf
        for batch in (1, 2):
            segs = [x.segment(audio, 60 + i)[0] for i in range(batch)]
            for _ in range(5):
                x._encode(segs)
            torch.cuda.synchronize()
            t = time.perf_counter()
            for _ in range(30):
                x._encode(segs)
            torch.cuda.synchronize()
            out[f"{name}_ms_per_call_batch{batch}"] = round((time.perf_counter() - t) / 30 * 1000, 2)
    return out


@app.function(image=image, gpu="A100-40GB", volumes={C.MODELS: C.models_vol, C.DATA: C.data_vol}, timeout=900)
def run() -> dict:
    return _run()


@app.local_entrypoint()
def main(gpu: str = "A100-40GB"):
    print(json.dumps(run.with_options(gpu=gpu).remote(), indent=1))
