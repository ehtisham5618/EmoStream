# Browser session quality analysis

Two recordings made by the project owner in the browser on 2026-11-15, saved by the app's "Save this session" button (a `MediaRecorder` capture of the on-screen canvas plus the microphone).

| | Session A | Session B |
|---|---|---|
| File | `emostream-session.webm` (15:53) | `emostream-session (1).webm` (15:54) |
| Container | WebM: VP8 512×512 video, Opus 48 kHz mono audio | same |
| Audio length | 25.4 s | 18.4 s |
| First video frame at | 2.75 s | 2.39 s |
| Video frames recorded | 248 | 173 |

**Evidence available:** the two video files only. No browser console log, backend log, WebSocket trace or screenshots were supplied, and the emotion, model and GPU used in each session are not recorded in the files. Everything below is measured from the recordings; where a cause cannot be established from them, it is listed as a hypothesis with the experiment that tested it.

Working copies and extracted frames are in `outputs/sessions/` (not committed: they contain the test portrait). Frame sheets: `outputs/sessions/sheet_A.png`, `sheet_B.png` (every 8th recorded frame).

## What the recordings show

### Playback (both sessions)

Measured from the video packet timestamps, i.e. the moments the canvas actually changed:

| | Session A | Session B |
|---|---|---|
| Distinct frames per second | 10.6 | 10.4 |
| Time between frames, median | 51 ms | 52 ms |
| 95th percentile | 252 ms | 229 ms |
| Longest gap | 990 ms (at 5.1 s) | 303 ms |
| Gaps over 100 ms | 82 of 247 (33 %) | 73 of 172 (42 %) |
| Gaps over 200 ms | 32 | 19 |
| Near-identical consecutive frames | 7 | 5 |

The intervals are bimodal: a few frames 10–50 ms apart, then a gap of 150–250 ms, repeating. In Session B, 42 of 172 intervals fall between 150 and 200 ms. That is the visible stutter: the picture advances in short bursts about five times a second instead of every 40 ms.

So the viewer saw about 10.5 distinct images per second, not 25, and they were unevenly spaced. The backend's frame counter does not see any of this.

### Mouth and jaw (both sessions)

- The mouth is open in essentially every recorded frame, including long stretches with no speech. Speech occupies 25 % of Session A and 29 % of Session B (audio RMS above 0.02); the rest is silence.
- A mouth-region contrast measure is the same in silence and in speech: A 37.7 vs 37.6, B 38.7 vs 37.8. The mouth does not close when the speaker stops and does not visibly open further when they speak.
- Correlation between the audio envelope and mouth-region motion is 0.18 (A) and 0.32 (B) at best, and that best is at a video delay of 1.6 s (A) and 1.0 s (B). At zero delay it is −0.05 and 0.04. Articulation is weak and arrives late.

### Expression, eyes, head

- Session A shows a broad, teeth-showing smile in every frame; Session B a smaller rounded open mouth in every frame. The expression does not change during either session.
- Blinks occur (visible in sheet A, frames 5, 15, 31).
- Head position is almost static; small tilts only.
- No frame shows a closed-mouth neutral face, so neither session contains a convincing neutral.

### Differences between the sessions

The mouth shape differs (wide smile vs small open mouth), which is consistent with a different selected emotion or intensity, but the files do not say which. Playback behaviour is the same in both. Session A has one long freeze (990 ms); B has none.

## Root causes

Each cause below was tested; the test and its result are given.

### C1. Frames were drawn when they arrived, not on a clock — **confirmed**

In microphone mode the client called `draw()` on each frame as it arrived (`frontend/src/App.tsx`, baseline commit). The server produces frames in groups of five (one speech-encoder block = 200 ms of audio) and renders a group in about 100 ms, so five frames arrive close together and then nothing for about 100 ms; network jitter adds to it. A 25 FPS canvas capture — and the eye — merges frames that are 10–20 ms apart, which leaves roughly two visible images per group: 10 per second. That matches the measured 10.5 per second and the bimodal intervals.

Fix: `frontend/src/lib/player.ts`, a paced player with a bounded buffer. See `browser_playback_diagnostics.md`.

### C2. The avatar's rest pose is the portrait's own expression — **confirmed**

Running the two sessions' audio through the same `reg` checkpoint offline (`evaluation` scripts, CPU) shows that the model predicts almost no motion during the silent parts: mean lip-opening delta −0.0003 (A) and 0.0000 (B), against −0.0066 and −0.0058 during speech. The model *does* return to rest.

The engine adds the predicted motion to the uploaded portrait's own expression. The test portrait shows an open-mouthed smile, so "rest" is an open-mouthed smile, and the avatar can never close its mouth or look neutral. This is an engine design gap, not a model error.

Averaging towards a "population neutral face" was examined and rejected: between-actor variation of the rest expression in MEAD is as large as the emotion offsets themselves (e.g. keypoint 19, vertical: between-actor SD 10.8 against a happy offset of 11.9, all ×10⁻³), so that would distort identity.

Fix: LivePortrait's lip-retargeting network, which computes the keypoint offset that closes an open-mouthed source, applied once per portrait (`emostream/engine/retarget.py`). The server also tells the client when a portrait has an open mouth. A closed-lip smile in the photo is not removed; that remains a limitation and is stated to the user.

### C3. Articulation is under-sized because the model regresses to the mean — **confirmed**

On validation clips, `reg`'s lip motion has 0.47 of the real amplitude and correlates 0.50 with it (single actor, lip principal component); on rendered video its mouth opening has 0.40 of the real amplitude and its jaw displacement 0.50 (80 clips, landmark-based). Amplitude ratio ≈ correlation is what an L1/L2 regression produces when it is uncertain: it predicts the average of the plausible motions.

Checked and excluded as causes:

- *Audio/video misalignment in MEAD.* Stream start times are identical; SyncNet's own offset estimate on 24 ground-truth validation clips is 0 or −1 frame for 20 of them (range −4…0).
- *Normalisation.* Targets are standardised per dimension and un-standardised on output; lip dimensions are the largest and are not clipped.
- *Renderer.* Driven by the real motion of each validation clip, the same renderer reproduces the real video's mouth opening at 0.94 correlation and 0.94 amplitude and its jaw movement at 0.92 / 0.96 (80 clips; `facial_motion_evaluation.md`).
- *Chunk boundaries.* Chunked and whole-sequence outputs differ by less than 1e-6.

Fix: a concordance-correlation loss term, which is maximal only when correlation, amplitude and offset all match. See `articulation_improvement.md`.

### C4. Delay of 1.0–1.6 s between speech and mouth motion — **main cause found**

The engine's own delay was 269 ms (p50) on an L40S, and a WebSocket client in Pakistan measured 570 ms round trip to the US-East worker. That leaves 0.4–1.0 s unexplained by engine and network.

Cause, reproduced in a real browser against the GPU worker: the client captured microphone audio while the portrait was still being prepared (about 3 s) and **queued** it, then sent it all at once when the server reported ready. The server therefore started several seconds behind the speaker and could only recover by skipping frames. Measured voice-to-face delay in that test: 2,576 ms, with 378 of 1,305 frames skipped by the server. After changing the client to discard audio captured before the server is ready: 541–554 ms, with 6–11 frames skipped.

Contributing: 200 ms microphone chunks (now 80 ms), and a worker that may have been an A10G running just under real time.

### C5. Emotion too weak to read, neutral reads as happy — **confirmed in part**

Independent of the portrait problem (C2): in motion space `reg` reaches only about 40 % of the real level-3 expression strength at full intensity, and its "happy" direction is the least accurate (cosine 0.45). On rendered validation clips the classifier labels 11 of 16 neutral clips "happy". See `emotion_control_evaluation.md`.

## Not determinable from the two recordings

- Which emotion, intensity, model and GPU each session used.
- How much of the 1.0–1.6 s delay was network, server queue or browser.
- Whether frames were skipped by the server or merged by the canvas capture (the capture cannot distinguish them).

The updated client has a "Save diagnostics file" button that records these every half second; a session recorded with it will answer all three.
