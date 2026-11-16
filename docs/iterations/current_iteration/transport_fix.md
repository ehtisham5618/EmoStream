# Why the browser sessions of 16 November failed, and the transport fix

Date: 16 November 2026. Input: the user's browser sessions 2 and 3 (real microphone, Chrome 157, Pakistan → Modal US-East, L40S worker) and the diagnostics file saved from session 3 (`docs/evaluation/data/user_session3_diagnostics.json`).

## What the diagnostics file shows

| Quantity (session 3, 38 s) | Value | Reading |
|---|---|---|
| Server latency, median | 240–264 ms throughout | The model and GPU kept up |
| Server output | 23.3–25 frames/s | Same |
| Voice → frame arrival in the browser | 0.85 s rising to **6.8 s**, back to 2.0 s | Frames were queueing between server and browser |
| Frames received per second | 4.5 to 48.5 | Stall, then a burst when the queue drained |
| Frames shown | 579 of 891 received (15 per second on average) | 134 arrived too late, 168 skipped in catch-up |
| Refreshes with no frame to show | 877 | Visible freezes |
| Timeline moved | 43 times | The buffer was chasing the link |

The model was not the cause. Every frame was an independent JPEG (17–35 kB; 3.4 Mbit/s measured on our own generated frames, more on detailed portraits) sent over one TCP connection. When the link could not carry that, data queued inside the connection, and nothing in the server or the client could shorten the queue.

The saved recordings had a second, separate fault: they combined the **live microphone** with the delayed picture. The face therefore trailed the voice by the whole round trip in every recording, however well the system ran.

## What Keyframe Labs does differently

From the SDK and documentation analysed earlier (`docs/reverse_engineering/technical_findings.md`), plus one new live observation.

| Aspect | Keyframe | EmoStream before this fix | Evidence |
|---|---|---|---|
| Video delivery | WebRTC video track through LiveKit: inter-frame compressed, congestion-controlled, with a jitter buffer in the browser | 25 JPEG images per second over a WebSocket | STATIC (SDK depends only on `livekit-client`) |
| Sound and picture | The GPU worker publishes the avatar's audio **and** video; the viewer hears the voice from that stream, in step with the lips | Viewer (and recording) heard the live microphone | STATIC / INF |
| Input audio | Sent ahead of playback as a data stream; the worker plays it out | Live microphone only | STATIC |
| Nearby entry point | WebRTC round trip of 97 ms and 159 ms measured from this PC in two demo calls | 262–320 ms to Modal US-East | **OBS (new)**, `evaluation/benchmarks/webrtc_stats_probe.py` |

Not obtained: Keyframe's codec, resolution, bitrate and jitter-buffer figures. The probe connected (peer connection with three audio and three video receivers) but the demo call ended before inbound video statistics appeared, in three attempts. Those remain unknown.

The important point for the user's impression that Keyframe is "perfect": in their product nobody compares a live voice with a delayed face. The avatar's voice comes out of the same stream as its picture.

## What was changed

| Part | Change | Code |
|---|---|---|
| Video codec | Low-delay H.264 (constrained baseline, no B-frames, one access unit per frame, key frame every 2 s). 900 kbit/s target instead of 3.4+ Mbit/s. JPEG stays as fallback | `backend/streaming/video.py` `H264Encoder`; tag `0x03` in the protocol |
| Decoding | WebCodecs `VideoDecoder` in the browser; key-frame request on error | `frontend/src/lib/player.ts` |
| Network pacing | The browser reports frames received five times a second. The server estimates how long frames are queueing; above 500 ms it stops encoding most frames until the queue drains and lowers the bitrate (down to 300 kbit/s), then restores it | `SendPacer` |
| Jitter buffer | The timeline sits behind the 95th percentile of recent arrival lateness; a late frame moves the timeline instead of being dropped; delay is given back slowly; cap 1.2 s | `PlayoutClock` |
| Voice with picture | The audio that was sent is replayed on the picture's timeline (sample *n* at base + *n*/16000 s). It always goes into the session recording, and to the speakers if the user ticks "Hear the avatar's voice" | `frontend/src/lib/audio.ts` `SyncedVoice` |
| Recording | Canvas is repainted while a frame is held and an inaudible tone keeps the recorded audio stream running. Without these Chrome's recorder lost 0.5–0.7 s of audio time at every pause (measured) | same, and `player.ts` |
| Emotion changes | Applied in order with the audio queue, so a change no longer lands early when audio is waiting | `backend/api/app.py` |
| Server frame skipping | Threshold raised from 450 to 700 ms (it skipped 4 % of frames when microphone audio arrived in bursts) | `modal/apps/serve.py` |
| Telemetry | Network round trip, received bitrate, arrival jitter, server pacing state, lateness of uploaded audio, decoder errors | diagnostics panel and file |

Not changed: the behaviour model, the renderer, the checkpoint (`it_ccc_la2`), emotion strength. Lip-sync accuracy of the model is as reported in `final_iteration_report.md`.

## Measurements

All with a real Chromium (headless), a recording played as the microphone, 25–48 s per run. "Drawn" is counted by wrapping `drawImage` in the page, not from the app's own counters.

### Emulated poor link (local stand-in server, real generated frames)

Link: 1.5 Mbit/s towards the browser, 150 ms each way, a 700 ms stall every 6 s (`evaluation/benchmarks/throttle_proxy.py`).

| | JPEG transport | H.264 transport |
|---|---|---|
| Frames drawn per second | 4.9 | 20.7 |
| Intervals between drawn frames at 30–50 ms | 10 % | 77 % |
| Intervals over 80 ms | 88 % | 4 % |
| Longest gap | 1,483 ms | 700 ms (the stall itself) |
| Voice → frame arrival at the end | 3.4 s and growing | 0.6–1.2 s |
| Picture minus sound, as played (median; share within ±80 ms) | — | 7 ms; 95 % |
| Picture minus sound in the saved recording, per 5 s window | — | 0 to 110 ms, typically 30–50 ms |

Before the two recording fixes the same recording was 510–740 ms out after the first stall.

### Unconstrained link (local)

24.8 frames/s drawn, 79 % of intervals at 30–50 ms, longest gap 117 ms, recording offset −30 to 0 ms.

### Deployed worker (L40S, TensorRT, `it_ccc_la2`, Pakistan → US-East), 48 s

| Measure | Value |
|---|---|
| Frames drawn per second | 23.3 |
| Intervals at 30–50 ms / over 80 ms | 75 % / 3.2 % |
| Longest gap | 684 ms |
| Video bitrate received | 836 kbit/s (H.264) |
| Picture minus sound, as played | median 8 ms; 95 % within ±80 ms |
| Frames dropped as late by the browser | 0 |
| Decoder errors | 0 |
| Network round trip (small message) | 262 ms |
| Arrival jitter, 95th percentile | 212 ms |
| Avatar behind the speaker (voice and picture together) | about 1.2 s on this link at that time |
| Server latency, median / 95 % | 275 / 410 ms |
| Frames skipped by the server engine (450 ms threshold, before it was raised) | 50 of 1,229 |

Data: `docs/evaluation/data/browser_{badlink_jpeg,badlink_h264,goodlink_h264,l40s_h264}.json`.

## What this does not fix, and what was not tested

- **Delay behind the speaker.** The avatar is 0.6–1.2 s behind the person speaking on this route (network round trip, 200 ms model look-ahead, 70 ms compute, buffer). Voice and picture are together, so a viewer sees correct lip-sync; the speaker watching their own avatar still sees it answer late. Only a nearer worker or WebRTC reduces that.
- **Still TCP.** One lost packet delays everything behind it. WebRTC (UDP, as Keyframe uses) avoids that. It needs either a LiveKit project or a TURN relay, which is an account decision for the user, and was not built.
- **A person at a real microphone** has not tested this build; the measurements used a recording as the microphone.
- **Echo.** With "Hear the avatar's voice" ticked and loudspeakers, the microphone can pick the voice up again. Headphones avoid it; not measured.
- **The lip-sync accuracy of the model itself** is unchanged (mouth correlation 0.55–0.58 against real video).
- Safari and Firefox were not tested; a browser without WebCodecs H.264 falls back to JPEG.
- Five-minute browser session: not run.

## How to reproduce

```
python -m evaluation.benchmarks.fake_server --dist frontend/dist --port 8765 --block 1 --lookahead-frames 5 \
    --video outputs/compare/side_by_side/M005_happy_L3_009.mp4
python -m evaluation.benchmarks.throttle_proxy --listen 8766 --target 8765 --down-kbps 1500 --delay-ms 150 \
    --stall-every 6 --stall-ms 700
python -m evaluation.benchmarks.browser_playback --url "http://127.0.0.1:8766/" --mic-wav <48 kHz wav> \
    --seconds 30 --record out.webm            # add "?video=jpeg" to the URL for the old transport
python -m evaluation.benchmarks.recording_av_offset out.webm
```
