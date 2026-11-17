"""EmoStream live application on Modal: FastAPI backend + built frontend on one GPU worker.

    cd frontend && npm run build && cd ..
    modal serve  modal/apps/serve.py     # temporary URL, live reload
    modal deploy modal/apps/serve.py     # persistent URL

One worker runs one live session at a time. The worker shuts down after five idle
minutes, so the first request after a pause waits for a cold start (model loading).

Environment:
    EMOSTREAM_RUN       trained behaviour model under /models/emostream (default "wl_base": WavLM
                        speech features, 17 Nov 2026; previous: "it_ccc_la2"; original baseline: "reg")
    EMOSTREAM_EMOTION_GAIN  scale of the emotion branch (default 1.5; 1.0 = as trained)
    EMOSTREAM_HOP       1 (default) per-frame streaming, lowest delay, needs an L40S-class GPU;
                        5 block streaming, for an A10G
    EMOSTREAM_GPU       Modal GPU types in order of preference (default "L40S"; measured too slow
                        for live sessions with the WavLM model: A100-40GB (render 27 ms per frame),
                        A10G, L4, T4)
    EMOSTREAM_TENSORRT  "1" (default) for the TensorRT renderer, "0" for PyTorch (required on a T4)
"""
from __future__ import annotations

import os

import modal

import _common as C

RUN = os.environ.get("EMOSTREAM_RUN", "wl_base")
EMOTION_GAIN = os.environ.get("EMOSTREAM_EMOTION_GAIN", "1.5")
SLOT = os.environ.get("EMOSTREAM_SLOT", "4")    # per-frame read-out slot, 0 (more look-ahead) .. 4
HOP = os.environ.get("EMOSTREAM_HOP", "1")   # 1 = per-frame streaming (L40S); 5 = block streaming (A10G)
# Comma-separated preference list. L40S only by default: an A100 fallback (tried 17 Nov 2026)
# renders a frame in 27 ms instead of 17.5 ms and, with encoding on top, fell behind in the
# user's session 6 (server latency 700 ms, 16 % of frames skipped). A start that waits for an
# L40S is better than a session that silently drops frames.
GPU = [g.strip() for g in os.environ.get("EMOSTREAM_GPU", "L40S").split(",") if g.strip()]
TENSORRT = os.environ.get("EMOSTREAM_TENSORRT", "1") == "1"   # needs an Ampere-or-newer GPU (not T4)

app = modal.App("emostream-v2-live")
image = C.engine_image(
    extra_pip=("fastapi==0.115.6", "python-multipart==0.0.20", "av==13.1.0", "transformers==4.46.3"),
    tensorrt=TENSORRT,
    env={"HF_HOME": f"{C.MODELS}/hf",    # speech-encoder weights cached on the models volume
         "EMOSTREAM_RUN": RUN, "EMOSTREAM_TENSORRT": "1" if TENSORRT else "0",
         "EMOSTREAM_EMOTION_GAIN": EMOTION_GAIN, "EMOSTREAM_HOP": HOP, "EMOSTREAM_SLOT": SLOT},
    local_dirs=((str(C.ROOT / "backend"), "/root/backend"),
                (str(C.ROOT / "frontend" / "dist"), "/root/frontend_dist")),
)


@app.function(image=image, gpu=GPU if len(GPU) > 1 else GPU[0], volumes={C.MODELS: C.models_vol}, scaledown_window=300, max_containers=1,
              timeout=3600)
@modal.concurrent(max_inputs=32)
@modal.asgi_app()
def web():
    os.chdir(C.REPO)
    from backend.api.app import create_app
    from backend.services.live import GpuEngineProvider

    trt = os.environ.get("EMOSTREAM_TENSORRT", "1") == "1"
    provider = GpuEngineProvider(
        C.ensure_checkpoints(tensorrt=trt),
        emostream_checkpoint=f"{C.MODELS}/emostream/{os.environ.get('EMOSTREAM_RUN', 'wl_base')}/model.pt",
        tensorrt=trt, emotion_gain=float(os.environ.get("EMOSTREAM_EMOTION_GAIN", "1.5")),
        hop=int(os.environ.get("EMOSTREAM_HOP", "1")),
        slot=int(os.environ.get("EMOSTREAM_SLOT", "4")),
        # Frames are skipped only when the engine is this far behind. The browser now buffers
        # adaptively and plays the voice with the picture, so a late frame is better than a
        # missing one; 450 ms skipped 4 % of frames when microphone audio arrived in bursts.
        max_latency_ms=float(os.environ.get("EMOSTREAM_MAX_LATENCY_MS", "700")),
    )
    # One throw-away session before the first request is served; a real session then
    # starts on a warm engine. Uses the example portrait that ships with the Ditto repository.
    import glob

    examples = sorted(glob.glob(f"{C.REPO}/example/*.png") + glob.glob(f"{C.REPO}/example/*.jpg"))
    print("warm-up:", provider.warm_up(examples[0]) if examples else "no example portrait found", flush=True)
    return create_app(provider, static_dir="/root/frontend_dist")
