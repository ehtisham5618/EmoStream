"""Project-wide constants. Timing is always derived from sample counts."""
from __future__ import annotations

FPS = 25
SAMPLE_RATE = 16_000
SAMPLES_PER_FRAME = SAMPLE_RATE // FPS  # 640 samples = 40 ms
assert SAMPLES_PER_FRAME * FPS == SAMPLE_RATE

# The five emotions EmoStream exposes, in a fixed order used by every model and metric.
EMOTIONS = ("neutral", "happy", "sad", "angry", "surprised")
EMOTION_TO_ID = {e: i for i, e in enumerate(EMOTIONS)}

# Ditto's motion-diffusion model takes an 8-way soft emotion vector in this order
# (core/atomic_components/condition_handler.py in antgroup/ditto-talkinghead).
DITTO_EMOTIONS = ("angry", "disgust", "fear", "happy", "neutral", "sad", "surprise", "contempt")
EMOSTREAM_TO_DITTO = {"neutral": 4, "happy": 3, "sad": 5, "angry": 0, "surprised": 6}

# LivePortrait has 21 implicit keypoints, each with a 3-D expression offset (63 values).
N_KEYPOINTS = 21
EXP_DIM = N_KEYPOINTS * 3
# Keypoint groups as used by Ditto's motion_stitch.py.
LIP_KEYPOINTS = (6, 12, 14, 17, 19, 20)
EYE_KEYPOINTS = (11, 13, 15, 16, 18)

WATERMARK_TEXT = "AI-generated"
