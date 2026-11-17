# Phoneme and viseme evaluation pipeline

Built 17 November 2026 to measure articulation per speech sound instead of overall mouth movement. Validation actors only; the six test actors are excluded in code (`TEST_ACTORS` in `modal/apps/phonemes.py`).

## Pipeline

| Step | Tool (licence) | Code |
|---|---|---|
| Audio of each real clip | the video's own sound track (gt256 crop), so audio and real mouth are aligned by construction | `modal/apps/phonemes.py::align_clips` |
| Transcript | Whisper large-v3 (MIT), English, word timestamps | same |
| Phonemes | espeak-ng via `phonemizer` (GPL-3 tool, used, not distributed), en-us IPA, no stress marks | same |
| Phoneme timing | CTC forced alignment (`torchaudio.functional.forced_align`) with `facebook/wav2vec2-lv-60-espeak-cv-ft` (Apache-2.0); 20 ms resolution; per-phoneme confidence | same |
| Mouth geometry | insightface `landmark_2d_106` on every frame (real and rendered), all 106 points saved | `modal/apps/phonemes.py::landmarks` |
| Analysis | per phoneme occurrence, per viseme class | `evaluation/benchmarks/viseme_eval.py` |
| User recordings | same steps on a browser session recording (voice on the picture's timeline) | `modal/apps/phonemes.py::recording` |

## Transcript reliability

MEAD uses TIMIT-style read sentences. Whisper output on the 80 clips reads as those sentences (e.g. "Nuclear rockets can destroy airfields with ease."). Known error seen: "He will allow a real lie." for the TIMIT sentence "He will allow a rare lie." — one word substitution, which changes two phonemes. A systematic check (the same sentence across actors must transcribe identically) has not been run yet; phoneme confidence is recorded per clip (mean 0.54–0.72 on MEAD), and clips can be filtered by it (`--min-phone-score`).

## Viseme classes

| Class | IPA (espeak) | Expected mouth |
|---|---|---|
| bilabial | p b m | lips closed |
| labiodental | f v | lower lip to upper teeth |
| dental | θ ð | slightly open, tongue (not visible to landmarks) |
| rounded | u uː ʊ w oʊ o ɔ ɔː ɔɪ | narrow, round |
| open | ɑ ɑː æ a aɪ aʊ ʌ | wide vertical opening |
| spread | i iː ɪ eɪ e | wide horizontally |
| postalveolar | ʃ ʒ tʃ dʒ | protruded lips |

Coarticulation is not modelled in the classes; it is the reason the shape is measured as a short window around the phoneme centre and z-scored within the clip.

## Mouth measurements

Landmark indices identified from the data, not assumed: over all real clips, the pair 62 (upper inner-lip midpoint) and 60 (lower inner-lip midpoint) reaches a gap of 0.002 eye-distances when the mouth closes; the outer pair 71–53 never goes below 0.255 (lip thickness). Inner lip uses points 62, 66, 70 (upper) and 60, 54, 57 (lower); corners 52 and 61.

| Measure | Definition (normalised by the distance between the eye centres) |
|---|---|
| inner gap | lower inner-lip midpoint minus upper inner-lip midpoint (≈ 0 when closed) |
| outer aperture | vertical extent of the 20 mouth points |
| width | corner-to-corner distance |
| roundness | outer aperture / width |
| mouth shape | the 20 mouth points relative to their centre (40 values) |

## Measures

- **Bilabial closure.** Window [onset − 100 ms, offset] (lips close before the acoustic release). Relative rule: gap in the bottom 20 % of the clip's range. Strict rule: gap < 0.03. Recall, precision, timing of the gap minimum relative to the real one.
- **False closures** on open vowels.
- **Shape error per class**: |model − real| of z-scored gap, width, roundness at the phoneme centre.
- **Distinctness**: nearest-centroid classification of viseme class from the mouth shape around the phoneme centre; centroids from the real video, accuracy for each model; real video scored leave-one-out.
- **Timing**: correlation of model and real inner gap, and the lag of maximum correlation (±6 frames).

## Known limitations

- Landmarks on a 512 px face crop are noisy for small shapes; real-video distinctness is only 0.33 (chance 0.14), so this measure detects only large differences.
- Tongue and teeth (dental, labiodental) are not seen by landmarks.
- 80 clips, 4 validation actors, 158 bilabials; enough for the differences reported, not for per-phoneme detail.
- ASR errors are not yet corrected; alignment confidence varies.
- For two validation actors (W026, W035) audio and video file numbering differs; this pipeline uses each video's own sound track, so it is not affected.
