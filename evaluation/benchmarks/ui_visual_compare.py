"""Screenshot comparison of the delivered Lovable UI and the integrated product UI (web/).

Takes full-page screenshots of every route on both servers, at desktop and phone widths, in the
light and dark themes, and reports the share of pixels that differ (per-channel difference > 24)
plus a side-by-side image for review. Differences are expected where content was changed on
purpose (figures, labels, the Studio's added consent and voice controls); everything else should
be identical.

    # delivered UI (git archive of the delivered commit, `vite dev`) and the integrated build
    python -m evaluation.benchmarks.ui_visual_compare --a http://127.0.0.1:5180 --b http://127.0.0.1:8765 --out outputs/ui_compare
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np
from PIL import Image

ROUTES = ["/", "/how-it-works", "/capabilities", "/research", "/responsible-ai", "/privacy", "/about", "/sign-in",
          "/app", "/app/studio", "/app/avatars", "/app/sessions", "/app/analytics", "/app/integrations", "/app/models",
          "/app/settings", "/app/help", "/app/text-to-speech", "/app/conversation"]
VIEWPORTS = {"desktop": (1440, 900), "phone": (390, 844)}


def shoot(p, base: str, route: str, size, theme: str, path: str):
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": size[0], "height": size[1]}, reduced_motion="reduce")
    ctx.add_init_script(f"localStorage.setItem('emostream.settings.v1', JSON.stringify({{theme: '{theme}'}}));")
    page = ctx.new_page()
    # the integrated build asks the engine for /api/info; the delivered one has no engine
    page.goto(base + route, wait_until="load", timeout=120000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:  # noqa: BLE001 - a dev server can keep a request open; the page is loaded
        pass
    page.wait_for_timeout(1200)
    page.add_style_tag(content="*{animation:none!important;transition:none!important;caret-color:transparent!important}")
    page.wait_for_timeout(200)
    page.screenshot(path=path, full_page=True)
    browser.close()


def diff(a_path: str, b_path: str, side: str) -> dict:
    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    w, h = max(a.width, b.width), max(a.height, b.height)
    A = np.zeros((h, w, 3), np.int16)
    B = np.zeros((h, w, 3), np.int16)
    A[: a.height, : a.width] = np.asarray(a)
    B[: b.height, : b.width] = np.asarray(b)
    changed = (np.abs(A - B).max(axis=2) > 24)
    canvas = Image.new("RGB", (a.width + b.width + 20, h), (255, 0, 255))
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.width + 20, 0))
    canvas.save(side)
    return {"changed_pixels": round(float(changed.mean()), 4), "height_a": a.height, "height_b": b.height}


def main():
    from playwright.sync_api import sync_playwright

    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="delivered UI")
    ap.add_argument("--b", required=True, help="integrated UI")
    ap.add_argument("--out", default="outputs/ui_compare")
    ap.add_argument("--routes", default=",".join(ROUTES))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    res = {}
    with sync_playwright() as p:
        for route in a.routes.split(","):
            for vname, size in VIEWPORTS.items():
                for theme in ("light", "dark"):
                    key = f"{route.strip('/').replace('/', '_') or 'home'}__{vname}__{theme}"
                    pa, pb = (os.path.join(a.out, f"{key}__{s}.png") for s in ("delivered", "integrated"))
                    if not (os.path.exists(pa) and os.path.exists(pb)):
                        shoot(p, a.a.rstrip("/"), route, size, theme, pa)
                        shoot(p, a.b.rstrip("/"), route, size, theme, pb)
                    res[key] = diff(pa, pb, os.path.join(a.out, f"{key}__side.png"))
                    print(key, res[key], flush=True)
    with open(os.path.join(a.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
