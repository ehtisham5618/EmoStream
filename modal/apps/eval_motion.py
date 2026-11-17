"""Motion-space validation of several checkpoints on clean and degraded speech features.

Degraded = the same validation clips with 'real microphone' audio (gain, noise, band limit,
echo; modal/apps/extract_wavlm.py --augment). Validation actors only.

    MODAL_PROFILE=abdulmat40 modal run modal/apps/eval_motion.py --runs wl_base,ph_ctrl,ph_aug
"""
from __future__ import annotations

import json

import modal

import _common as C

app = modal.App("emostream-v2-eval-motion")
image = C.engine_image()


@app.function(image=image, gpu="T4", volumes={C.MODELS: C.models_vol, C.DATA: C.data_vol}, timeout=3600, memory=32768)
def run(runs: str) -> dict:
    import numpy as np
    import torch

    from emostream.models import BehaviourNet
    from emostream.training.data import ClipSet
    from emostream.training.trainer import evaluate

    packed = json.load(open(f"{C.DATA}/mead_v2/manifests/packed.json"))
    out = {}
    sets = {}
    for kind in ("wavlm", "wavlm_aug"):
        rows, store = [], {}
        for actor, info in sorted(packed["actors"].items()):
            if info["split"] != "val":
                continue
            z = np.load(info["pack"])
            w = np.load(f"{C.DATA}/mead_v2/{kind}/{actor}.npz")
            valid = np.load(f"{C.DATA}/mead_v2/wavlm/{actor}.npz")["valid"]
            arr = {k: z[k] for k in ("exp", "pose", "t", "scale")}
            arr["hubert"] = w["wavlm"]
            ends = np.cumsum(z["lengths"])
            for cid, emo, lv, s, e, ok in zip(z["clip_ids"].tolist(), z["emotions"].tolist(), z["levels"].tolist(),
                                              ends - z["lengths"], ends, valid):
                if ok:
                    store[cid] = (arr, int(s), int(e))
                    rows.append({"clip_id": cid, "actor": actor, "emotion": emo, "level": int(lv), "split": "val",
                                 "features": cid})
        loader = (lambda st: (lambda cid: {k: v[st[cid][1]:st[cid][2]] for k, v in st[cid][0].items()}))(store)
        sets[kind] = (rows, loader)
    for name in runs.split(","):
        blob = torch.load(f"{C.MODELS}/emostream/{name}/model.pt", map_location="cpu", weights_only=False)
        net = BehaviourNet.load(blob).cuda()
        la = int(net.cfg.lookahead)
        res = {}
        for kind, (rows, loader) in sets.items():
            cs = ClipSet(rows, loader=loader, lookahead=la)
            m = evaluate(net, cs.clips, "cuda")
            res[kind] = {"lip_corr": round(m["lip_corr"], 4), "lip_amp": round(m["lip_amp"], 3),
                         "upper_amp": round(m["upper_amp"], 3),
                         "offset_cos": {k: round(v, 2) for k, v in m["offset_cos"].items()}}
        out[name] = res
        print(name, json.dumps(res), flush=True)
    return out


@app.local_entrypoint()
def main(runs: str = "wl_base"):
    print(json.dumps(run.remote(runs), indent=1))
