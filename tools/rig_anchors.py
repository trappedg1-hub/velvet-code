"""
rig_anchors.py — якоря скелета по силуэту спрайта.

Зачем. Спрайт — это картинка, а рантайму нужны точки: где макушка, где плечи,
где бёдра, где щиколотки, куда ставить тень и как посадить героиню на общую
линию пола. Ставить их «на глаз» в коде — значит переделывать каждый раз,
когда меняется кадр.

Метод: альфа-маска даёт силуэт. По строкам считается ширина тела; по ней
находятся характерные уровни:
  - низ (feet_y) и верх (head_top) — крайние непрозрачные строки;
  - бёдра — строка максимальной ширины в нижней половине;
  - плечи — строка максимальной ширины в верхней четверти;
  - талия — минимум ширины между ними;
  - колени и щиколотки — доли роста от низа (анатомически устойчивые).
Всё, что можно измерить, измеряется; доли остаются только там, где силуэт
не даёт ответа (колени в длинном платье).

    python3 tools/rig_anchors.py --all
    python3 tools/rig_anchors.py --name m_selena
"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPRITE = ROOT / "assets" / "sprite"
MANIFEST = SPRITE / "manifest.json"


def measure(img: Image.Image) -> dict:
    a = np.array(img.convert("RGBA"))[:, :, 3]
    mask = a > 127
    rows = np.where(mask.any(axis=1))[0]
    if rows.size == 0:
        raise SystemExit("пустая альфа")
    top, bottom = int(rows[0]), int(rows[-1])
    h = bottom - top + 1
    widths = mask.sum(axis=1).astype(float)

    def row_at(frac: float) -> int:
        return int(round(top + frac * h))

    def width_at(y: int) -> int:
        return int(widths[max(0, min(len(widths) - 1, y))])

    # плечи и бёдра ищем по ширине, а не по доле
    upper = slice(top, row_at(0.30))
    lower = slice(row_at(0.35), row_at(0.65))
    shoulders_y = int(np.argmax(widths[upper])) + top
    hips_y = int(np.argmax(widths[lower])) + row_at(0.35)

    # талия — минимум между ними
    if hips_y - shoulders_y > 10:
        seg = widths[shoulders_y:hips_y]
        waist_y = int(np.argmin(seg)) + shoulders_y
    else:
        waist_y = row_at(0.40)

    return {
        "top": top,
        "bottom": bottom,
        "height_px": h,
        "head_top": top,
        "chin": row_at(0.115),
        "shoulders": shoulders_y,
        "bust": row_at(0.29),
        "waist": waist_y,
        "hips": hips_y,
        "knee": row_at(1.0 - 0.285),
        "ankle": row_at(1.0 - 0.06),
        "feet": bottom,
        "shoulder_width_px": width_at(shoulders_y),
        "hip_width_px": width_at(hips_y),
        "waist_width_px": width_at(waist_y),
    }


def add(name: str) -> dict:
    path = SPRITE / f"{name}.webp"
    if not path.exists():
        raise SystemExit(f"нет спрайта {path}")
    anchors = measure(Image.open(path))
    data = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    entry = data.get(name, {})
    entry["anchors"] = anchors
    data[name] = entry
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"name": name, **anchors}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    if a.all:
        names = sorted(p.stem for p in SPRITE.glob("*.webp"))
        for n in names:
            r = add(n)
            print(f"{n:<12} рост {r['height_px']}px · плечи {r['shoulders']} · талия {r['waist']} · "
                  f"бёдра {r['hips']} · колени {r['knee']} · стопы {r['feet']}")
        return
    if a.name:
        r = add(a.name)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return
    ap.print_help()


if __name__ == "__main__":
    main()
