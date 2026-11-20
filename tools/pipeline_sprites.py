"""
pipeline_sprites.py — raw AI render -> game-ready alpha sprite.

Stage 1 of the production pipeline described in docs/02-art-pipeline.md:
  chroma-key  ->  despill  ->  alpha erode  ->  trim/pad  ->  WebP(alpha)

In production this stage is replaced by See-through (layer decomposition)
+ image2live2d (auto-rig). Here we only need a single-sprite cutout.
"""
import base64
import io
import argparse
import json
import pathlib

import numpy as np
from PIL import Image, ImageFilter

RAW = pathlib.Path("assets/raw")
OUT = pathlib.Path("assets/sprite")
OUT.mkdir(parents=True, exist_ok=True)


def key_green(img: Image.Image) -> Image.Image:
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]

    # greenness: how much the green channel dominates
    key = g - np.maximum(r, b)

    # soft matte: fully opaque below LO, fully transparent above HI
    LO, HI = 12.0, 62.0
    alpha = np.clip(1.0 - (key - LO) / (HI - LO), 0.0, 1.0)

    # despill: kill green fringing on semi-transparent edge pixels
    edge = (alpha < 0.995)
    cap = np.maximum(r, b) + 14.0
    g_despilled = np.where(edge, np.minimum(g, cap), g)

    out = np.stack([r, g_despilled, b], axis=-1)
    out = np.clip(out, 0, 255).astype(np.uint8)
    a = (alpha * 255).astype(np.uint8)
    return Image.fromarray(np.dstack([out, a]), mode="RGBA")


def erode_alpha(img: Image.Image, px: int = 1) -> Image.Image:
    """Shrink the matte slightly so no green halo survives on dark backgrounds."""
    if px <= 0:
        return img
    a = img.getchannel("A").filter(ImageFilter.MinFilter(px * 2 + 1))
    img = img.copy()
    img.putalpha(a)
    return img


def _repair(img: Image.Image) -> tuple[Image.Image, dict]:
    """Прогнать через artifact_repair: деспилл, дырки, точки, кайма, резкость.

    Порядок из artifact_repair, а не «сначала эрозия»: эрозия по несжатому
    матту съедает волосы и тонкие ремешки, а деспилл до неё их сохраняет.
    """
    try:
        import artifact_repair as ar
        rgba = np.array(img)
        bgr = cv2 if False else None
        import cv2
        bgr_img = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2BGR)
        fixed, alpha, log = ar.repair(bgr_img, rgba[:, :, 3])
        out = cv2.cvtColor(fixed, cv2.COLOR_BGR2RGB)
        return Image.fromarray(np.dstack([out, alpha]), mode="RGBA"), log
    except Exception as exc:  # без инструмента остаёмся на старом поведении
        return img, {"repair": f"пропущен: {exc}"}


def process(name: str, target_h: int = 1200) -> dict:
    src = Image.open(RAW / f"{name}_raw.png")
    img = key_green(src)
    img, repairlog = _repair(img)
    img = erode_alpha(img, 1)

    bbox = img.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    img = img.crop(bbox)

    w, h = img.size
    scale = target_h / h
    img = img.resize((max(1, round(w * scale)), target_h), Image.LANCZOS)

    dst = OUT / f"{name}.webp"
    img.save(dst, "WEBP", quality=88, method=6, exact=True)

    # anchor metadata: where the eyes/feet sit, used by the rig in the game
    return {
        "name": name,
        "repair": repairlog,
        "file": str(dst),
        "width": img.width,
        "height": img.height,
        "bytes": dst.stat().st_size,
    }


MANIFEST = OUT / "manifest.json"


def _load_manifest() -> dict[str, dict]:
    """Манифест — словарь по имени. Раньше он перезаписывался целиком, и один
    прогон по двум героиням стирал индекс остальных. Теперь — только слияние."""
    if not MANIFEST.exists():
        return {}
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(data, dict):
        return data
    return {m["name"]: m for m in data if isinstance(m, dict) and "name" in m}


def _save_manifest(entries: dict[str, dict]) -> None:
    MANIFEST.write_text(json.dumps(dict(sorted(entries.items())), ensure_ascii=False, indent=2),
                        encoding="utf-8")


def _rebuild_index() -> dict[str, dict]:
    """Пересобрать записи по фактическим файлам, сохранив якоря из старого индекса.

    Якоря считает отдельный инструмент (rig_anchors), и терять их при
    переиндексации нельзя: иначе срез остаётся без точек скелета.
    """
    previous = _load_manifest()
    entries = {}
    for webp in sorted(OUT.glob("*.webp")):
        try:
            with Image.open(webp) as im:
                w, h = im.size
        except Exception:
            continue
        entry = {"name": webp.stem, "file": str(webp),
                 "width": w, "height": h, "bytes": webp.stat().st_size}
        if (previous.get(webp.stem) or {}).get("anchors"):
            entry["anchors"] = previous[webp.stem]["anchors"]
        entries[webp.stem] = entry
    return entries


def main() -> None:
    ap = argparse.ArgumentParser(description="сырой рендер → спрайт с альфой")
    ap.add_argument("names", nargs="*", help="имена без _raw.png; пусто = все")
    ap.add_argument("--name", action="append", default=[], help="то же, флагом (можно повторять)")
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument("--reindex", action="store_true", help="пересобрать манифест по файлам")
    a = ap.parse_args()

    if a.reindex:
        entries = _rebuild_index()
        _save_manifest(entries)
        print(f"манифест пересобран по файлам: {len(entries)} записей")
        for n in entries:
            print(f"  {n}")
        return

    names = a.names + a.name
    if not names:
        names = sorted(f.stem.removesuffix("_raw") for f in RAW.glob("*_raw.png"))
    entries = _load_manifest()
    for n in names:
        meta = process(n, a.height)
        entries[meta["name"]] = meta
        print(f"{meta['name']:14s} {meta['width']}x{meta['height']}  {meta['bytes']/1024:.0f} KB")
    _save_manifest(entries)
    print(f"манифест: {len(entries)} записей")


if __name__ == "__main__":
    main()
