"""Training loop and motion-space validation metrics for the behaviour model."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field

import numpy as np
import torch

from ..constants import EMOTIONS, EXP_DIM
from ..models.behaviour_net import MOTION_DIM, BehaviourConfig, BehaviourNet


@dataclass
class TrainConfig:
    steps: int = 12000
    batch_size: int = 64
    length: int = 125              # frames per training crop (5 s)
    lr: float = 1e-3
    weight_decay: float = 1e-4
    w_velocity: float = 1.0        # weight of the frame-difference term
    w_articulation: float = 1.0    # weight of the articulation-branch term
    separate_branches: bool = True  # train the emotion branch against a detached articulation branch
    w_ccc: float = 0.0             # weight of the concordance-correlation term (amplitude-preserving)
    lookahead: int = 0             # future feature frames given to the model
    w_vel_ccc: float = 0.0         # concordance of lip *velocities* (timing of openings and closings)
    w_closure: float = 0.0         # extra lip error weight on frames where the real mouth is closed
    w_viseme: float = 0.0          # phoneme supervision: cross-entropy of the articulation branch's viseme head
    w_bilabial: float = 0.0        # extra lip error on /p b m/ frames and the 2 frames before them
    aug_prob: float = 0.0          # chance of training a sample on degraded-audio features
    eval_every: int = 1000
    seed: int = 0
    model: BehaviourConfig = field(default_factory=BehaviourConfig)


def masked_l1(pred, target, mask, weight):
    """Mean absolute error over valid frames; ``weight`` is per output dimension."""
    err = (pred - target).abs() * weight
    m = mask.unsqueeze(-1)
    return (err * m).sum() / (m.sum() * weight.sum()).clamp_min(1e-8)


def ccc_loss(pred, target, mask, weight, eps: float = 1e-4, min_var: float = 0.05):
    """1 - concordance correlation coefficient, per clip and output dimension.

    L1 regression predicts the average of what is plausible, so motion comes out with the
    right timing but too little amplitude. The concordance coefficient
    2 cov / (var_p + var_t + (mean_p - mean_t)^2) is 1 only when the prediction matches
    the target in correlation, amplitude and offset, so maximising it keeps the amplitude
    of real motion. Dimensions that barely move in a clip are left out, so the term
    cannot amplify noise.
    """
    m = mask.unsqueeze(-1)
    n = m.sum(1).clamp_min(1.0)
    mp, mt = (pred * m).sum(1) / n, (target * m).sum(1) / n
    dp, dt = (pred - mp.unsqueeze(1)) * m, (target - mt.unsqueeze(1)) * m
    vp, vt = (dp ** 2).sum(1) / n, (dt ** 2).sum(1) / n
    cov = (dp * dt).sum(1) / n
    ccc = 2 * cov / (vp + vt + (mp - mt) ** 2 + eps)
    # (B, D): keep dimensions that really move in this clip (targets are standardised)
    active = ((vt > min_var) & (mask.sum(1, keepdim=True) >= 20)).float() * weight
    return ((1.0 - ccc) * active).sum() / active.sum().clamp_min(1e-8)


def lip_timing_terms(pred, target, mask, closed, weight, lip, w_vel_ccc: float, w_closure: float):
    """Two optional lip terms.

    * Velocity concordance: 1 - CCC of frame-to-frame lip changes. Position losses are
      satisfied by a prediction that is right on average but smeared in time; this term is
      only low when openings and closings happen at the same frames as in the real video.
    * Closure weighting: extra L1 on lip coordinates in frames where the real mouth is among
      the most closed of its clip (bilabial stops /p b m/, pauses), where a missed closure
      is most visible.
    """
    loss = pred.new_zeros(())
    lw = weight * lip
    if w_vel_ccc > 0:
        vm = mask[:, 1:] * mask[:, :-1]
        loss = loss + w_vel_ccc * ccc_loss(pred[:, 1:] - pred[:, :-1], target[:, 1:] - target[:, :-1], vm, lw,
                                           min_var=0.005)
    if w_closure > 0:
        loss = loss + w_closure * masked_l1(pred, target, mask * closed, lw)
    return loss


def motion_loss(pred, target, mask, weight, w_velocity, w_ccc: float = 0.0):
    loss = masked_l1(pred, target, mask, weight)
    if w_ccc > 0:
        loss = loss + w_ccc * ccc_loss(pred, target, mask, weight)
    if w_velocity > 0:
        vm = mask[:, 1:] * mask[:, :-1]
        loss = loss + w_velocity * masked_l1(pred[:, 1:] - pred[:, :-1], target[:, 1:] - target[:, :-1], vm, weight)
    return loss


@torch.no_grad()
def evaluate(net: BehaviourNet, clips: list[dict], device: str, chunk: int = 0) -> dict:
    """Motion-space metrics on whole clips, processed as a stream.

    * ``lip_mae``      mean absolute error on lip-keypoint coordinates (renderer units)
    * ``lip_corr``     Pearson correlation of predicted and real lip motion, averaged over
                       the lip coordinates that actually move
    * ``lip_energy``   mean |frame difference| of the prediction divided by the real one;
                       1.0 means the mouth is as lively as the real one, lower means muted
    * ``pose_mae_deg`` head rotation error
    * ``offset_cos``   per emotion: cosine similarity between the predicted and the real
                       mean expression offset from neutral (full-intensity clips)
    """
    net.eval()
    lip = net.lip_mask.bool().cpu().numpy()
    mae, corr, e_pred, e_gt, pose = [], [], [], [], []
    amp_p, amp_g, pose_p, pose_g, upper_p, upper_g = [], [], [], [], [], []
    upper = ~(net.lip_mask.bool().cpu().numpy())
    off_pred = {e: [] for e in EMOTIONS[1:]}
    off_gt = {e: [] for e in EMOTIONS[1:]}
    for c in clips:
        a = torch.from_numpy(c["audio"].astype(np.float32))[None].to(device)
        e = torch.from_numpy(c["emo"])[None, None].expand(1, a.shape[1], -1).to(device)
        if chunk:
            outs, state = [], None
            for i in range(0, a.shape[1], chunk):
                o, state = net(a[:, i:i + chunk], e[:, i:i + chunk], state)
                outs.append(o)
            p = torch.cat(outs, 1)[0].cpu().numpy()
        else:
            p = net(a, e)[0][0].cpu().numpy()
        y = c["y"]
        pl, yl = p[:, :EXP_DIM][:, lip], y[:, :EXP_DIM][:, lip]
        mae.append(np.abs(pl - yl).mean())
        moving = yl.std(0) > 0.5 * yl.std(0).max()
        if moving.any() and len(yl) > 5:
            cc = [np.corrcoef(pl[:, j], yl[:, j])[0, 1] for j in np.where(moving)[0] if pl[:, j].std() > 1e-8]
            if cc:
                corr.append(float(np.mean(cc)))
        if moving.any():
            amp_p.append(pl[:, moving].std(0).mean())
            amp_g.append(yl[:, moving].std(0).mean())
        pose_p.append(p[:, EXP_DIM:EXP_DIM + 3].std(0))
        pose_g.append(y[:, EXP_DIM:EXP_DIM + 3].std(0))
        upper_p.append(p[:, :EXP_DIM][:, upper].std(0).mean())
        upper_g.append(y[:, :EXP_DIM][:, upper].std(0).mean())
        e_pred.append(np.abs(np.diff(pl, axis=0)).mean())
        e_gt.append(np.abs(np.diff(yl, axis=0)).mean())
        pose.append(np.abs(p[:, EXP_DIM:EXP_DIM + 3] - y[:, EXP_DIM:EXP_DIM + 3]).mean())
        if c["emotion"] != "neutral" and c["level"] == 3:
            off_pred[c["emotion"]].append(p[:, :EXP_DIM].mean(0))
            off_gt[c["emotion"]].append(y[:, :EXP_DIM].mean(0))
    out = {"lip_mae": float(np.mean(mae)), "lip_corr": float(np.mean(corr)) if corr else float("nan"),
           "lip_energy": float(np.sum(e_pred) / max(np.sum(e_gt), 1e-12)), "pose_mae_deg": float(np.mean(pose)),
           "lip_amp": float(np.sum(amp_p) / max(np.sum(amp_g), 1e-12)),
           "upper_amp": float(np.sum(upper_p) / max(np.sum(upper_g), 1e-12)),
           "pose_std_deg": [round(float(v), 3) for v in np.mean(pose_p, 0)],
           "pose_std_deg_real": [round(float(v), 3) for v in np.mean(pose_g, 0)],
           "offset_cos": {}}
    for emo in off_pred:
        if off_pred[emo]:
            u, v = np.mean(off_pred[emo], 0), np.mean(off_gt[emo], 0)
            out["offset_cos"][emo] = float(u @ v / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-12))
    net.train()
    return out


def train(train_set, val_set, cfg: TrainConfig, device: str = "cuda", log=print, out_path: str | None = None) -> dict:
    torch.manual_seed(cfg.seed)
    rng = np.random.default_rng(cfg.seed)
    cfg.model.lookahead = cfg.lookahead
    assert train_set.lookahead == cfg.lookahead == val_set.lookahead, "datasets must share the look-ahead"
    net = BehaviourNet(cfg.model).to(device)
    std = torch.from_numpy(train_set.stats()).to(device)
    net.out_scale.copy_(std)
    # Dimensions that vary more get more weight, within a 10x range.
    weight = (std / std.median()).clamp(0.3, 3.0)
    weight[EXP_DIM:] = 1.0
    net.lip_mask_full = torch.cat([net.lip_mask, torch.zeros(MOTION_DIM - EXP_DIM, device=device)])
    opt = torch.optim.AdamW(net.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.lr, total_steps=cfg.steps, pct_start=0.05)
    history, best, t0 = [], None, time.perf_counter()
    net.train()
    for step in range(1, cfg.steps + 1):
        audio, emo, y, y_art, mask, closed, vis = (torch.from_numpy(x).to(device) for x in
                                                   train_set.batch(rng, cfg.batch_size, cfg.length, cfg.aug_prob))
        _, _, parts = net(audio, emo, return_parts=True)
        art, emo_part = parts["art"] / std, parts["emo"] / std
        if cfg.separate_branches:
            full = art.detach() + emo_part
            loss_art = motion_loss(art, y_art / std, mask, weight, cfg.w_velocity, cfg.w_ccc)
            loss_art = loss_art + lip_timing_terms(art, y_art / std, mask, closed, weight, net.lip_mask_full,
                                                   cfg.w_vel_ccc, cfg.w_closure)
            if cfg.w_bilabial > 0:
                # lips close before the acoustic release: include the 2 frames before each /p b m/ frame
                bil = (vis == 1).float()
                ant = torch.maximum(bil, torch.nn.functional.pad(bil[:, 2:], (0, 2)))
                ant = torch.maximum(ant, torch.nn.functional.pad(bil[:, 1:], (0, 1)))
                loss_art = loss_art + cfg.w_bilabial * masked_l1(art, y_art / std, mask * ant,
                                                                 weight * net.lip_mask_full)
            if cfg.w_viseme > 0 and "vis_logits" in parts:
                lab = torch.where(mask > 0, vis, torch.full_like(vis, -1))
                loss_art = loss_art + cfg.w_viseme * torch.nn.functional.cross_entropy(
                    parts["vis_logits"].reshape(-1, parts["vis_logits"].shape[-1]), lab.reshape(-1), ignore_index=-1)
        else:
            full = art + emo_part
            loss_art = torch.zeros((), device=device)
        loss_full = motion_loss(full, y / std, mask, weight, cfg.w_velocity, cfg.w_ccc)
        loss = loss_full + cfg.w_articulation * loss_art
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        opt.step()
        sched.step()
        if step % cfg.eval_every == 0 or step == cfg.steps:
            m = evaluate(net, val_set.clips, device)
            m.update({"step": step, "loss_full": float(loss_full), "loss_art": float(loss_art),
                      "minutes": round((time.perf_counter() - t0) / 60, 2)})
            history.append(m)
            # Selection score: lip-motion correlation plus emotion-offset agreement, both on
            # validation actors. (Lip MAE alone picks an early, emotion-poor checkpoint.)
            cos = list(m["offset_cos"].values())
            m["score"] = float(m["lip_corr"] + 0.5 * (sum(cos) / len(cos) if cos else 0.0))
            log(json.dumps({k: (round(v, 5) if isinstance(v, float) else v) for k, v in m.items()}))
            if best is None or m["score"] > best["score"]:
                best = m
                if out_path:
                    torch.save({**net.export(), "train_config": asdict(cfg), "val": m,
                                "gate": net.emotion_gate().detach().cpu().numpy()}, out_path)
    # chunked streaming must match whole-clip processing
    net.eval()
    with torch.no_grad():
        c = val_set.clips[0]
        a = torch.from_numpy(c["audio"].astype(np.float32))[None].to(device)
        e = torch.from_numpy(c["emo"])[None, None].expand(1, a.shape[1], -1).to(device)
        whole = net(a, e)[0]
        diffs = {}
        for k in (1, 5, 10):
            outs, state = [], None
            for i in range(0, a.shape[1], k):
                o, state = net(a[:, i:i + k], e[:, i:i + k], state)
                outs.append(o)
            diffs[k] = float((torch.cat(outs, 1) - whole).abs().max())
    return {"best": best, "history": history, "parameters": net.n_parameters(), "chunk_max_abs_diff": diffs,
            "minutes": round((time.perf_counter() - t0) / 60, 2)}
