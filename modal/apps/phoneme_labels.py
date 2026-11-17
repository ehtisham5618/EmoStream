"""Per-frame phoneme and viseme labels for every train/validation clip with verified audio.

Transcripts: MEAD actors read the same sentences, identified by the audio file name
(<emotion>/level_<l>/<nnn>.m4a; the content-verified map gives each clip's file). Each distinct
sentence is transcribed with Whisper large-v3 from two different actors; the transcript is kept
only if both agree after normalisation (case, punctuation). Then every clip is force-aligned to
its sentence's phonemes (espeak IPA, CTC aligner, 20 ms), and each 40 ms video frame gets:
  phone   index into the aligner's phoneme vocabulary (-1 = silence / unaligned)
  viseme  0 silence, 1..7 viseme classes (as in evaluation/benchmarks/viseme_eval.py), 8 other
Test actors are refused.

Output: /data/mead_v2/phonemes/<actor>.npz  clip_ids, lengths, viseme (int8 per frame),
        phone (int16 per frame), phone_score (float16 per frame); manifest transcripts.json.

    MODAL_PROFILE=abdulmat40 modal run modal/apps/phoneme_labels.py
"""
from __future__ import annotations

import json
import os
import re

import modal

import _common as C
from phonemes import align_image, tokenize

app = modal.App("emostream-v2-phoneme-labels")
TEST_ACTORS = {"M023", "M029", "M039", "W009", "W024", "W036"}
VISEMES = [
    ("bilabial", {"p", "b", "m"}),
    ("labiodental", {"f", "v"}),
    ("dental", {"θ", "ð"}),
    ("rounded", {"u", "uː", "ʊ", "w", "oʊ", "o", "ɔ", "ɔː", "ɔɪ"}),
    ("open", {"ɑ", "ɑː", "æ", "a", "aɪ", "aʊ", "ʌ"}),
    ("spread", {"i", "iː", "ɪ", "eɪ", "e"}),
    ("postalveolar", {"ʃ", "ʒ", "tʃ", "dʒ"}),
]
image = align_image.add_local_file(str(C.ROOT / "modal" / "apps" / "phonemes.py"), "/root/phonemes.py")


def viseme_index(p: str) -> int:
    for i, (_, ps) in enumerate(VISEMES):
        if p in ps:
            return i + 1
    return 8


def norm(t: str) -> str:
    return re.sub(r"[^a-z' ]", "", t.lower()).split().__str__()


def decode(path: str):
    import subprocess

    import numpy as np

    pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(pcm, "<i2").astype(np.float32) / 32768.0


@app.function(image=image, gpu="A10G", timeout=3 * 3600, volumes={C.DATA: C.data_vol, C.MODELS: C.models_vol},
              memory=16384)
def transcribe_sentences() -> dict:
    import torch
    from transformers import pipeline

    amap = json.load(open(f"{C.DATA}/mead_v2/manifests/audio_map.json"))["mapping"]
    by_sentence: dict[str, list[tuple[str, str]]] = {}
    for actor, m in amap.items():
        if actor in TEST_ACTORS:
            continue
        for cid, rel in m.items():
            by_sentence.setdefault(rel, []).append((actor, cid))
    asr = pipeline("automatic-speech-recognition", model="openai/whisper-large-v3", torch_dtype=torch.float16,
                   device="cuda")
    out, agree, disagree = {}, 0, 0
    for rel, items in sorted(by_sentence.items()):
        items = sorted(items)
        texts = []
        for actor, _ in (items[0], items[len(items) // 2]) if len(items) > 1 else items[:1]:
            audio = decode(f"{C.DATA}/mead_v2/audio/{actor}/{rel}")
            texts.append(asr({"raw": audio, "sampling_rate": 16000},
                             generate_kwargs={"language": "en", "task": "transcribe"})["text"].strip())
        ok = len(texts) == 2 and norm(texts[0]) == norm(texts[1])
        agree += ok
        disagree += (not ok) and len(texts) == 2
        out[rel] = {"text": texts[0], "alt": texts[1] if len(texts) > 1 else None, "agree": ok, "clips": len(items)}
    with open(f"{C.DATA}/mead_v2/manifests/transcripts.json", "w") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    C.data_vol.commit()
    return {"sentences": len(out), "agree": int(agree), "disagree": int(disagree)}


@app.function(image=image, gpu="A10G", timeout=3600, volumes={C.DATA: C.data_vol, C.MODELS: C.models_vol},
              memory=16384, max_containers=8)
def label_actor(actor: str) -> dict:
    import numpy as np
    import torch
    import torchaudio.functional as AF
    from phonemizer import phonemize
    from transformers import AutoModelForCTC, AutoProcessor

    assert actor not in TEST_ACTORS
    amap = json.load(open(f"{C.DATA}/mead_v2/manifests/audio_map.json"))["mapping"].get(actor, {})
    trans = json.load(open(f"{C.DATA}/mead_v2/manifests/transcripts.json"))
    z = np.load(f"{C.DATA}/mead_v2/packed/{actor}.npz")
    proc = AutoProcessor.from_pretrained("facebook/wav2vec2-lv-60-espeak-cv-ft")
    ctc = AutoModelForCTC.from_pretrained("facebook/wav2vec2-lv-60-espeak-cv-ft").cuda().eval()
    vocab = proc.tokenizer.get_vocab()
    phone_vocab = {t for t in vocab if t not in ("<pad>", "<s>", "</s>", "<unk>", "|")}
    ipa_cache: dict[str, list[str]] = {}
    vis, ph, sc, n_ok, scores = [], [], [], 0, []
    for cid, n in zip(z["clip_ids"].tolist(), z["lengths"].tolist()):
        v = np.full(n, -1, np.int8)
        p = np.full(n, -1, np.int16)
        s = np.zeros(n, np.float16)
        rel = amap.get(cid)
        t = trans.get(rel) if rel else None
        if t and t["agree"]:
            if rel not in ipa_cache:
                ipa = phonemize(t["text"], language="en-us", backend="espeak", strip=True, with_stress=False)
                ipa_cache[rel] = tokenize(ipa, phone_vocab)
            phones = ipa_cache[rel]
            audio = decode(f"{C.DATA}/mead_v2/audio/{actor}/{rel}")
            if phones and len(audio) > 1600:
                with torch.inference_mode():
                    logp = torch.log_softmax(ctc(proc(audio, sampling_rate=16000, return_tensors="pt")
                                                 .input_values.cuda()).logits.float(), -1)
                ids = torch.tensor([[vocab[x] for x in phones]], device="cuda")
                try:
                    ali, scr = AF.forced_align(logp, ids, blank=vocab["<pad>"])
                    spans = AF.merge_tokens(ali[0], scr[0].exp())
                except Exception:  # noqa: BLE001  (transcript longer than the audio allows)
                    spans = []
                step = len(audio) / 16000 / logp.shape[1]
                v[:] = 0
                for i, sp in enumerate(spans):
                    a, b = int(sp.start * step * 25), int(np.ceil(sp.end * step * 25))
                    v[a:b + 1] = viseme_index(phones[i])
                    p[a:b + 1] = vocab[phones[i]]
                    s[a:b + 1] = float(sp.score)
                    scores.append(float(sp.score))
                if spans:
                    n_ok += 1
        vis.append(v)
        ph.append(p)
        sc.append(s)
    os.makedirs(f"{C.DATA}/mead_v2/phonemes", exist_ok=True)
    np.savez(f"{C.DATA}/mead_v2/phonemes/{actor}.npz", clip_ids=z["clip_ids"], lengths=z["lengths"],
             viseme=np.concatenate(vis), phone=np.concatenate(ph), phone_score=np.concatenate(sc))
    C.data_vol.commit()
    return {"actor": actor, "clips": len(vis), "aligned": n_ok, "mean_phone_score": round(float(np.mean(scores)), 3)
            if scores else None}


@app.local_entrypoint()
def main(skip_transcripts: bool = False):
    if not skip_transcripts:
        print(json.dumps(transcribe_sentences.remote()), flush=True)
    packed = json.load(open(C.ROOT / "outputs" / "local" / "packed.json"))
    actors = [a for a in packed["splits"]["train"]["actors"] + packed["splits"]["val"]["actors"] if a not in TEST_ACTORS]
    calls = [(a, label_actor.spawn(a)) for a in actors]
    for a, c in calls:
        try:
            print(json.dumps(c.get()), flush=True)
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"actor": a, "error": f"{type(e).__name__}: {e}"}), flush=True)
