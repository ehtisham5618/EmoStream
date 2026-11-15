# Evidence and limitations

Investigation date: 2026-11-14. Target: Keyframe Labs (keyframelabs.com), public surface only.

## Claim labels used in this folder

| Label | Meaning |
|---|---|
| **[OBS]** Direct observation | Seen in the live public page through REA/CDP on our own browser. |
| **[DOC]** Publicly documented claim | Stated by Keyframe on its site, docs, blog, changelog or pricing page. A vendor claim, not verified by us. |
| **[STATIC]** Static analysis evidence | Read from published code (the MIT-licensed npm package `@keyframelabs/sdk` 0.3.0) or from page scripts. Shows what the code can do, not that it ran. |
| **[INF]** Technical inference | Our reasoning from the evidence above. May be wrong. |
| **[UNK]** Unknown | Not established by any evidence we have. |

## Evidence sources

| ID | Source | How obtained | Used for |
|---|---|---|---|
| E1 | REA `list_browser_targets`, evidence `ev_90a0500a…d4ff` | CDP, dedicated Chrome profile on 127.0.0.1:9222 | Browser reachable (Chrome 157). |
| E2 | REA `inspect_web_page` on `https://keyframelabs.com/`, evidence `ev_f801ebe010accdac54d438d03c319ae106d613fe351e9f9d85fd24c915944bbc` | Passive CDP inspection, 4 s window, accessibility text on | Page structure, visible claims, script inventory. |
| E3 | REA `analyze_web_bundle` on the same page, evidence `ev_238a1c5a2a617652f782ad89b5683ab814307be84efe9fae8bd886c34cc57e95` | Static analysis of 16 captured scripts, source maps requested | Endpoint search (none found), build system. |
| E4 | npm package `@keyframelabs/sdk` 0.3.0 (MIT), dependency `livekit-client ^2.15.14` | `npm pack`, files read locally; never executed | Transport, audio format, emotion protocol. |
| E5 | `https://keyframelabs.com/blog/persona-1-5-live` ("Semantic Codes: Decoupling Behavior from Appearance in Real-Time Avatars", 27 Mar 2026) | Web fetch, summarised | Publicly described architecture. |
| E6 | `https://docs.keyframelabs.com/` incl. `llms.txt`, `llms-full.txt`, `sdk-reference/javascript`, `api-reference/v1/openapi.json` (Sessions API 1.3.0) | Web fetch, summarised | API surface, integrations, emotion API. |
| E7 | `https://keyframelabs.com/benchmarks`, `/changelog`, `/pricing` | Web fetch, summarised | Model versions, claims, plan limits. |

E5–E7 were read through a fetch-and-summarise tool, so wording in our notes is paraphrase except where quoted. Parts of E6 (`llms-full.txt`, OpenAPI) came back as model-extracted summaries rather than verbatim text.

## What was not done, and why

1. **No live avatar session was observed.** The homepage "Start call" demo needs a click and microphone permission. REA's CDP tools are passive, and nobody was at the browser during this pass. Consequently there are no runtime observations of: the session request, LiveKit signalling, WebRTC media, WebSocket frame sizes, video resolution/FPS/bitrate, or first-frame latency. Everything about runtime behaviour below is [DOC], [STATIC] or [INF].
2. **No network bodies.** CDP inspection records metadata only. A HAR export is needed for bodies (procedure below).
3. **No WebSocket/WebRTC payloads.** REA reports WebSocket frame sizes at most. Media travels over WebRTC (SRTP), which CDP network capture does not show at all; `chrome://webrtc-internals` is the right tool.
4. **No authenticated surfaces.** `platform.keyframelabs.com` (dashboard), the Sessions API and image-to-avatar (Enterprise-only per the pricing page) were not accessed. No API key was created or used.
5. **Bundle analysis was partial.** One of 16 scripts hit REA's 30 s per-script deadline (`scr_8e3660d7…`), so findings from that script are unknown. No endpoint candidates were found in the other 15. No source maps were declared.
6. **Attach-window limits.** REA attached after page load, so load-time network requests and console events were not captured (`attach_limited`).
7. **Nothing proprietary was recovered.** No model weights, training code, server code or internal parameters are available publicly, and none were sought.

## Manual follow-up for a live-session observation (optional, ~5 minutes)

This would upgrade several [INF] rows to [OBS]. It only uses the public homepage demo.

1. Launch the dedicated profile:
   `& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="$env:USERPROFILE\rea-chrome-profile" https://keyframelabs.com/`
2. Open a second tab at `chrome://webrtc-internals` **before** starting the call.
3. Open DevTools (F12) on the Keyframe tab, Network panel, tick **Preserve log**.
4. Tell Claude to start `observe_web_session` (60 s window), then click **Start call**, allow the microphone, speak for ~20 s, and end the call.
5. In `chrome://webrtc-internals`, expand the peer connection and note for the inbound video: `frameWidth`, `frameHeight`, `framesPerSecond`, codec, `jitterBufferDelay`; then **Create dump** and save it.
6. In the Network panel: right-click → **Save all as HAR (sanitized)**. The sanitized option strips cookies and `Authorization` headers. Before sharing, open the file and search for `token`, `Bearer`, `participant_token`, `cookie` and delete any remaining values. Give Claude the path; it will be read with `inspect_web_network_capture` (format `har`) without contacting any URL.

Never share an unsanitized HAR: session responses contain a `participant_token` JWT.

## Legal and ethical boundary

Only public pages, public docs and an MIT-licensed public npm package were read. No access control was bypassed, no API was called, and Keyframe's hosted service is not used anywhere in our implementation. The findings are used as product and architecture reference; EmoStream is built on independently selected open-source models and our own code.
