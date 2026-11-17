"""Phoneme timing and per-frame mouth landmarks for the validation evaluation clips.

1. ``align``: for each evaluation clip (validation actors only), the audio of the real video
   (gt256 crop, i.e. the video's own sound track) is transcribed with Whisper large-v3, the
   transcript is converted to IPA phonemes with espeak-ng (``phonemizer``), and the phonemes
   are force-aligned to the audio with the CTC phoneme recogniser
   ``facebook/wav2vec2-lv-60-espeak-cv-ft`` (20 ms resolution). Saved per clip as JSON:
   transcript, Whisper confidence, word list, phonemes with start/end in seconds.
2. ``landmarks``: all 106 landmarks per frame for the real clip (tag "gt") or a generated
   evaluation tag, saved as npz, so mouth geometry can be computed locally in any way.

    MODAL_PROFILE=abdulmat40 modal run modal/apps/phonemes.py::align
    MODAL_PROFILE=abdulmat40 modal run modal/apps/phonemes.py::lms --tags gt,slot_s4,ev_wl_base
"""
from __future__ import annotations

import json
import os

import modal

import _common as C

app = modal.App("emostream-v2-phonemes")
TEST_ACTORS = {"M023", "M029", "M039", "W009", "W024", "W036"}

align_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "espeak-ng")
    .pip_install("torch==2.5.1", "torchaudio==2.5.1", index_url="https://download.pytorch.org/whl/cu121")
    .pip_install("transformers==4.46.3", "phonemizer==3.3.0", "soundfile", "numpy==1.26.4", "accelerate==1.1.1")
    .env({"HF_HOME": f"{C.MODELS}/hf"})
    .add_local_file(str(C.ROOT / "modal" / "apps" / "_common.py"), "/root/_common.py")
)
lm_image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "libgl1", "libglib2.0-0", "build-essential")
    .pip_install("numpy==1.23.5", "opencv-python-headless==4.8.1.78", "onnxruntime-gpu==1.16.3", "insightface==0.7.3")
    .add_local_file(str(C.ROOT / "modal" / "apps" / "_common.py"), "/root/_common.py")
)


def eval_clips(per_cell: int = 4, levels=(3,)) -> list[dict]:
    """The same deterministic subset as modal/apps/evaluate.py (validation split only)."""
    rows = [json.loads(line) for line in open(f"{C.DATA}/mead_v2/manifests/clips.jsonl")]
    rows = [r for r in rows if r["valid"] and r["split"] == "val" and r["actor"] not in TEST_ACTORS]
    out = []
    for actor in sorted({r["actor"] for r in rows}):
        for emo in ("neutral", "happy", "sad", "angry", "surprised"):
            lv = (1,) if emo == "neutral" else levels
            cell = sorted([r for r in rows if r["actor"] == actor and r["emotion"] == emo and r["level"] in lv],
                          key=lambda r: (r["level"], r["clip_id"]))
            out += cell[8:8 + per_cell] if len(cell) >= 8 + per_cell else cell[-per_cell:]
    return out


def tokenize(ipa: str, vocab: set[str]) -> list[str]:
    """Greedy longest match of an IPA string against the recogniser's phoneme vocabulary."""
    out, i = [], 0
    longest = max(len(v) for v in vocab)
    while i < len(ipa):
        if ipa[i] in " ˈˌ":          # spaces and stress marks are not aligned
            i += 1
            continue
        for L in range(min(longest, len(ipa) - i), 0, -1):
            if ipa[i:i + L] in vocab:
                out.append(ipa[i:i + L])
                i += L
                break
        else:
            i += 1                               # symbol the recogniser does not have
    return out


@app.function(image=align_image, gpu="A10G", timeout=3600, volumes={C.DATA: C.data_vol, C.MODELS: C.models_vol})
def align_clips(per_cell: int = 4, levels: str = "3") -> dict:
    import subprocess

    import numpy as np
    import torch
    import torchaudio.functional as AF
    from phonemizer import phonemize
    from transformers import AutoModelForCTC, AutoProcessor, pipeline

    clips = eval_clips(per_cell, tuple(int(x) for x in levels.split(",")))
    asr = pipeline("automatic-speech-recognition", model="openai/whisper-large-v3", torch_dtype=torch.float16,
                   device="cuda")
    proc = AutoProcessor.from_pretrained("facebook/wav2vec2-lv-60-espeak-cv-ft")
    ctc = AutoModelForCTC.from_pretrained("facebook/wav2vec2-lv-60-espeak-cv-ft").cuda().eval()
    vocab = proc.tokenizer.get_vocab()
    phone_vocab = {t for t in vocab if t not in ("<pad>", "<s>", "</s>", "<unk>", "|")}
    out_dir = f"{C.DATA}/eval_out/phonemes"
    os.makedirs(out_dir, exist_ok=True)
    done = 0
    for r in clips:
        video = f"{C.DATA}/mead_v2/gt256/{r['actor']}/{r['clip_id']}.mp4"
        pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", video, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le",
                              "-"], capture_output=True, check=True).stdout
        audio = np.frombuffer(pcm, "<i2").astype(np.float32) / 32768.0
        res = asr({"raw": audio, "sampling_rate": 16000}, return_timestamps="word",
                  generate_kwargs={"language": "en", "task": "transcribe"})
        text = res["text"].strip()
        words = [{"w": c["text"].strip(), "t": c["timestamp"]} for c in res.get("chunks", [])]
        ipa = phonemize(text, language="en-us", backend="espeak", strip=True, preserve_punctuation=False,
                        with_stress=False)
        phones = tokenize(ipa, phone_vocab)
        entry = {**{k: r[k] for k in ("clip_id", "actor", "emotion", "level")}, "transcript": text, "words": words,
                 "ipa": ipa, "phones": []}
        if phones:
            with torch.inference_mode():
                inp = proc(audio, sampling_rate=16000, return_tensors="pt").input_values.cuda()
                logp = torch.log_softmax(ctc(inp).logits.float(), -1)
            ids = torch.tensor([[vocab[p] for p in phones]], device="cuda")
            ali, scores = AF.forced_align(logp, ids, blank=vocab["<pad>"])
            spans = AF.merge_tokens(ali[0], scores[0].exp())
            step = len(audio) / 16000 / logp.shape[1]
            entry["phones"] = [{"p": phones[i], "start": round(s.start * step, 3), "end": round(s.end * step, 3),
                                "score": round(float(s.score), 3)} for i, s in enumerate(spans)]
            # how well the recogniser alone agrees with the transcript's phonemes (alignment sanity)
            entry["mean_phone_score"] = round(float(np.mean([s.score for s in spans])), 3)
        with open(f"{out_dir}/{r['clip_id']}.json", "w") as f:
            json.dump(entry, f, indent=1)
        done += 1
    C.data_vol.commit()
    return {"clips": done}


@app.function(image=lm_image, gpu=["T4", "L4", "A10G"], timeout=3600, volumes={C.DATA: C.data_vol}, cpu=4)
def landmarks(tag: str, per_cell: int = 4, levels: str = "3") -> dict:
    import cv2
    import numpy as np
    from insightface.app import FaceAnalysis

    fa = FaceAnalysis(name="buffalo_l", allowed_modules=["detection", "landmark_2d_106"],
                      providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    fa.prepare(ctx_id=0, det_size=(320, 320))
    lm_model = fa.models["landmark_2d_106"]
    clips = eval_clips(per_cell, tuple(int(x) for x in levels.split(",")))
    out_dir = f"{C.DATA}/eval_out/{tag}/lm106"
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    for r in clips:
        video = (f"{C.DATA}/mead_v2/gt256/{r['actor']}/{r['clip_id']}.mp4" if tag == "gt"
                 else f"{C.DATA}/eval_out/{tag}/{r['clip_id']}.mp4")
        if not os.path.exists(video):
            continue
        cap = cv2.VideoCapture(video)
        face, pts = None, []
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if face is None:
                faces = fa.get(frame)
                if not faces:
                    pts.append(np.full((106, 2), np.nan, np.float32))
                    continue
                face = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
            pts.append(lm_model.get(frame, face).astype(np.float32))
            if n == 0 and len(pts) == 20:
                # one labelled frame, to check which indices are the inner lip
                big = cv2.resize(frame, None, fx=3, fy=3)
                for i in range(52, 72):
                    x, y = (pts[-1][i] * 3).astype(int)
                    cv2.circle(big, (x, y), 3, (0, 255, 0), -1)
                    cv2.putText(big, str(i), (x + 4, y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
                cv2.imwrite(f"{C.DATA}/eval_out/{tag}/lm106_index.png", big)
        cap.release()
        np.save(f"{out_dir}/{r['clip_id']}.npy", np.stack(pts))
        n += 1
    C.data_vol.commit()
    return {"tag": tag, "clips": n}


def _align_audio(audio, asr, proc, ctc, vocab, phone_vocab):
    import numpy as np
    import torch
    import torchaudio.functional as AF
    from phonemizer import phonemize

    res = asr({"raw": audio, "sampling_rate": 16000}, return_timestamps="word",
              generate_kwargs={"language": "en", "task": "transcribe"})
    text = res["text"].strip()
    ipa = phonemize(text, language="en-us", backend="espeak", strip=True, preserve_punctuation=False, with_stress=False)
    phones = tokenize(ipa, phone_vocab)
    out = {"transcript": text, "words": [{"w": c["text"].strip(), "t": c["timestamp"]} for c in res.get("chunks", [])],
           "ipa": ipa, "phones": []}
    if phones:
        with torch.inference_mode():
            inp = proc(audio, sampling_rate=16000, return_tensors="pt").input_values.cuda()
            logp = torch.log_softmax(ctc(inp).logits.float(), -1)
        ids = torch.tensor([[vocab[p] for p in phones]], device="cuda")
        ali, scores = AF.forced_align(logp, ids, blank=vocab["<pad>"])
        spans = AF.merge_tokens(ali[0], scores[0].exp())
        step = len(audio) / 16000 / logp.shape[1]
        out["phones"] = [{"p": phones[i], "start": round(s.start * step, 3), "end": round(s.end * step, 3),
                          "score": round(float(s.score), 3)} for i, s in enumerate(spans)]
        out["mean_phone_score"] = round(float(np.mean([s.score for s in spans])), 3)
    return out


@app.function(image=align_image, gpu="A10G", timeout=3600, volumes={C.DATA: C.data_vol, C.MODELS: C.models_vol})
def align_recording(path: str, segment_s: float = 20.0) -> dict:
    """A browser session recording (avatar picture + the voice on the picture's timeline):
    transcribe and align the voice in segments (Whisper and the aligner work best on short audio)."""
    import subprocess

    import numpy as np
    import torch
    from transformers import AutoModelForCTC, AutoProcessor, pipeline

    pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    audio = np.frombuffer(pcm, "<i2").astype(np.float32) / 32768.0
    asr = pipeline("automatic-speech-recognition", model="openai/whisper-large-v3", torch_dtype=torch.float16, device="cuda")
    proc = AutoProcessor.from_pretrained("facebook/wav2vec2-lv-60-espeak-cv-ft")
    ctc = AutoModelForCTC.from_pretrained("facebook/wav2vec2-lv-60-espeak-cv-ft").cuda().eval()
    vocab = proc.tokenizer.get_vocab()
    phone_vocab = {t for t in vocab if t not in ("<pad>", "<s>", "</s>", "<unk>", "|")}
    seg = int(segment_s * 16000)
    out = {"seconds": len(audio) / 16000, "segments": []}
    for s0 in range(0, len(audio), seg):
        a = audio[s0:s0 + seg]
        if np.sqrt((a ** 2).mean()) < 1e-3:
            continue
        r = _align_audio(a, asr, proc, ctc, vocab, phone_vocab)
        off = s0 / 16000
        for p in r["phones"]:
            p["start"] = round(p["start"] + off, 3)
            p["end"] = round(p["end"] + off, 3)
        out["segments"].append({"offset_s": off, **r})
    return out


@app.function(image=lm_image, gpu=["T4", "L4", "A10G"], timeout=3600, volumes={C.DATA: C.data_vol}, cpu=4)
def recording_landmarks(path: str) -> dict:
    """106 landmarks for every frame of a recording, with each frame's presentation time."""
    import subprocess

    import cv2
    import numpy as np
    from insightface.app import FaceAnalysis

    probe = subprocess.run(["ffprobe", "-loglevel", "error", "-select_streams", "v:0", "-show_entries", "frame=pts_time",
                            "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout
    times = [float(x.split(",")[0]) for x in probe.split() if x.strip() and x.split(",")[0] != "N/A"]
    fa = FaceAnalysis(name="buffalo_l", allowed_modules=["detection", "landmark_2d_106"],
                      providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    fa.prepare(ctx_id=0, det_size=(320, 320))
    lm_model = fa.models["landmark_2d_106"]
    cap = cv2.VideoCapture(path)
    face, pts = None, []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if face is None:
            faces = fa.get(frame)
            if not faces:
                pts.append(np.full((106, 2), np.nan, np.float32))
                continue
            face = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
        pts.append(lm_model.get(frame, face).astype(np.float32))
    n = min(len(pts), len(times))
    return {"times": times[:n], "landmarks": np.stack(pts[:n]).tolist()}


@app.local_entrypoint()
def recording(path: str, out: str):
    a, l = align_recording.spawn(path), recording_landmarks.spawn(path)
    res = {"alignment": a.get(), **l.get()}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    print(json.dumps({"seconds": res["alignment"]["seconds"], "segments": len(res["alignment"]["segments"]),
                      "frames": len(res["times"]),
                      "transcript": " | ".join(s["transcript"] for s in res["alignment"]["segments"])}, indent=1,
                     ensure_ascii=False))


@app.local_entrypoint()
def align(per_cell: int = 4):
    print(json.dumps(align_clips.remote(per_cell=per_cell), indent=1))


@app.local_entrypoint()
def lms(tags: str = "gt", per_cell: int = 4):
    calls = [(t, landmarks.spawn(t, per_cell)) for t in tags.split(",")]
    for t, c in calls:
        try:
            print(json.dumps(c.get()))
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"tag": t, "error": f"{type(e).__name__}: {e}"}))
