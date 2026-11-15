# MEAD dataset validation and manifest — 2026-11-14

All checks were run from scratch against the original files. No manifest, feature file or statistic from the previous implementation was read.

## Where the data is

| Modal volume | Path | What it is | Used |
|---|---|---|---|
| `emostream-mead-raw` | `archives/<actor>/video.tar`, `audio.tar` | Original MEAD downloads (48 actor folders) | Read-only source for level 2/3 clips |
| `emostream-mead-raw` | `extracted/<actor>/{video,audio}/…` | Files unpacked earlier: front view, intensity level 1 only (43 actors) | Read-only source for level 1 clips |
| `emostream-mead-raw` | `status/*.json` | Download bookkeeping (size and checksum per archive) | Not needed |
| `emostream-mead-raw` | `derived/`, `features/`, `issue2/`, `pilot/` | Outputs of the discarded implementation | **Not used** |
| `emostream-studio-data` | everything | Discarded implementation's app data | **Not used** |
| `emostream-v2-data` | `mead_v2/…` | Everything this implementation writes | New |

The raw volume is mounted with `.read_only()` in every job, so it cannot be modified.

## Survey of the extracted files (`modal/apps/mead_survey.py`)

- 43 actors (24 men, 19 women), 10,629 video files, all `front` view, all `level_1`.
- Eight emotions: angry 1,258, contempt 1,247, disgusted 1,286, fear 1,278, happy 1,285, neutral 1,716, sad 1,290, surprised 1,269.
- Probed 516 clips (12 per actor, seeded sample): none failed to open. All 1920×1080. 434 are H.264 at 30 FPS and 82 are MPEG-4 at 29.97 FPS. Median length 3.8 s, maximum 14.5 s.
- **Every probed video file carries its own audio track** (AAC, 48 kHz, stereo).
- The separate `audio/` folder is incomplete: 6,816 `.m4a` files against 10,629 videos. Nineteen actors have only 21–40 audio files. Where both exist, the durations differ by up to −4.05 s / +3.23 s (median 0.03 s, 95th percentile 1.4 s).

**Decision:** use the audio track embedded in each video file. It exists for every clip and is aligned with the picture by construction; the separate audio files are neither complete nor reliably aligned.

## What the archives contain (`mead_survey.py --archives M003,W009`)

The earlier extraction kept only front view, level 1. The tar files hold more:

- Seven views: `front`, `left_30`, `left_60`, `right_30`, `right_60`, `top`, `down`.
- Three intensity levels for every emotion except neutral (which has one).
- Front view, per actor: about 30 clips per emotion and level, 40 neutral.

So the intensity data the project needs (levels 1–3) exists and only had to be unpacked. Five archive folders (48 vs 43) have no extracted counterpart and were left out.

## Manifest (`modal/apps/mead_manifest.py`)

Scope: front view; emotions neutral, happy, sad, angry, surprised; levels 1–3. Fear, disgust and contempt are outside the project's emotion set.

Level 2 and 3 clips were copied out of the tars into `emostream-v2-data:/mead_v2/raw_l23/` (10,175 files). Every clip was then probed with `ffprobe`. A clip is valid when it has one video stream, at least one audio stream, a duration between 1 s and 20 s, a frame rate between 20 and 61 FPS, and audio and video stream durations within 0.5 s of each other.

| | Clips | Valid |
|---|---|---|
| Found | 16,993 | 16,988 |
| Rejected: no audio stream | 4 | `M041_sad_L2_020` … `_023` |
| Rejected: file unreadable (`moov atom not found`) | 1 | `W014_angry_L1_017` |

All valid clips are 1920×1080 at ~30 FPS; they are resampled to 25 FPS during preprocessing.

## Splits

Actor-disjoint, fixed by a seeded shuffle within gender (`SPLIT_SEED = 20261114`), chosen before any model was trained and not revisited. The manifest builder asserts that no actor appears in two splits.

| Split | Actors | Clips | Hours |
|---|---|---|---|
| train | 33: M003 M007 M009 M011 M012 M013 M019 M022 M025 M027 M028 M030 M031 M033 M034 M035 M037 M040 M041 W011 W014 W015 W016 W018 W019 W023 W025 W028 W029 W033 W037 W038 W040 | 13,057 | 15.64 |
| val | 4: M005 M024 W026 W035 | 1,589 | 1.97 |
| test | 6: M023 M029 M039 W009 W024 W036 | 2,342 | 2.91 |

Each split is balanced over emotion and level, e.g. train has 959–990 clips for every emotion × level cell and 1,320 neutral.

The test split is not read by any training or model-selection code. `modal/apps/evaluate.py` refuses to generate on `test` unless the run tag starts with `test_`.

## Files produced

- `emostream-v2-data:/mead_survey/survey.json`, `archive_contents.json`
- `emostream-v2-data:/mead_v2/manifests/clips.jsonl` — one row per clip: id, actor, gender, emotion, level, split, path, validity and reason, resolution, FPS, durations
- `emostream-v2-data:/mead_v2/manifests/summary.json`

## Licence note

MEAD is distributed for research use under its authors' terms. The data stays on the private Modal volume; no clip, frame or derived media is committed to the repository or redistributed.
