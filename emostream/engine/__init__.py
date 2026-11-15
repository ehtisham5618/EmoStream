"""Streaming engine. ``runtime`` and ``behaviour`` need a GPU worker; the rest is pure Python."""
from .emotion import EmotionTimeline, ditto_emotion_vector, one_hot_with_intensity

__all__ = ["EmotionTimeline", "ditto_emotion_vector", "one_hot_with_intensity"]
