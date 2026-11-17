# Phoneme-level articulation: diagnosis, 17 November 2026

Question from the user after session 6: the mouth moves and playback is smooth, but the mouth shapes do not correspond to the words. Three separate things are measured here, as the brief asks:

- **A. Response latency** — time from speaking to the face moving.
- **B. Temporal lip synchronisation** — whether mouth events happen at the right moment.
- **C. Phoneme-specific articulation** — whether each sound gets the right mouth shape.

## 1. The deployed checkpoint

| Item | Value |
|---|---|
| Live checkpoint | `wl_base` — `emostream-v2-models:/emostream/wl_base/model.pt`, SHA-256 `b44e81887685909627dbe6e0ff164fd464f202442530a4f3eae4081a6fdda2f5` |
| Features | WavLM-base-plus layer 6, 1 s past, 80 ms future, one window per frame (`emostream/audio/wavlm.py`) |
| Previous | `it_ccc_la2`, SHA-256 `79517d81…3893` |
| Original baseline | `reg`, frozen copy `emostream/_frozen/reg_2026-11-15/`, SHA-256 `d792adfe…7027` |
| Renderer | LivePortrait via Ditto (commit `c3e47ee`), TensorRT fp16, 512 px, full-face keypoints |

## 2. Session 6 (17 Nov, 13:27): what reached the screen

Files: `docs/evaluation/data/user_session6_diagnostics.json`; recording `emostream-session (6).webm` (local only).

| Measure | Session 6 |
|---|---|
| Page | current (H.264, synced voice) — the first session on the new page |
| GPU | **A100-40GB** (the fallback added on 16 Nov; worker log: `renderer: NVIDIA A100-SXM4-40GB`) |
| Server latency p50 / p95 | **700 / 722 ms** (at the frame-skipping threshold) |
| Frames skipped by the server | **164 of 1,018 (16 %)** |
| Pictures shown per second | 20.9 |
| Voice to frame arrival | 0.63–0.98 s |
| Voice-to-picture offset as played | voice scheduled on the picture's timeline (≈ 10 ms) |

**Finding 1 (A, and part of C): the fallback GPU was too slow.** On an A100 a frame takes 27.4 ms to render (17.5 ms on the L40S); with WavLM and H.264 encoding in series the worker could not hold 25 frames per second, so one frame in six was skipped. Skipped frames remove short mouth closures from what is seen. **Fixed and deployed:** L40S only, batched WavLM, encoding in parallel with compute. Verified on the deployed L40S with a browser: 24.8 pictures per second, server 208 ms median, 2 of 1,010 frames skipped, voice to face 751 ms (`docs/evaluation/data/browser_l40s_wavlm_pipelined.json`). A second run in the same hour was disrupted by this PC's own connection (ping to 8.8.8.8 up to 1.2 s), not by the server.

**Finding 2 (C): the recording holds very little speech.** Whisper large-v3 transcribes the session voice as "Hello, can you hear me? Hello? … hello hello" (45 s). One bilabial (the /m/ of "me") and four /oʊ/.

**Finding 3 (C): the voice signal differs strongly from the training speech.** Speech level −47 dBFS (MEAD −30; the user's sessions 3–4: −24 to −29), noise floor −74 dBFS. The phoneme aligner, which reaches 0.54–0.72 confidence on MEAD clips, reaches 0.00–0.23 on this voice. On the avatar, the inner-lip gap stays between 0.03 and 0.06 for nearly all phonemes, including the /oʊ/ of "hello" — no distinct shapes.

Loudness alone is not the cause: the live model's lip motion is unchanged when MEAD speech is attenuated to −47 dBFS (correlation with the original-level prediction 0.96; −55 dBFS: 0.92; `evaluation/benchmarks/level_sensitivity.py`, `docs/evaluation/data/level_sensitivity_wl_base.json`). What else differs (microphone, browser noise suppression, room, accent) cannot be separated with 45 s of mostly "hello"; a controlled recording is needed (section 5).

## 3. On MEAD validation speech (same clips for every model)

Pipeline and definitions: `phoneme_viseme_evaluation.md`. 80 validation clips, 1,068 aligned phonemes in 7 viseme classes.

| Measure | Real | `reg` | `it_ccc_la2` | `wl_base` |
|---|---|---|---|---|
| /p b m/ fully closed (inner lips < 3 % of eye distance) | 86 | 49 | 88 | 120 |
| Strict closure recall | 1 | 0.38 | 0.67 | **0.90** |
| Strict closure precision | 1 | 0.67 | 0.66 | 0.64 |
| Relative closure recall / precision | 1 / 1 | 0.79 / 0.91 | 0.91 / 0.91 | 0.91 / 0.91 |
| Closure timing error, mean absolute (median) | 0 | 41 ms (0) | 41 ms (0) | 43 ms (0) |
| False closures on open vowels | 0 | 9.8 % | 9.8 % | 8.5 % |
| Inner-lip gap correlation with real (best lag) | 1 (0) | 0.48 (0) | 0.53 (0) | **0.57** (0) |
| Shape error, rounded vowels (z) | 0 | 0.88 | 0.83 | **0.79** |
| Shape error, spread vowels (z) | 0 | 0.70 | 0.69 | 0.71 |
| Mouth-shape class distinctness (chance 0.14) | 0.33 | 0.28 | 0.30 | 0.30 |

Reading:

- **B (timing) is right on MEAD speech**: closures and the inner-lip trajectory have no systematic offset (median 0, one-frame jitter). This agrees with the motion-space analysis of 17 Nov (`behaviour_model_root_cause.md`).
- **C (shape) improved with every version** (closure recall 0.38 → 0.90, rounding error down) but two faults remain: `wl_base` **over-closes** (full closure on 120 bilabials where the real speaker fully closes on 86; it presses the lips where real lips only nearly touch), and **rounding** is the weakest class.
- **Distinctness** of mouth shapes per class is near the real video's, but even real video reaches only 0.33 with this measure (landmark noise on a 512 px crop), so it cannot resolve fine differences.

## 4. What this means

On studio speech the model articulates measurably better than before, at the right times. The user's impression of generic movement in session 6 has three identified contributors, in order of certainty: frames dropped by the A100 (fixed), a voice signal far from the training distribution (quiet, aligner cannot follow it), and the model's own remaining shape errors (over-closing, weak rounding). Their relative weight for the user's own voice is not yet measured.

## 5. Needed to finish the diagnosis

A controlled recording of the user's own voice (see the final report for the sentences), run offline through the same pipeline on the user's portrait. This separates the live path from the model and gives phoneme-level numbers for the user's speech.
