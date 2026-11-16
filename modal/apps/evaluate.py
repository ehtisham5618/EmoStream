"""Evaluation on held-out MEAD actors: generate with a behaviour model, then score.

Stage 1 ``generate``: for a fixed subset of clips of a split, animate the actor's neutral
portrait with the clip's own audio and emotion label -> ``/data/eval_out/<tag>/``.

Stage 2 ``score``: on a folder of videos (generated, or the ground-truth crops):
  * SyncNet LSE-C / LSE-D   joonson/syncnet_python with the Wav2Lip scoring scripts
  * Emotion                 HSEmotion (enet_b2_8, AffectNet) on face frames, clip-level
                            majority over mean probabilities, restricted to our 5 classes;
                            macro-F1 and confusion matrix against the MEAD label
  * Identity                ArcFace (InsightFace buffalo_l) cosine similarity between the
                            portrait and sampled frames

The emotion classifier is first scored on the real MEAD crops of the same clips: that
number is its own accuracy on this data and the ceiling for any generated result.

    modal run modal/apps/evaluate.py::gen --behaviour ditto --tag val_ditto
    modal run modal/apps/evaluate.py::gen --behaviour emostream --run base --tag val_emostream_base
    modal run modal/apps/evaluate.py::sc --tag val_ditto
    modal run modal/apps/evaluate.py::sc --tag gt        # ground-truth reference
"""
from __future__ import annotations

import json

import modal

import _common as C

app = modal.App("emostream-v2-evaluate")
gen_image = C.engine_image()

SYNC = "/opt/syncnet_python"
score_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "git", "wget", "libgl1", "libglib2.0-0", "build-essential")
    .pip_install("torch==2.0.1", "torchvision==0.15.2", index_url="https://download.pytorch.org/whl/cu118")
    .pip_install("numpy==1.23.5", "scipy==1.10.1", "scenedetect==0.6.4", "opencv-contrib-python-headless==4.8.1.78",
                 "python_speech_features", "tqdm", "onnxruntime-gpu==1.16.3", "insightface==0.7.3",
                 "hsemotion-onnx==0.3.1", "scikit-learn==1.3.2", "imageio==2.33.0", "imageio-ffmpeg==0.4.9")
    .run_commands(
        f"git clone https://github.com/joonson/syncnet_python {SYNC}",
        "git clone --depth 1 https://github.com/Rudrabha/Wav2Lip /opt/Wav2Lip",
        f"cp /opt/Wav2Lip/evaluation/scores_LSE/*.py {SYNC}/",
        f"mkdir -p {SYNC}/data {SYNC}/detectors/s3fd/weights",
        f"wget -q http://www.robots.ox.ac.uk/~vgg/software/lipsync/data/syncnet_v2.model -O {SYNC}/data/syncnet_v2.model",
        f"wget -q https://www.robots.ox.ac.uk/~vgg/software/lipsync/data/sfd_face.pth -O {SYNC}/detectors/s3fd/weights/sfd_face.pth",
    )
    .add_local_file(str(C.ROOT / "modal" / "apps" / "_common.py"), "/root/_common.py")
    .add_local_dir(str(C.ROOT / "emostream"), "/root/emostream")
)

EMOS = ["neutral", "happy", "sad", "angry", "surprised"]
HSE = {"Anger": "angry", "Happiness": "happy", "Neutral": "neutral", "Sadness": "sad", "Surprise": "surprised"}


def eval_subset(split: str, per_cell: int, levels=(3,)) -> list[dict]:
    """Deterministic subset: for each actor and emotion, the first ``per_cell`` clips
    (by clip number) at the given levels; neutral has a single level."""
    rows = [json.loads(line) for line in open(f"{C.DATA}/mead_v2/manifests/clips.jsonl")]
    rows = [r for r in rows if r["valid"] and r["split"] == split]
    out = []
    for actor in sorted({r["actor"] for r in rows}):
        for emo in EMOS:
            lv = (1,) if emo == "neutral" else levels
            cell = sorted([r for r in rows if r["actor"] == actor and r["emotion"] == emo and r["level"] in lv],
                          key=lambda r: (r["level"], r["clip_id"]))
            # skip the first clips: clip 001 supplies the portrait, and the engine-bench audio uses others
            out += cell[8:8 + per_cell] if len(cell) >= 8 + per_cell else cell[-per_cell:]
    return out


@app.function(image=gen_image, gpu=["A10G", "L4", "T4"], timeout=3 * 3600,
              volumes={C.MODELS: C.models_vol, C.DATA: C.data_vol})
def generate(tag: str, behaviour: str = "ditto", run: str = "base", split: str = "val", per_cell: int = 4,
             steps: int = 10, valid_frames: int = 10, exp_gain: float = 1.0, pose_gain: float = 1.0,
             intensity: float = 1.0, size: int = 512, force_emotion: str = "", hop: int = 5,
             emotions: str = "", levels: str = "3", emotion_gain: float = 1.0, force_emotions: str = "") -> dict:
    import os
    import subprocess
    import time

    import imageio
    import numpy as np
    import soundfile as sf
    import torch

    from emostream.engine.behaviour import DittoBehaviour
    from emostream.engine.runtime import Runtime
    from emostream.engine.session import AvatarSession, stream_file

    assert split != "test" or tag.startswith("test_"), "test split is reserved for the final report"
    assert not (behaviour == "oracle" and split == "test"), "the oracle reads real motion; never on the test split"
    os.chdir(C.REPO)
    rt = Runtime(C.ensure_checkpoints())
    net = None
    if behaviour == "emostream":
        from emostream.models import BehaviourNet

        net = BehaviourNet.load(torch.load(f"{C.MODELS}/emostream/{run}/model.pt", map_location="cpu",
                                           weights_only=False))

    def factory(runtime, av, timeline):
        if behaviour == "emostream":
            from emostream.engine.behaviour_emostream import EmoStreamBehaviour

            return EmoStreamBehaviour(runtime, av, timeline, net, exp_gain=exp_gain, pose_gain=pose_gain, hop=hop,
                                      emotion_gain=emotion_gain)
        if behaviour == "ditto_full":
            from emostream.engine.behaviour_emostream import DittoFullFace

            return DittoFullFace(runtime, av, timeline, sampling_timesteps=steps, valid_frames=valid_frames)
        return DittoBehaviour(runtime, av, timeline, sampling_timesteps=steps, valid_frames=valid_frames)

    oracle = {}

    def oracle_deltas(r):
        """Real motion of this clip as deltas from the actor's rest pose (renderer check)."""
        from emostream.training.data import to_delta

        actor = r["actor"]
        if actor not in oracle:
            z = np.load(f"{C.DATA}/mead_v2/packed/{actor}.npz")
            ends = np.cumsum(z["lengths"])
            mot = np.concatenate([z["exp"], z["pose"], z["t"][:, :2], z["scale"].reshape(-1, 1)], 1).astype(np.float32)
            neutral = [i for i, e in enumerate(z["emotions"]) if e == "neutral"]
            rest = np.median(np.concatenate([mot[ends[i] - z["lengths"][i]:ends[i] - z["lengths"][i] + 3]
                                             for i in neutral]), 0)
            oracle[actor] = (z["clip_ids"].tolist(), ends, z["lengths"], mot, rest)
        ids, ends, lengths, mot, rest = oracle[actor]
        i = ids.index(r["clip_id"])
        return to_delta(mot[ends[i] - lengths[i]:ends[i]].copy(), rest)

    clips = eval_subset(split, per_cell, tuple(int(x) for x in levels.split(",")))
    if emotions:  # restrict the *audio* emotion, e.g. for cross-conditioning runs
        clips = [c for c in clips if c["emotion"] in emotions.split(",")]
    avatars = {}
    base_tag, results = tag, []
    selections = [e for e in force_emotions.split(",") if e] or [force_emotion]
    for force_emotion in selections:
      tag = f"{base_tag}_{force_emotion}" if force_emotions else base_tag
      out_dir = f"{C.DATA}/eval_out/{tag}"
      os.makedirs(out_dir, exist_ok=True)
      meta, t0 = [], time.perf_counter()
      stage_tot, n_frames = {}, 0
      for r in clips:
            actor = r["actor"]
            if actor not in avatars:
                avatars[actor] = rt.register(f"{C.DATA}/eval/{split}/{actor}/portrait.png")
            gt = f"{C.DATA}/mead_v2/gt256/{actor}/{r['clip_id']}.mp4"
            wav = f"/tmp/{r['clip_id']}.wav"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", gt, "-vn", "-ac", "1", "-ar", "16000", wav],
                           check=True)
            audio, _ = sf.read(wav, dtype="float32")
            emotion = force_emotion or r["emotion"]
            fac = factory
            if behaviour == "oracle":
                from emostream.engine.behaviour_emostream import OracleBehaviour

                deltas = oracle_deltas(r)
                fac = lambda runtime, av, timeline: OracleBehaviour(runtime, av, timeline, deltas)  # noqa: E731
            sess = AvatarSession(rt, avatars[actor], fac, emotion=emotion,
                                 intensity=(1.0 if emotion == "neutral" else intensity if force_emotion
                                            else intensity * r["level"] / 3), size=size,
                                 portrait_consent=True, audio_consent=True)
            tmp = f"/tmp/{r['clip_id']}.mp4"
            w = imageio.get_writer(tmp, fps=25, codec="libx264", quality=8, macro_block_size=1)
            for fr in stream_file(sess, audio, chunk_ms=200, paced=False):
                w.append_data(fr.rgb)
            w.close()
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", tmp, "-i", wav, "-map", "0:v", "-map", "1:a",
                            "-c:v", "copy", "-c:a", "aac", "-shortest", f"{out_dir}/{r['clip_id']}.mp4"], check=True)
            os.remove(tmp)
            os.remove(wav)
            st = sess.stats()
            n_frames += st["frames"]
            for k, v in st["stages"].items():
                stage_tot[k] = stage_tot.get(k, 0.0) + v["total_s"]
            deltas = getattr(sess.behaviour, "last_deltas", None)
            if deltas:
                np.save(f"{out_dir}/{r['clip_id']}.motion.npy", np.stack(deltas).astype(np.float32))
            meta.append({"clip_id": r["clip_id"], "actor": actor, "emotion": r["emotion"], "level": r["level"],
                         "condition": emotion, "frames": st["frames"]})
      info = {"tag": tag, "behaviour": behaviour, "run": run if behaviour == "emostream" else None, "split": split,
              "gpu": torch.cuda.get_device_name(0), "clips": len(meta), "frames": n_frames,
              "minutes": round((time.perf_counter() - t0) / 60, 2), "exp_gain": exp_gain, "pose_gain": pose_gain,
              "force_emotion": force_emotion, "hop": hop, "intensity": intensity, "emotion_gain": emotion_gain,
              "ms_per_frame": {k: round(1000 * v / max(n_frames, 1), 2) for k, v in stage_tot.items()}}
      with open(f"{out_dir}/meta.json", "w") as f:
          json.dump({"info": info, "clips": meta}, f, indent=1)
      results.append(info)
    C.data_vol.commit()
    return results[0] if len(results) == 1 else {"runs": results}


@app.function(image=score_image, gpu=["T4", "L4", "A10G"], timeout=3 * 3600, volumes={C.DATA: C.data_vol}, cpu=4)
def score(tag: str, split: str = "val", per_cell: int = 4, do_sync: bool = True) -> dict:
    import os
    import shutil
    import subprocess

    import cv2
    import numpy as np
    from sklearn.metrics import confusion_matrix, f1_score

    C.data_vol.reload()
    if tag == "gt":
        clips = eval_subset(split, per_cell)
        items = [{"clip_id": r["clip_id"], "actor": r["actor"], "emotion": r["emotion"], "level": r["level"],
                  "video": f"{C.DATA}/mead_v2/gt256/{r['actor']}/{r['clip_id']}.mp4"} for r in clips]
        out_dir = f"{C.DATA}/eval_out/gt_{split}"
        os.makedirs(out_dir, exist_ok=True)
    else:
        out_dir = f"{C.DATA}/eval_out/{tag}"
        meta = json.load(open(f"{out_dir}/meta.json"))
        items = [{**m, "video": f"{out_dir}/{m['clip_id']}.mp4"} for m in meta["clips"]]

    # ---- emotion + identity (frame sampling) ----------------------------------------------
    from hsemotion_onnx.facial_emotions import HSEmotionRecognizer
    from insightface.app import FaceAnalysis

    fer = HSEmotionRecognizer(model_name="enet_b2_8")
    classes = [fer.idx_to_class[i] for i in range(len(fer.idx_to_class))]
    keep = [i for i, c in enumerate(classes) if c in HSE]
    keep_names = [HSE[classes[i]] for i in keep]
    fa = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
                      allowed_modules=["detection", "recognition"])
    fa.prepare(ctx_id=0, det_size=(320, 320))

    def embed(img_bgr):
        faces = fa.get(img_bgr)
        if not faces:
            return None, None
        f = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
        return f.normed_embedding, f.bbox.astype(int)

    ref = {}
    for actor in sorted({i["actor"] for i in items}):
        img = cv2.imread(f"{C.DATA}/eval/{split}/{actor}/portrait.png")
        ref[actor], _ = embed(img)

    y_true, y_pred, ids, per_clip = [], [], [], []
    for it in items:
        cap = cv2.VideoCapture(it["video"])
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        probs, sims = [], []
        for k in np.linspace(0, max(n - 1, 0), num=min(n, 12)).astype(int):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(k))
            ok, frame = cap.read()
            if not ok:
                continue
            emb, box = embed(frame)
            if emb is None:
                continue
            if ref[it["actor"]] is not None:
                sims.append(float(emb @ ref[it["actor"]]))
            x0, y0, x1, y1 = [max(0, v) for v in box]
            face = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)
            if face.size == 0:
                continue
            _, scores = fer.predict_emotions(face, logits=False)
            probs.append(np.asarray(scores)[keep])
        cap.release()
        row = {"clip_id": it["clip_id"], "emotion": it["emotion"], "level": it["level"]}
        if probs:
            p = np.mean(probs, 0)
            row["pred"] = keep_names[int(np.argmax(p))]
            row["probs"] = {k: round(float(v / p.sum()), 4) for k, v in zip(keep_names, p)}
            y_true.append(it.get("condition") or it["emotion"])   # the selected emotion is the label
            y_pred.append(row["pred"])
        if sims:
            row["arcface"] = float(np.mean(sims))
            ids.append(row["arcface"])
        per_clip.append(row)

    res = {"tag": tag, "n_clips": len(items),
           "emotion": {"n": len(y_true), "macro_f1": float(f1_score(y_true, y_pred, labels=EMOS, average="macro")),
                       "accuracy": float(np.mean([a == b for a, b in zip(y_true, y_pred)])),
                       "labels": EMOS, "confusion": confusion_matrix(y_true, y_pred, labels=EMOS).tolist(),
                       "per_class_f1": dict(zip(EMOS, f1_score(y_true, y_pred, labels=EMOS, average=None).tolist()))},
           "identity": {"n": len(ids), "arcface_mean": float(np.mean(ids)) if ids else None,
                        "arcface_min": float(np.min(ids)) if ids else None}}

    # ---- SyncNet ---------------------------------------------------------------------------
    if do_sync:
        lse_c, lse_d, failed = [], [], 0
        for it, row in zip(items, per_clip):
            work = f"/tmp/sync/{it['clip_id']}"
            shutil.rmtree(work, ignore_errors=True)
            os.makedirs(work, exist_ok=True)
            a = subprocess.run(["python", "run_pipeline.py", "--videofile", it["video"], "--reference", "x",
                                "--data_dir", work], cwd=SYNC, capture_output=True, text=True)
            b = subprocess.run(["python", "calculate_scores_real_videos.py", "--videofile", it["video"],
                                "--reference", "x", "--data_dir", work], cwd=SYNC, capture_output=True, text=True)
            shutil.rmtree(work, ignore_errors=True)
            try:
                dist, conf = [float(v) for v in b.stdout.strip().splitlines()[-1].split()[:2]]
                lse_d.append(dist)
                lse_c.append(conf)
                row["lse_d"], row["lse_c"] = dist, conf
            except Exception:  # noqa: BLE001
                failed += 1
                row["sync_error"] = (b.stderr or a.stderr)[-200:]
        res["sync"] = {"n": len(lse_c), "failed": failed, "lse_c": float(np.mean(lse_c)) if lse_c else None,
                       "lse_d": float(np.mean(lse_d)) if lse_d else None,
                       "lse_c_std": float(np.std(lse_c)) if lse_c else None}
    res["per_clip"] = per_clip
    with open(f"{out_dir}/scores.json", "w") as f:
        json.dump(res, f, indent=1)
    C.data_vol.commit()
    return {k: v for k, v in res.items() if k != "per_clip"}


@app.local_entrypoint()
def gen(tag: str, behaviour: str = "ditto", run: str = "base", split: str = "val", per_cell: int = 4,
        exp_gain: float = 1.0, pose_gain: float = 1.0, force_emotion: str = "", then_score: bool = True,
        hop: int = 5, intensity: float = 1.0, emotions: str = "", levels: str = "3", sync: bool = False,
        mouth: bool = True, emotion_gain: float = 1.0, force_emotions: str = ""):
    print(json.dumps(generate.remote(tag=tag, behaviour=behaviour, run=run, split=split, per_cell=per_cell,
                                     exp_gain=exp_gain, pose_gain=pose_gain, force_emotion=force_emotion, hop=hop,
                                     intensity=intensity, emotions=emotions, levels=levels,
                                     emotion_gain=emotion_gain, force_emotions=force_emotions), indent=1))
    if force_emotions:      # cross-conditioning: score emotion and identity for each selection
        for e in force_emotions.split(","):
            r = score.remote(tag=f"{tag}_{e}", split=split, per_cell=per_cell, do_sync=False)
            print(json.dumps(r, indent=1))
        return
    if then_score:
        print(json.dumps(score.remote(tag=tag, split=split, per_cell=per_cell, do_sync=sync), indent=1))
        if mouth:
            print(json.dumps(mouth_metrics.remote(tag=tag, split=split, per_cell=per_cell), indent=1))


def _mouth_series(video: str, fa) -> dict:
    """Per-frame mouth and jaw measurements from 106-point landmarks, normalised by the
    distance between the eye centres so they are comparable across crops and sizes.

    * ``open``  vertical extent of the mouth landmarks (lip aperture including lip thickness)
    * ``width`` horizontal extent of the mouth landmarks
    * ``jaw``   chin height below the eye line
    """
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(video)
    face, out = None, {"open": [], "width": [], "jaw": []}
    lm_model = fa.models["landmark_2d_106"]
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if face is None:
            faces = fa.get(frame)
            if not faces:
                for k in out:
                    out[k].append(np.nan)
                continue
            face = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
        lm = lm_model.get(frame, face)                      # (106, 2), same face box for the whole clip
        mouth = lm[52:72]
        eyes = np.linalg.norm(lm[33:43].mean(0) - lm[87:97].mean(0)) + 1e-6
        eye_y = (lm[33:43].mean(0)[1] + lm[87:97].mean(0)[1]) / 2
        out["open"].append((mouth[:, 1].max() - mouth[:, 1].min()) / eyes)
        out["width"].append((mouth[:, 0].max() - mouth[:, 0].min()) / eyes)
        out["jaw"].append((lm[0:33, 1].max() - eye_y) / eyes)
    cap.release()
    return {k: np.asarray(v, dtype=np.float32) for k, v in out.items()}


@app.function(image=score_image, gpu=["T4", "L4", "A10G"], timeout=2 * 3600, volumes={C.DATA: C.data_vol}, cpu=4)
def mouth_metrics(tag: str, split: str = "val", per_cell: int = 4) -> dict:
    """Mouth aperture, mouth width and jaw displacement of generated clips against the
    ground-truth video of the same clip: correlation over time and amplitude ratio."""
    import os

    import numpy as np
    from insightface.app import FaceAnalysis

    C.data_vol.reload()
    fa = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
                      allowed_modules=["detection", "landmark_2d_106"])
    fa.prepare(ctx_id=0, det_size=(320, 320))
    gt_dir = f"{C.DATA}/eval_out/gt_{split}/mouth"
    os.makedirs(gt_dir, exist_ok=True)

    def gt_series(r):
        path = f"{gt_dir}/{r['clip_id']}.npz"
        if not os.path.exists(path):
            np.savez(path, **_mouth_series(f"{C.DATA}/mead_v2/gt256/{r['actor']}/{r['clip_id']}.mp4", fa))
        return dict(np.load(path))

    if tag == "gt":
        clips = eval_subset(split, per_cell)
        for r in clips:
            gt_series(r)
        C.data_vol.commit()
        return {"tag": "gt", "clips": len(clips)}

    out_dir = f"{C.DATA}/eval_out/{tag}"
    meta = json.load(open(f"{out_dir}/meta.json"))
    rows, agg = [], {k: {"corr": [], "sp": [], "sg": [], "rp": [], "rg": []} for k in ("open", "width", "jaw")}
    for m in meta["clips"]:
        g = gt_series(m)
        p = _mouth_series(f"{out_dir}/{m['clip_id']}.mp4", fa)
        row = {"clip_id": m["clip_id"], "emotion": m["emotion"]}
        for k in agg:
            n = min(len(g[k]), len(p[k]))
            a, b = g[k][:n], p[k][:n]
            ok = np.isfinite(a) & np.isfinite(b)
            if ok.sum() < 20:
                continue
            a, b = a[ok], b[ok]
            c = float(np.corrcoef(a, b)[0, 1]) if a.std() > 1e-6 and b.std() > 1e-6 else float("nan")
            agg[k]["corr"].append(c)
            agg[k]["sp"].append(b.std())
            agg[k]["sg"].append(a.std())
            agg[k]["rp"].append(np.percentile(b, 95) - np.percentile(b, 5))
            agg[k]["rg"].append(np.percentile(a, 95) - np.percentile(a, 5))
            row[k] = {"corr": c, "amp": float(b.std() / (a.std() + 1e-9))}
        rows.append(row)
    res = {"tag": tag, "clips": len(rows)}
    for k, v in agg.items():
        res[k] = {"corr": round(float(np.nanmean(v["corr"])), 3),
                  "amplitude_ratio": round(float(np.sum(v["sp"]) / np.sum(v["sg"])), 3),
                  "range_ratio": round(float(np.sum(v["rp"]) / np.sum(v["rg"])), 3)}
    with open(f"{out_dir}/mouth.json", "w") as f:
        json.dump({**res, "per_clip": rows}, f, indent=1)
    C.data_vol.commit()
    return res


@app.function(image=score_image, gpu=["T4", "L4", "A10G"], timeout=3600, volumes={C.DATA: C.data_vol}, cpu=4)
def av_offsets(split: str = "val", max_clips: int = 24) -> dict:
    """SyncNet's own audio-video offset estimate on ground-truth clips (frames; the sign
    convention is SyncNet's). A consistent non-zero offset would mean the recordings
    themselves are out of sync, which would cap what any model trained on them can learn."""
    import os
    import re
    import shutil
    import subprocess
    from collections import Counter, defaultdict

    C.data_vol.reload()
    rows = [json.loads(line) for line in open(f"{C.DATA}/mead_v2/manifests/clips.jsonl")]
    rows = [r for r in rows if r["valid"] and r["split"] == split and r["duration_s"] >= 4.5]
    by = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["clip_id"]):
        by[r["actor"]].append(r)
    picks = [r for a in sorted(by) for r in by[a][:: max(1, len(by[a]) // (max_clips // len(by)))][: max_clips // len(by)]]
    per_actor, out = defaultdict(list), []
    for r in picks:
        work = f"/tmp/off/{r['clip_id']}"
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work, exist_ok=True)
        video = f"{C.DATA}/mead_v2/gt256/{r['actor']}/{r['clip_id']}.mp4"
        subprocess.run(["python", "run_pipeline.py", "--videofile", video, "--reference", "x", "--data_dir", work],
                       cwd=SYNC, capture_output=True, text=True)
        b = subprocess.run(["python", "run_syncnet.py", "--videofile", video, "--reference", "x", "--data_dir", work],
                           cwd=SYNC, capture_output=True, text=True)
        shutil.rmtree(work, ignore_errors=True)
        text = b.stdout + b.stderr          # SyncNet reports through the logging module (stderr)
        m = re.search(r"AV offset:\s*(-?\d+)", text)
        c = re.search(r"Confidence:\s*([\d.]+)", text)
        if m:
            off = int(m.group(1))
            per_actor[r["actor"]].append(off)
            out.append({"clip_id": r["clip_id"], "offset": off, "confidence": float(c.group(1)) if c else None})
        else:
            out.append({"clip_id": r["clip_id"], "offset": None, "debug": (b.stdout[-300:] + " | " + b.stderr[-400:])})
    res = {"split": split, "clips": len(out), "offset_histogram": dict(sorted(Counter(o["offset"] for o in out if o["offset"] is not None).items())),
           "picked": len(picks), "first_debug": next((o.get("debug") for o in out if o.get("debug")), None),
           "per_actor": {a: v for a, v in per_actor.items()}, "per_clip": out}
    os.makedirs(f"{C.DATA}/eval_out/gt_{split}", exist_ok=True)
    with open(f"{C.DATA}/eval_out/gt_{split}/av_offsets.json", "w") as f:
        json.dump(res, f, indent=1)
    C.data_vol.commit()
    return {k: v for k, v in res.items() if k != "per_clip"}


@app.local_entrypoint()
def sc(tag: str, split: str = "val", per_cell: int = 4, sync: bool = True):
    print(json.dumps(score.remote(tag=tag, split=split, per_cell=per_cell, do_sync=sync), indent=1))


@app.local_entrypoint()
def mouth(tag: str, split: str = "val", per_cell: int = 4):
    print(json.dumps(mouth_metrics.remote(tag=tag, split=split, per_cell=per_cell), indent=1))


@app.local_entrypoint()
def offsets(split: str = "val", max_clips: int = 24):
    assert split != "test", "the test split is reserved"
    print(json.dumps(av_offsets.remote(split=split, max_clips=max_clips), indent=1))
