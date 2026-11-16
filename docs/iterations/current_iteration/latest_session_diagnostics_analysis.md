# The user's browser sessions of 16–17 November: what each one shows

Sources: `Downloads` on the user's PC. Diagnostics files are copied to `docs/evaluation/data/user_session{3,4,5}_diagnostics.json`; recordings stay local (not committed). Summaries: `evaluation/benchmarks/diagnostics_summary.py`. Contact sheets and freeze counts: frames extracted from the `.webm` recordings.

## Which file is which

| Session | Recording | Diagnostics | Time | Page that ran |
|---|---|---|---|---|
| 2 | `emostream-session (2).webm` | none saved | 16 Nov 19:21 | JPEG-only page (before the H.264 change) |
| 3 | `emostream-session (3).webm` | `emostream-diagnostics.json` | 16 Nov 19:24 | JPEG-only page |
| 4 | `emostream-session (4).webm` | `emostream-diagnostics (1).json` | 16 Nov 21:49 | **cached** JPEG-only page against the H.264 server |
| 5 | `emostream-session (5).webm` | `emostream-diagnostics (2).json` | 17 Nov 01:14 | **cached** JPEG-only page again |

How "cached" is established: the diagnostics of sessions 4 and 5 lack every field the newer page writes (`codec`, `jitterP95Ms`, network round trip, voice scheduling). The server's own statistics in the same files report codec `jpeg` and show that it never received an acknowledgement, which the newer page sends five times a second. The H.264 transport, network pacing and the voice-on-the-picture's-timeline playback were therefore **never exercised in any of the user's sessions**.

## Comparison

| Measure | Session 3 | Session 4 | Session 5 |
|---|---|---|---|
| Start-up | worked | failed twice (server crash, see `startup_failure_root_cause.md`), third attempt worked | worked |
| Wait from Start to first frame | 4.3 s | 35.2 s | 5.1 s |
| Seconds with frames | 37.6 | 32.4 | 26.0 |
| Server output | 24.1 FPS, 33 of 913 frames skipped | 23.9 FPS, 35 of 685 skipped | 24.9 FPS, 0 of 665 skipped |
| Server latency p50 / p95 / max | 259 / 398 / 1,276 ms | 271 / 573 / 2,122 ms | 265 / 374 / 516 ms |
| Video bitrate sent | not recorded (old server) | up to 4.6 Mbit/s (JPEG) | up to 4.2 Mbit/s (JPEG) |
| Your audio arriving late at the server (worst) | not recorded | 1,921 ms | 243 ms |
| Frames received / shown | 891 / 579 | 673 / 306 | 665 / 643 |
| Shown per second | 15.4 | 9.4 | **24.7** |
| Dropped late / skipped / held refreshes | 134 / 168 / 877 | 141 / 222 / 1,206 | 6 / 12 / 40 |
| Longest gap between shown frames | 1,150 ms | 1,833 ms | 217 ms |
| Voice → frame arrival | 0.85 – 6.8 s | 1.9 – **14.4 s** | 0.80 – 1.31 s |
| Distinct pictures in the recording | 12.5 per s | 8.4 per s | 22.9 per s |

The network was the difference between sessions: in session 4 the user's upload stalled (audio up to 1.9 s late at the server) and the 4 Mbit/s JPEG stream backed up; in session 5 the link carried it.

## Four different problems, separated

| Problem | What it is | Session 5 value | Status |
|---|---|---|---|
| Voice-to-face response delay | Time from speaking to the face moving | about 1.1 s (0.8 s to arrival + about 0.3 s buffer) | Inherent: network round trip, 200 ms model look-ahead, compute. A nearer server or WebRTC would reduce it |
| What you see and hear together | Old page: your live voice (instant) against a face 1.1 s behind | 1.1 s offset | **Fixed in the current page** (the voice is played and recorded on the picture's timeline: measured 7–9 ms median offset, 95–99 % of frames within 80 ms). Not yet seen by the user because of the cache |
| Frame presentation | Pictures shown per second, gaps | 24.7 per s, longest gap 217 ms | Good in session 5; poor in 3 and 4 because of the JPEG load on a weak link |
| Phoneme-to-mouth accuracy | Whether the mouth shape matches the sound at the right moment | Not measurable from the browser files | A model limit, analysed in `behaviour_model_root_cause.md` |

The user's description of session 5 ("smoother, but lips do not correspond to the words") matches this: presentation was fine, while the 1.1 s offset between the live voice and the face, together with the model's own accuracy limit, made the mouth look disconnected from the speech.

## Looking at the recordings

Contact sheet of session 4 (24 frames over 32 s): the mouth is closed or nearly closed in most frames, lips pressed. Two causes, measured:

- The user spoke in 24 % of the frames of that session (379 of 1,599 frames above a speech threshold); in silence a closed mouth is correct.
- The old page showed 9.4 pictures per second there, so most mouth peaks never reached the screen or the recording.

Whether the model under-reacts to browser microphone audio (noise suppression, automatic gain) was checked directly: it does not (table in `behaviour_model_root_cause.md`).

A pixel-based measurement of the speech-to-mouth offset inside the recordings (`evaluation/benchmarks/recording_lipsync.py`) was tried and is **not** used for conclusions: on real MEAD video it correlates only 0.29 with the voice, and its windowed estimates scatter by more than a second.

## Actions taken

- The page is served `no-store` and reloads itself when the server has a newer build.
- Because a cached old page cannot reload itself, the server now refuses its start request with the message "This page is out of date. Press Ctrl+Shift+R…", which the old page displays.
