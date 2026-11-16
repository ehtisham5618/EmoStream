"""Composes labelled side-by-side comparison videos (same clip, same audio).

    python -m evaluation.benchmarks.side_by_side --out out.mp4 --audio-from 0 \
        "Real video=gt.mp4" "Previous (reg)=reg.mp4" "Improved=new.mp4"

Each input is scaled to a square of ``--size`` pixels; a label strip is drawn above.
The audio track is taken from the input given by ``--audio-from``.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont


def header(labels: list[str], size: int, path: str) -> None:
    img = Image.new("RGB", (size * len(labels), 44), (23, 28, 58))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    for i, text in enumerate(labels):
        w = draw.textlength(text, font=font)
        draw.text((i * size + (size - w) / 2, 9), text, fill=(255, 255, 255), font=font)
    img.save(path)


def compose(items: list[tuple[str, str]], out: str, size: int = 384, audio_from: int = 0) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        head = os.path.join(tmp, "head.png")
        header([label for label, _ in items], size, head)
        cmd = ["ffmpeg", "-loglevel", "error", "-y"]
        for _, path in items:
            cmd += ["-i", path]
        cmd += ["-loop", "1", "-i", head]
        n = len(items)
        parts = "".join(f"[{i}:v]fps=25,scale={size}:{size}[v{i}];" for i in range(n))
        row = "".join(f"[v{i}]" for i in range(n)) + f"hstack=inputs={n}[row];"
        graph = parts + row + f"[{n}:v][row]vstack=inputs=2:shortest=1[v]"
        cmd += ["-filter_complex", graph, "-map", "[v]", "-map", f"{audio_from}:a?", "-c:v", "libx264", "-crf", "20",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out]
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("items", nargs="+", help="label=path")
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, default=384)
    ap.add_argument("--audio-from", type=int, default=0)
    a = ap.parse_args()
    compose([tuple(x.split("=", 1)) for x in a.items], a.out, a.size, a.audio_from)
    print(a.out)
