# Lip closure and mouth opening: experiments, 17 November 2026

Two questions: does the avatar close its lips for /p b m/ at the right time, and does it open them enough for vowels? Measurement pipeline: `phoneme_viseme_evaluation.md`.

## 1. On MEAD validation speech (80 clips, evaluation portraits)

See `phoneme_articulation_diagnosis.md` §3. Closure timing is right (median error 0, one-frame jitter). `wl_base` closes on 90 % of real full closures but also closes fully on 34 bilabials where the real speaker only nearly closes (precision 0.64).

## 2. On the user's own recording and portrait

Input: the user's recording of six test sentences (26 s, speech −23.6 dBFS, noise floor −79 dBFS) and the user's portrait (`Portrait.png`; lip-opening ratio 0.31, i.e. clearly open). Rendered offline through the live engine (L40S, TensorRT, per-frame streaming, emotion strength 1.5; `modal/apps/live_bench.py`), then transcribed, phoneme-aligned (aligner confidence 0.50–0.54) and measured (`modal/apps/phonemes.py::recording`, `evaluation/benchmarks/user_recording_eval.py`). 15 bilabial, 23 rounded, 17 spread, 9 open-vowel, 12 labiodental occurrences.

Real-speaker reference: inner-lip gap at the phoneme centre on the 80 MEAD validation clips — bilabial 0.102, labiodental 0.125, dental 0.189, rounded 0.182, open 0.233, spread 0.191, postalveolar 0.166; full closure on 54 % of bilabials.

### Finding: the mouth-closing step over-closed this portrait

For portraits with an open mouth, the engine adds LivePortrait's lip-closing offset (target ratio 0) to every frame (added on 16 Nov). On this portrait it pressed the lips together: during speech the inner-lip gap stayed at 0.026–0.048 for **every** sound class — vowels opened to 20–25 % of a real speaker's opening — and the chin puckered. This is the "barely speaking, generic movement" the user saw.

Sweep (model `wl_base`; one variable changed):

| Closing setting | Mean |gap − real| over classes | Vowel minus /p b m/ gap (real 0.131) | /p b m/ full closure (real 54 %) |
|---|---|---|---|---|
| target 0, strength 1 (as deployed until now) | 0.133 | 0.022 | 100 % |
| strength 0.75 | 0.114 | 0.045 | 67 % |
| target 0.08 | 0.113 | 0.052 | 93 % |
| strength 0.6 | 0.098 | 0.058 | 33 % |
| strength 0.5 | 0.086 | 0.066 | 20 % |
| **target 0.15** | **0.087** | **0.070** | **47 %** |
| no closing | 0.023 | 0.076 | 0 % (lips never close) |

**Change:** portraits with lip ratio ≥ 0.2 are closed to a relaxed ratio of 0.15; portraits between 0.03 and 0.2 keep target 0 (validated on MEAD, evaluation portrait ratio 0.12). `emostream/engine/retarget.py::lip_target_for`.

### Same recording, new closing, three models

| Model | Mean |gap − real| | Vowel minus /p b m/ | /p b m/ full closure | Width z: rounded / spread |
|---|---|---|---|---|
| `wl_base` | 0.087 | 0.070 | 47 % | −0.74 / +0.67 |
| `ph_aug` | 0.088 | 0.070 | 73 % | −0.75 / +0.49 |
| `ph_all` | 0.082 | 0.068 | 20 % | −0.86 / +0.92 |

With 15 bilabials these differences are not significant.

### Remaining limit

Even with the best setting, vowel openings on this portrait reach about half a real speaker's range (0.070 against 0.131); on the MEAD evaluation portrait the model reaches about 80 % of real opening amplitude. Whether the renderer or the model limits this portrait is being tested by driving the user's portrait with real recorded motion (section 3).
