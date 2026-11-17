# Speech feature timing (WavLM, live model `wl_base`)

| Item | Value | Where |
|---|---|---|
| Encoder | `microsoft/wavlm-base-plus`, hidden layer 6 (768-d) | `emostream/audio/wavlm.py` |
| Sample rate | 16 kHz mono | browser capture and server resampling |
| Encoder stride | 320 samples (20 ms); receptive field 400 samples | WavLM convolution stack |
| Video frame | 640 samples (40 ms); frame k covers samples [640k, 640(k+1)) | `emostream/constants.py` |
| Frame feature | mean of encoder vectors 2m and 2m+1 of the segment, m = k − segment start | exact, segments start on frame boundaries |
| Window for frame k | [max(0, 640(k+1) − 16,000), 640(k+3)) — up to 1 s of past, 80 ms of future | same |
| Model look-ahead | 2 feature frames (80 ms) | checkpoint config |
| Total audio after a frame that its motion may use | 160 ms | |
| Algorithmic delay | 5 frames = 200 ms | `EmoStreamBehaviour.algorithmic_delay_frames` |

## Checks

| Check | Result | Evidence |
|---|---|---|
| Live features equal training features | max difference < 1e-4 for every chunk size tested | `tests/test_wavlm_features.py` |
| A frame's feature ignores audio after its window | verified | same |
| Batched live computation (new, 17 Nov) equals per-frame | verified | same |
| TF32 matrix maths (allowed on GPU) vs FP32 | cosine ≥ 0.999999, mean relative difference 0.06 % | `modal/apps/wavlm_precision.py` |
| Feature-to-mouth alignment (Ditto features) | best predicting feature is the frame's own (offset 0) | `behaviour_model_root_cause.md` §2 |
| Model lag against real mouth (WavLM) | median 0 frames on the inner-lip gap | `phoneme_articulation_diagnosis.md` §3 |
| Future context | 80 ms gives probe 0.346, 160 ms gives 0.389 (per-frame windows); the model's own 2-frame look-ahead supplies the second 80 ms | `docs/evaluation/data/feature_encoder_probe_perframe.json` |
| Sensitivity to loudness | −20 to −47 dBFS: lip motion correlation with the original ≥ 0.96; −55 dBFS: 0.92 | `docs/evaluation/data/level_sensitivity_wl_base.json` |

Cost per frame on the L40S: one WavLM call 9.5 ms, two frames in one call 10.6 ms; the live path batches the frames of each 80 ms microphone chunk.

Not yet done: an offset sweep with WavLM features (the Ditto-feature sweep found 0; the WavLM model's measured lag is 0, so no shift is indicated).
