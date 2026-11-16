# Facial motion evaluation: representation, renderer, upper face and head

## 1. The 69-value motion representation

The behaviour model outputs 69 numbers per 40 ms frame, as a change from a neutral rest pose. The engine adds them to the portrait's own values and the renderer consumes all of them.

| Index | Count | Meaning | How the renderer uses it |
|---|---|---|---|
| 0–62 | 63 | Expression: a 3-D offset (x, y, z) for each of LivePortrait's 21 implicit keypoints | `kp_driving = scale · (kp_canonical · R + exp) + t`; the warping network moves the appearance volume from source to driving keypoints |
| 63–65 | 3 | Head rotation: pitch, yaw, roll, in degrees | Rotation matrix `R` |
| 66–67 | 2 | Head translation in the image plane | `t` (x, y) |
| 68 | 1 | Head scale, as a ratio | `scale` |

The implicit keypoints are learned by LivePortrait, not anatomical landmarks, so there is no published "this number is the left eyebrow" table. Two sources tell us what they do:

**From the renderer's code** (Ditto `motion_stitch.py`): lip keypoints are 6, 12, 14, 17, 19, 20 and eye keypoints are 11, 13, 15, 16, 18.

**From the data** (validation actor M005, movement ×10⁻³ in renderer units; level-3 clips against neutral):

| Keypoint | Movement in neutral speech (std) | What moves it most | Reading |
|---|---|---|---|
| 19 | y 13.8 (largest) | Speech; angry +37, sad +22 | Lower lip / jaw opening |
| 20 | y 7.6, z 3.8 | Speech, opposite in sign to 19 (correlation −0.6); happy −13, sad +19 | Upper lip |
| 17 | y 2.2, z 1.8 | Speech (correlation −0.78 with 19) | Lip region |
| 14 | y 2.6 | Happy −7 | Mouth corner region |
| 5 | x 5.3, y 7.3 | Every emotion: sad −46, angry −43, surprised −27, happy −15 (y) | Large-scale lower/mid-face deformation |
| 0 | y 3.8 | Sad −30; happy +7, surprised +9 | Brow / upper face |
| 2 | y 2.0 | Surprised −21; angry +3 | Brow raise |
| 10 | y 2.2 | Sad −12; happy +6 | Mid-face |
| 11, 13, 15, 16, 18 | 1–2.5 | Blinks; angry and surprised change eye opening | Eyes and lids |
| 6, 8, 9, 12 | < 0.5 | — | Effectively unused by the motion extractor on this data |

The z components of most keypoints are zero in the extracted data, so depth change comes almost entirely from head rotation and scale.

**Does predicting a value produce visible movement?** Yes, verified end to end: rendering the *real* extracted motion of 80 validation clips and comparing with the real videos gives mouth opening 0.94 correlation / 0.94 amplitude, jaw 0.92 / 0.96, mouth width 0.87 / 0.93, and the same emotion-classifier score as real video (0.725 vs 0.734). Every part of the representation that matters for these measures is rendered.

One difference from Ditto matters: Ditto's own stitcher keeps the driving expression only on lip and eye keypoints and copies the rest from the source. EmoStream's path (`keypoints_full_face`) applies all 63, which is what lets brows and cheeks move.

## 2. Renderer assessment

| Question | Finding | Evidence |
|---|---|---|
| Weak mouth opening | Not the renderer | Oracle: 0.94 of real amplitude |
| Insufficient jaw movement | Not the renderer | Oracle: 0.96 |
| Static eye region | Not the renderer: eye keypoints are driven; blinks render | Frame sheets; blink template |
| Limited eyebrow control | Brows move with emotion; fine detail limited by 21 keypoints | Frame sheets for sad, angry, surprised |
| Head-pose restrictions | Rotation and translation are rendered; large turns were not tested (MEAD front view has ±3°) | Oracle clips; real clips show larger motion than we drive |
| Facial distortion | None seen at emotion strength 1.0 or 1.5 on the validation portraits | Frame sheets |
| Cropping limitations | The output is the 512 px face crop; shoulders and hair outside it do not move | By design |
| Identity change | ArcFace 0.88–0.93 against the portrait; real video of the same person scores 0.75 | Scores |
| Temporal flicker | Not measured numerically; none visible in the sheets | — |
| Open-mouthed source | A real limitation of relative driving; handled by LivePortrait's lip-retargeting network | Frame sheet with and without |

**Conclusion.** For mouth, jaw, expression and identity the frozen renderer is not what limits quality; a renderer change is not justified by these measurements. Its real limits are scope (face crop only), large head turns (untested), and portraits that are not neutral.

A closed-lip smile or raised brows in the portrait remain: the engine cannot tell a person's resting face from an expression. Pulling every portrait towards an "average neutral" was examined and rejected because resting faces differ between people by as much as an emotion changes one person (keypoint 19 vertical: between-actor SD 10.8, happy offset 11.9; ×10⁻³).

## 3. Upper face

Motion space, 1,589 validation clips. "Upper-face amplitude" is the standard deviation over time of all non-lip expression coordinates, relative to the real clips.

| | Upper-face amplitude | Lip amplitude |
|---|---|---|
| `reg` (reproduced) | 0.39 | 0.53 |
| `it_ccc` | 0.79 | 0.79 |
| `it_ccc_la2` (selected) | 0.84 | 0.83 |

The concordance loss more than doubled non-lip movement. The animation is no longer a moving mouth on a still face.

## 4. Head movement

Standard deviation of head rotation within a clip, degrees (pitch / yaw / roll), same 1,589 clips:

| | Pitch | Yaw | Roll |
|---|---|---|---|
| Real clips | 1.16 | 0.56 | 0.32 |
| `reg` (reproduced) | 0.45 | 0.14 | 0.10 |
| `it_ccc_la2` | 0.94 | 0.44 | 0.27 |

Head motion is now 80 % of real in each axis instead of 25–40 %. Mean rotation error is unchanged (2.3–2.5°).

Emotion changes head pose in the data and the model learns it: for example, sad clips have a mean pitch of −23° for actor M005 against −4° for neutral (head lowered), and real within-clip variation roughly doubles for emotional speech (2.3–3.1° pitch against 1.0°).

What this does not establish: that the head moves *at the right moments*. Head motion is only weakly determined by audio, and its correlation with the real motion was not evaluated. The measure here is liveliness, and by that measure it is no longer static. Nodding in rhythm with speech was not assessed.

## 5. Eyes

| Behaviour | Implementation | Assessment |
|---|---|---|
| Blinks | The renderer's 15-frame blink template on a seeded random schedule, one blink every 2.4–4 s | Visible; intervals are random, so not periodic. Timing is not linked to speech or emotion. |
| Eye opening with emotion | Eye keypoints are predicted by the emotion branch | Surprised and angry change eye shape in the frame sheets |
| Gaze | No separate gaze model. Eye keypoints follow what the model learned from front-facing clips | Eyes stay on the camera. No deliberate gaze shifts. |

Blink statistics were not compared with real blink rates, and gaze variation was not added. Both remain as they were in the previous iteration.

## 6. Summary

| Area | Before | Now | Still limited by |
|---|---|---|---|
| Lips and jaw | 40–50 % of real movement | 72–87 % | Model timing accuracy |
| Cheeks, brows, mid-face | 39 % | 84 % | 21-keypoint representation; under-expressed emotion |
| Head | 25–40 % of real variation | about 80 % | Timing not evaluated |
| Blinks | Scheduled template | Unchanged | Not speech- or emotion-aware |
| Gaze | Fixed on camera | Unchanged | No gaze model |
| Open-mouthed portraits | Mouth never closed | Closed automatically | Closed-lip expressions in the photo remain |
