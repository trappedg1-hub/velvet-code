"""
qa_sprites.py — honest sprite QA.

The first version of this check was wrong and produced a false alarm on all 7
sprites: it measured the *processed* sprite, which `pipeline_sprites.process()`
crops to the alpha bbox — so content always touches all four edges by
construction. Cropping can only be judged on the keyed RAW render, before trim.

Checks (exit code 1 if any sprite fails):
  frame    content must not touch the outermost N px of the RAW image
           -> proves nothing (shoes, hair) was cut off by the render itself
  alpha    silhouette must be a single reasonably solid mass (no green holes)
  aspect   width/height must be plausible for a curvy adult figure (0.20–0.60)
  height   processed sprite normalised to 1200 px
  bytes    < 400 KB (mobile budget)

Usage:  python3 tools/qa_sprites.py [--raw-dir assets/raw] [--sprite-dir assets/sprite]
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pipeline_sprites import key_green  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
EDGE_PX = 3
ASPECT = (0.20, 0.60)


def frame_crop(raw: pathlib.Path) -> list[str]:
    """Which edges of the RAW frame does the subject touch?"""
    a = np.array(key_green(Image.open(raw)))[:, :, 3]
    h, w = a.shape
    bands = {
        "left": a[:, :EDGE_PX], "right": a[:, -EDGE_PX:],
        "top": a[:EDGE_PX, :], "bottom": a[-EDGE_PX:, :],
    }
    return [name for name, band in bands.items() if (band > 8).mean() > 0.001]


def qa_one(raw: pathlib.Path, sprite: pathlib.Path) -> list[str]:
    fails: list[str] = []
    edges = frame_crop(raw)
    if edges:
        fails.append("frame:" + ",".join(edges))

    if not sprite.exists():
        return fails + ["sprite:missing"]
    im = Image.open(sprite)
    if im.height != 1200:
        fails.append(f"height:{im.height}")
    ratio = im.width / im.height
    if not (ASPECT[0] <= ratio <= ASPECT[1]):
        fails.append(f"aspect:{ratio:.2f}")
    if sprite.stat().st_size > 400 * 1024:
        fails.append(f"bytes:{sprite.stat().st_size // 1024}KB")

    a = np.array(im.convert("RGBA"))[:, :, 3]
    solid = (a > 200).mean()
    if solid < 0.10:
        fails.append(f"alpha_holes:{solid:.2f}")
    return fails


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default=str(ROOT / "assets" / "raw"))
    ap.add_argument("--sprite-dir", default=str(ROOT / "assets" / "sprite"))
    a = ap.parse_args()
    raw_dir, sprite_dir = pathlib.Path(a.raw_dir), pathlib.Path(a.sprite_dir)

    rows, bad = [], 0
    for raw in sorted(raw_dir.glob("*_raw.png")):
        name = raw.stem.removesuffix("_raw")
        fails = qa_one(raw, sprite_dir / f"{name}.webp")
        bad += bool(fails)
        rows.append((name, fails))

    width = max((len(n) for n, _ in rows), default=10)
    for name, fails in rows:
        mark = "OK  " if not fails else "FAIL"
        print(f"{mark} {name:<{width}}  {'—' if not fails else ', '.join(fails)}")
    print(f"\n{len(rows) - bad}/{len(rows)} ok")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
