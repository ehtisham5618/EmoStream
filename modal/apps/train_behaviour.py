"""Trains the EmoStream behaviour model on MEAD features (train split), selecting on val.

The test split is never loaded here.

    modal run modal/apps/train_behaviour.py --run base
    modal run modal/apps/train_behaviour.py --run joint --no-separate-branches   # ablation
"""
from __future__ import annotations

import json

import modal

import _common as C

app = modal.App("emostream-v2-train-behaviour")
image = C.engine_image()
RUNS = f"{C.MODELS}/emostream"


@app.function(image=image, gpu=["T4", "L4", "A10G"], volumes={C.MODELS: C.models_vol, C.DATA: C.data_vol},
              timeout=3 * 3600, cpu=8, memory=32768)
def train_run(run: str = "base", steps: int = 12000, separate_branches: bool = True, lip_cap: float = 0.35,
              hidden: int = 256, w_velocity: float = 1.0, seed: int = 0, max_train_clips: int = 0,
              dropout: float = 0.1, lr: float = 1e-3, eval_every: int = 500, weight_decay: float = 1e-4,
              w_ccc: float = 0.0, lookahead: int = 0, w_vel_ccc: float = 0.0, w_closure: float = 0.0,
              features: str = "ditto_hubert", only_valid_wavlm: bool = False, w_viseme: float = 0.0,
              w_bilabial: float = 0.0, aug_prob: float = 0.0, init_from: str = "") -> dict:
    import os
    import numpy as np
    import torch

    from emostream.models.behaviour_net import BehaviourConfig
    from emostream.training.data import ClipSet
    from emostream.training.trainer import TrainConfig, train

    packed = json.load(open(f"{C.DATA}/mead_v2/manifests/packed.json"))
    feature_config: dict = {}

    def load_split(split, max_clips=0):
        """ClipSet from the per-actor packs of one split. Never called with 'test'."""
        assert split in ("train", "val")
        rows, store = [], {}
        for actor, info in sorted(packed["actors"].items()):
            if info["split"] != split:
                continue
            z = np.load(info["pack"])
            arr = {k: z[k] for k in ("exp", "pose", "t", "scale", "hubert")}
            if w_viseme > 0 or w_bilabial > 0:
                ph = np.load(f"{C.DATA}/mead_v2/phonemes/{actor}.npz")
                assert (ph["clip_ids"] == z["clip_ids"]).all(), actor
                arr["viseme"] = ph["viseme"]
            if aug_prob > 0:
                wa = np.load(f"{C.DATA}/mead_v2/wavlm_aug/{actor}.npz")
                assert (wa["clip_ids"] == z["clip_ids"]).all(), actor
                arr["hubert_aug"] = wa["wavlm"]
            if features == "wavlm":
                w = np.load(f"{C.DATA}/mead_v2/wavlm/{actor}.npz")
                assert (w["clip_ids"] == z["clip_ids"]).all() and (w["lengths"] == z["lengths"]).all(), actor
                arr["hubert"] = w["wavlm"]          # ClipSet reads the speech features from this key
                feature_config.update(json.loads(str(w["config"])))
                valid = w["valid"]
            elif only_valid_wavlm:
                # the same clips as a WavLM run, so the two can be compared fairly
                valid = np.load(f"{C.DATA}/mead_v2/wavlm/{actor}.npz")["valid"]
            else:
                valid = np.ones(len(z["clip_ids"]), bool)
            ends = np.cumsum(z["lengths"])
            for cid, emo, lv, s, e, ok in zip(z["clip_ids"].tolist(), z["emotions"].tolist(), z["levels"].tolist(),
                                              ends - z["lengths"], ends, valid):
                if not ok:      # no verified audio for this clip (WavLM features only)
                    continue
                store[cid] = (arr, int(s), int(e))
                rows.append({"clip_id": cid, "actor": actor, "emotion": emo, "level": int(lv), "split": split,
                             "features": cid})
        if max_clips:
            rows = rows[:: max(1, len(rows) // max_clips)]

        def loader(cid):
            arr, s, e = store[cid]
            return {k: v[s:e] for k, v in arr.items()}

        return ClipSet(rows, loader=loader, lookahead=lookahead)

    train_set, val_set = load_split("train", max_train_clips), load_split("val")
    print(f"train clips {len(train_set)}  val clips {len(val_set)}  gpu {torch.cuda.get_device_name(0)}")
    cfg = TrainConfig(steps=steps, separate_branches=separate_branches, w_velocity=w_velocity, seed=seed, lr=lr,
                      eval_every=eval_every, weight_decay=weight_decay, w_ccc=w_ccc, lookahead=lookahead,
                      w_vel_ccc=w_vel_ccc, w_closure=w_closure, w_viseme=w_viseme, w_bilabial=w_bilabial,
                      aug_prob=aug_prob,
                      model=BehaviourConfig(hidden=hidden, lip_cap=lip_cap, dropout=dropout,
                                            audio_dim=int(train_set.clips[0]["audio"].shape[1]), features=features,
                                            feature_config=feature_config or None,
                                            n_visemes=9 if w_viseme > 0 else 0))
    out_dir = f"{RUNS}/{run}"
    os.makedirs(out_dir, exist_ok=True)
    res = train(train_set, val_set, cfg, out_path=f"{out_dir}/model.pt")
    res.update({"run": run, "gpu": torch.cuda.get_device_name(0), "train_clips": len(train_set),
                "val_clips": len(val_set), "train_actors": sorted({c["actor"] for c in train_set.clips}),
                "val_actors": sorted({c["actor"] for c in val_set.clips})})
    # Rest poses of the *training* actors are not needed at inference (the portrait supplies its own).
    with open(f"{out_dir}/report.json", "w") as f:
        json.dump(res, f, indent=1)
    C.models_vol.commit()
    return res


@app.local_entrypoint()
def main(run: str = "base", steps: int = 12000, separate_branches: bool = True, lip_cap: float = 0.35,
         hidden: int = 256, w_velocity: float = 1.0, seed: int = 0, max_train_clips: int = 0,
         dropout: float = 0.1, lr: float = 1e-3, eval_every: int = 500, weight_decay: float = 1e-4,
         w_ccc: float = 0.0, lookahead: int = 0, w_vel_ccc: float = 0.0, w_closure: float = 0.0,
         features: str = "ditto_hubert", only_valid_wavlm: bool = False, w_viseme: float = 0.0,
         w_bilabial: float = 0.0, aug_prob: float = 0.0):
    res = train_run.remote(w_vel_ccc=w_vel_ccc, w_closure=w_closure, features=features,
                           only_valid_wavlm=only_valid_wavlm, w_viseme=w_viseme, w_bilabial=w_bilabial,
                           aug_prob=aug_prob, run=run, steps=steps, separate_branches=separate_branches, lip_cap=lip_cap,
                           hidden=hidden, w_velocity=w_velocity, seed=seed, max_train_clips=max_train_clips,
                           dropout=dropout, lr=lr, eval_every=eval_every, weight_decay=weight_decay,
                           w_ccc=w_ccc, lookahead=lookahead)
    res.pop("history", None)
    print(json.dumps(res, indent=1))
