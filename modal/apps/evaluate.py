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
             intensity: float = 1.0, size: int = 512, force_emotion: str = "") -> dict:
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

            return EmoStreamBehaviour(runtime, av, timeline, net, exp_gain=exp_gain, pose_gain=pose_gain)
        if behaviour == "ditto_full":
            from emostream.engine.behaviour_emostream import DittoFullFace

            return DittoFullFace(runtime, av, timeline, sampling_timesteps=steps, valid_frames=valid_frames)
        return DittoBehaviour(runtime, av, timeline, sampling_timesteps=steps, valid_frames=valid_frames)

    clips = eval_subset(split, per_cell)
    out_dir = f"{C.DATA}/eval_out/{tag}"
    os.makedirs(out_dir, exist_ok=True)
    avatars, meta, t0 = {}, [], time.perf_counter()
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
        sess = AvatarSession(rt, avatars[actor], factory, emotion=emotion,
                             intensity=1.0 if emotion == "neutral" else intensity * r["level"] / 3, size=size,
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
            "force_emotion": force_emotion,
            "ms_per_frame": {k: round(1000 * v / max(n_frames, 1), 2) for k, v in stage_tot.items()}}
    with open(f"{out_dir}/meta.json", "w") as f:
        json.dump({"info": info, "clips": meta}, f, indent=1)
    C.data_vol.commit()
    return info


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
            y_true.append(it["emotion"])
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
        exp_gain: float = 1.0, pose_gain: float = 1.0, force_emotion: str = "", then_score: bool = True):
    print(json.dumps(generate.remote(tag=tag, behaviour=behaviour, run=run, split=split, per_cell=per_cell,
                                     exp_gain=exp_gain, pose_gain=pose_gain, force_emotion=force_emotion), indent=1))
    if then_score:
        print(json.dumps(score.remote(tag=tag, split=split, per_cell=per_cell), indent=1))


@app.local_entrypoint()
def sc(tag: str, split: str = "val", per_cell: int = 4):
    print(json.dumps(score.remote(tag=tag, split=split, per_cell=per_cell), indent=1))
