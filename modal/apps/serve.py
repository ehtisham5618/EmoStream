"""EmoStream live application on Modal: FastAPI backend + built frontend on one GPU worker.

    cd frontend && npm run build && cd ..
    modal serve  modal/apps/serve.py     # temporary URL, live reload
    modal deploy modal/apps/serve.py     # persistent URL

One worker runs one live session at a time. The worker shuts down after five idle
minutes, so the first request after a pause waits for a cold start (model loading).

Environment:
    EMOSTREAM_RUN       trained behaviour model under /models/emostream (default "reg")
    EMOSTREAM_GPU       Modal GPU type (default "L40S": 25 FPS measured; "A10G" is cheaper, ~23 FPS)
    EMOSTREAM_TENSORRT  "1" (default) for the TensorRT renderer, "0" for PyTorch (required on a T4)
"""
from __future__ import annotations

import os

import modal

import _common as C

RUN = os.environ.get("EMOSTREAM_RUN", "reg")
GPU = os.environ.get("EMOSTREAM_GPU", "L40S")
TENSORRT = os.environ.get("EMOSTREAM_TENSORRT", "1") == "1"   # needs an Ampere-or-newer GPU (not T4)

app = modal.App("emostream-v2-live")
image = C.engine_image(
    extra_pip=("fastapi==0.115.6", "python-multipart==0.0.20"), tensorrt=TENSORRT,
    env={"EMOSTREAM_RUN": RUN, "EMOSTREAM_TENSORRT": "1" if TENSORRT else "0"},
    local_dirs=((str(C.ROOT / "backend"), "/root/backend"),
                (str(C.ROOT / "frontend" / "dist"), "/root/frontend_dist")),
)


@app.function(image=image, gpu=GPU, volumes={C.MODELS: C.models_vol}, scaledown_window=300, max_containers=1,
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
        emostream_checkpoint=f"{C.MODELS}/emostream/{os.environ.get('EMOSTREAM_RUN', 'reg')}/model.pt",
        tensorrt=trt,
    )
    return create_app(provider, static_dir="/root/frontend_dist")
