"""
artifact_repair.py — поиск и лечение артефактов спрайта.

Что реально портит кадр на хромакее и в мелком вебе:

  spill      — зелёный налёт на волосах, плече, светлой ткани: самый заметный
               дефект, потому что кожа рядом и глаз ловит разницу;
  fringe     — полупрозрачная кайма по контуру после кеинга;
  specks     — одиночные точки и «острова» фона внутри силуэта (и наоборот);
  holes      — дырки в альфе (волосы, между пальцами, тонкие ремешки);
  halo       — светлая или тёмная обводка вокруг фигуры;
  edge_cut   — силуэт прилип к краю кадра (обрезанная рука, стопа);
  blockiness — следы JPEG и шум в ровных областях (кожа, ткань);
  softness   — кадр «мыльный»: линия не читается.

Каждый дефект измеряется числом, лечится отдельным шагом и попадает в отчёт.
Порядок лечения важен и потому зашит в код: деспилл → матирование → дырки →
точки → кайма → резкость. Если лечить в другом порядке, шаги портят друг друга.

    python3 tools/artifact_repair.py --report assets/raw/b_selena_raw.png
    python3 tools/artifact_repair.py --fix assets/raw/b_selena_raw.png \
        --out assets/sprite/b_selena_clean.webp
    python3 tools/artifact_repair.py --fix-all assets/raw --out-dir assets/sprite
"""
from __future__ import annotations

import argparse
import json
import pathlib

import cv2
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Пороги подобраны под наши рендеры 864–1200 px по высоте.
# fringe меряется как ДОЛЯ ЗЕЛЁНЫХ пикселей на контуре, а не «полупрозрачных»:
# полупрозрачный край — это нормальное сглаживание, а зелёный — дефект кеинга.
THRESHOLDS = {
    "spill": 1.5,        # % пикселей тела с зелёным налётом
    "fringe": 8.0,       # % зелёных пикселей на контуре
    "residue": 1.0,      # % полупрозрачных зелёных остатков вне тела
    "specks": 25,        # количество мелких островов
    "holes": 12,         # количество дырок в альфе
    "edge_cut": 0,       # пикселей силуэта на границе кадра
    "blockiness": 14.0,  # индекс блочности
    "softness": 55.0,    # дисперсия лапласиана: ниже — мыло
}


def load(path: pathlib.Path) -> tuple[np.ndarray, np.ndarray]:
    """BGR + альфа. Зелёный фон вырезается по хроме, если альфы нет."""
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise SystemExit(f"не читается: {path}")
    if img.shape[2] == 4:
        return img[:, :, :3], img[:, :, 3]
    b, g, r = cv2.split(img)
    # хромакей: зелёный доминирует
    mask = ((g.astype(np.int16) - np.maximum(r, b).astype(np.int16)) > 40).astype(np.uint8) * 255
    alpha = cv2.bitwise_not(mask)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
    return img, alpha


def _components(mask: np.ndarray) -> list[int]:
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    return [int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, n)]


def measure(bgr: np.ndarray, alpha: np.ndarray) -> dict:
    """Измерить все дефекты. Возвращает числа, не вердикты."""
    h, w = alpha.shape
    body = alpha > 127
    body_area = max(int(body.sum()), 1)

    g = bgr[:, :, 1].astype(np.int16)
    r = bgr[:, :, 0].astype(np.int16)
    b = bgr[:, :, 2].astype(np.int16)
    greenish = (g - np.maximum(r, b)) > 18

    visible = body & (alpha > 200)
    spill = float((visible & greenish).sum()) / max(int(visible.sum()), 1) * 100

    er = cv2.erode(body.astype(np.uint8), np.ones((3, 3), np.uint8))
    edge = body & ~er.astype(bool)
    fringe = float((edge & greenish).sum()) / max(int(edge.sum()), 1) * 100

    # остатки кеинга: полупрозрачные зелёные пиксели вне тела
    residue_mask = (~body) & (alpha > 8) & (alpha < 200) & greenish
    residue = float(residue_mask.sum()) / (alpha.size) * 100

    holes_mask = (~body).astype(np.uint8)
    holes = [a for a in _components(holes_mask) if 6 <= a <= body_area * 0.002]
    specks = [a for a in _components(body.astype(np.uint8)) if a <= body_area * 0.0008]

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)

    # обрезанный силуэт
    border = np.zeros_like(body)
    border[:2, :] = border[-2:, :] = border[:, :2] = border[:, -2:] = True
    edge_cut = int((body & border).sum())

    # блочность JPEG: разница между соседними пикселями на границах блоков 8x8
    # блочность: считаем только там, где есть тело, иначе фон даёт ложный ноль
    dh = np.abs(np.diff(gray, axis=1))
    dv = np.abs(np.diff(gray, axis=0))
    body_c = body[:, 1:] & body[:, :-1]
    body_r = body[1:, :] & body[:-1, :]
    blockiness = float((dh[body_c].mean() if body_c.any() else 0)
                       + (dv[body_r].mean() if body_r.any() else 0))

    softness = float(cv2.Laplacian(gray, cv2.CV_32F)[body].var()) if body.any() else 0.0

    return {
        "size": [int(w), int(h)],
        "body_share": round(body_area / (w * h) * 100, 1),
        "spill": round(spill, 2),
        "fringe": round(fringe, 2),
        "residue": round(residue, 3),
        "specks": len(specks),
        "holes": len(holes),
        "edge_cut": edge_cut,
        "blockiness": round(blockiness, 2),
        "softness": round(softness, 1),
    }


def verdict(m: dict) -> list[str]:
    bad = []
    if m["spill"] > THRESHOLDS["spill"]:
        bad.append(f"spill {m['spill']}% > {THRESHOLDS['spill']}% — зелёный налёт на коже и волосах")
    if m["fringe"] > THRESHOLDS["fringe"]:
        bad.append(f"fringe {m['fringe']}% — кайма по контуру")
    if m["specks"] > THRESHOLDS["specks"]:
        bad.append(f"specks {m['specks']} — острова фона")
    if m["holes"] > THRESHOLDS["holes"]:
        bad.append(f"holes {m['holes']} — дырки в альфе")
    if m["residue"] > THRESHOLDS["residue"]:
        bad.append(f"residue {m['residue']}% — полупрозрачные зелёные остатки кеинга")
    if m["edge_cut"] > THRESHOLDS["edge_cut"]:
        bad.append(f"edge_cut {m['edge_cut']} px — силуэт упёрся в край, кадр обрезан")
    if m["softness"] < THRESHOLDS["softness"]:
        bad.append(f"softness {m['softness']} < {THRESHOLDS['softness']} — кадр мыльный")
    return bad


def repair(bgr: np.ndarray, alpha: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """Вылечить в правильном порядке. Возвращает изображение, альфу и лог шагов."""
    log = {}
    body = (alpha > 127).astype(np.uint8)

    # 1) деспилл: зелёный канал придавливается к максимуму R/B
    img = bgr.astype(np.float32)
    g = img[:, :, 1]
    lim = np.maximum(img[:, :, 0], img[:, :, 2])
    over = np.clip(g - lim, 0, None)
    g_new = g - over * 0.92
    img[:, :, 1] = g_new
    log["despill"] = round(float(over.mean()), 3)

    # 2) матирование: чистка альфы от мусора и мелких островов
    a = alpha.copy()
    a = cv2.morphologyEx(a, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    a = cv2.medianBlur(a, 5)

    # 3) дырки: закрывать ТОЛЬКО мелкие разрывы (между пальцами, в тонких
    # ремешках). Крупные просветы — это настоящий фон: между рукой и телом,
    # между ног. Если залить их «по внешнему контуру», получится чёрная плита,
    # что и случилось в первой версии.
    body2 = (a > 127).astype(np.uint8)
    holes_mask = (1 - body2).astype(np.uint8)
    cnts, _ = cv2.findContours(holes_mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    area_body = int(body2.sum())
    # порог: и доля от тела, и абсолютный минимум — иначе на маленьких
    # спрайтах не закрывается ни одна дырка, а на больших закрываются просветы
    limit = max(400.0, area_body * 0.0015)
    filled_px, filled_n = 0, 0
    pad = np.zeros_like(body2)
    for c in cnts:
        area = cv2.contourArea(c)
        if area <= 0 or area > limit:
            continue  # крупные просветы не трогаем
        # дырка должна быть окружена телом, а не примыкать к краю кадра
        x, y, w, h = cv2.boundingRect(c)
        if x <= 1 or y <= 1 or x + w >= a.shape[1] - 1 or y + h >= a.shape[0] - 1:
            continue
        cv2.drawContours(pad, [c], -1, 1, thickness=-1)
        filled_n += 1
    filled_px = int(pad.sum())
    a = np.where(pad == 1, np.maximum(a, 245), a)
    log["holes_filled_n"] = filled_n
    log["holes_filled_px"] = filled_px

    # 4) точки: убрать всё, что меньше 0.05% площади
    n, lab, stats, _ = cv2.connectedComponentsWithStats((a > 127).astype(np.uint8), 8)
    keep = np.zeros_like(a)
    total = max(int((a > 127).sum()), 1)
    removed = 0
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= total * 0.0005:
            keep[lab == i] = a[lab == i]
        else:
            removed += 1
    a = keep
    log["specks_removed"] = removed

    # 5) кайма: лёгкое сглаживание края без потери силуэта
    a = cv2.GaussianBlur(a, (3, 3), 0.6)
    a = np.where(a > 250, 255, a).astype(np.uint8)

    # 6) резкость по телу: линия должна читаться
    out = img.astype(np.uint8)
    blur = cv2.GaussianBlur(out, (0, 0), 1.1)
    out = cv2.addWeighted(out, 1.35, blur, -0.35, 0)
    log["unsharp"] = 0.35

    # 7) финальный деспилл: после резкости зелёный снова подрастает на контуре
    fin = out.astype(np.float32)
    lim2 = np.maximum(fin[:, :, 0], fin[:, :, 2])
    over2 = np.clip(fin[:, :, 1] - lim2, 0, None)
    fin[:, :, 1] -= over2
    out = fin.astype(np.uint8)
    log["despill_final"] = round(float(over2.mean()), 3)

    return out, a, log


def save(path: pathlib.Path, bgr: np.ndarray, alpha: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = alpha
    if path.suffix.lower() == ".webp":
        cv2.imwrite(str(path), rgba, [cv2.IMWRITE_WEBP_QUALITY, 92])
    else:
        cv2.imwrite(str(path), rgba)


def process(src: pathlib.Path, out: pathlib.Path | None = None) -> dict:
    bgr, alpha = load(src)
    before = measure(bgr, alpha)
    fixed, a2, log = repair(bgr, alpha)
    after = measure(fixed, a2)
    if out:
        save(out, fixed, a2)
    return {"source": str(src.name), "before": before, "after": after,
            "bad_before": verdict(before), "bad_after": verdict(after), "steps": log,
            "out": str(out) if out else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", metavar="PNG")
    ap.add_argument("--fix", metavar="PNG")
    ap.add_argument("--out", metavar="PATH")
    ap.add_argument("--fix-all", metavar="DIR")
    ap.add_argument("--out-dir", default="assets/sprite")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.fix_all:
        src_dir = pathlib.Path(a.fix_all)
        out_dir = pathlib.Path(a.out_dir)
        rows = []
        for f in sorted(src_dir.glob("*_raw.png")):
            target = out_dir / (f.stem.replace("_raw", "") + "_clean.webp")
            rows.append(process(f, target))
        for r in rows:
            print(f"{r['source']}: spill {r['before']['spill']}% → {r['after']['spill']}% · "
                  f"точек {r['before']['specks']} → {r['after']['specks']} · "
                  f"дырок {r['before']['holes']} → {r['after']['holes']} · "
                  f"резкость {r['before']['softness']} → {r['after']['softness']}")
            for b in r["bad_after"]:
                print(f"    осталось: {b}")
        print(f"\nготово: {len(rows)} файлов → {out_dir}")
        return

    src = a.fix or a.report
    if not src:
        ap.error("нужен --report, --fix или --fix-all")
    out = pathlib.Path(a.out) if (a.fix and a.out) else None
    res = process(pathlib.Path(src), out)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return
    print(f"{res['source']}  {res['before']['size'][0]}×{res['before']['size'][1]}")
    for k in ("spill", "fringe", "residue", "specks", "holes", "edge_cut", "blockiness", "softness"):
        b, aft = res["before"][k], res["after"][k]
        mark = "→" if b != aft else " "
        print(f"  {k:<11} {b:>8} {mark} {aft:>8}")
    print("  дефекты до:", "; ".join(res["bad_before"]) or "нет")
    print("  дефекты после:", "; ".join(res["bad_after"]) or "нет")
    if res["out"]:
        print("  сохранено:", res["out"])


if __name__ == "__main__":
    main()
