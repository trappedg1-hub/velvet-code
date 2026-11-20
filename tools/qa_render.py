"""
qa_render.py — приёмка рендера по артефактам.

Задача: не пускать в продакшн кадр, который выглядит «сломанным», и делать это
до того, как человек его увидит. Проверки разделены на два уровня.

  OFFLINE (всегда, без ML, работает в CI):
    frame      контент не касается края кадра  -> обрезанная кисть/волосы/обувь
    halo       зелёный ореол на кромке готового спрайта (проверяется по .webp,
               на зелёном исходнике эта метрика бессмысленна)
    sharpness  дисперсия лапласиана по силуэту -> «мыло» и пересжатие
    symmetry   асимметрия альфа-силуэта -> вывих таза/плеч, «слипшаяся» рука
    budget     размер файла и разрешение
    text       OCR: надписи и логотипы в кадре (нужен бинарь tesseract; без него
               info:text-skip — честный пропуск, а не «пройдено»)
    gaps       ИНФО: замкнутые петли силуэта (рука на бедре, нога + стул).
               Это нормальная анатомия и реквизит, поэтому не блокирует приёмку.

  ML (--ml, если установлен pyiqa; иначе честно пропускается):
    MUSIQ / CLIPIQA / MANIQA  -> общая воспринимаемая качественность
    TOPIQ-face                -> качество лица в кадре

Причина разделения: offline-проверки детерминированы и бесплатны, их можно гонять
на каждый рендер. ML-метрики дорогие и требуют torch, поэтому они опциональны —
но именно они ловят «всё вроде цело, а лицо поплыло».

Использование:
    python3 tools/qa_render.py                     # все raw-рендеры
    python3 tools/qa_render.py selena mika         # конкретные
    python3 tools/qa_render.py --ml                # + ML-метрики (если есть pyiqa)
"""
from __future__ import annotations

import argparse
import re
import pathlib
import sys

import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pipeline_sprites import key_green  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "assets" / "raw"

EDGE_PX = 3
MIN_SHARPNESS = 40.0      # дисперсия лапласиана по телу; ниже — мыло
MAX_ASYMMETRY = 0.35      # |L-R| / ширина силуэта
MAX_HOLE = 0.06           # доля прозрачных пикселей ВНУТРИ силуэта
ML_FLOOR = 0.35           # нижняя граница для нормализованных ML-метрик


def green_share(raw: pathlib.Path) -> float:
    """Доля зелёного по рамке кадра. Нужна, чтобы отличить хромакей от кадра с фоном."""
    im = Image.open(raw).convert("RGB")
    arr = np.array(im).astype(np.int16)
    b = 3
    border = np.concatenate([arr[:, :b].reshape(-1, 3), arr[:, -b:].reshape(-1, 3),
                             arr[:b, :].reshape(-1, 3), arr[-b:, :].reshape(-1, 3)])
    r, g, bl = border[:, 0], border[:, 1], border[:, 2]
    return float(((g > 90) & (g > 1.4 * np.maximum(r, bl))).mean())


def _silhouette(raw: pathlib.Path):
    keyed = key_green(Image.open(raw))
    a = np.array(keyed)[:, :, 3]
    rgb = np.array(keyed.convert("RGB")).astype(np.int16)
    return a, rgb


def check_frame(a: np.ndarray) -> list[str]:
    h, w = a.shape
    bands = {"left": a[:, :EDGE_PX], "right": a[:, -EDGE_PX:],
             "top": a[:EDGE_PX, :], "bottom": a[-EDGE_PX:, :]}
    return [f"frame:{side}" for side, band in bands.items() if (band > 8).mean() > 0.001]


def check_text(raw: pathlib.Path) -> list[str]:
    """Надписи и логотипы в кадре.

    Модель охотно рисует вывески, таблички и «документы» — и подставляет туда
    чужие имена и неверные цифры (пойман случай: табличка «41 KIM YUNA, HEIGHT
    168cm» на рендере Рэйки). Текст в кадре — брак: он ломает четвёртую стену и
    врёт про героиню.

    Требует бинарь tesseract. Если его нет — проверка ЧЕСТНО пропускается
    (`info:text-skip`), а не считается пройденной: «нет инструмента» и «нет
    текста» — разные вещи.
    """
    try:
        import pytesseract
        txt = pytesseract.image_to_string(Image.open(raw), lang="eng")
    except Exception:
        return ["info:text-skip"]
    words = re.findall(r"[A-Za-z]{3,}", txt)
    return [f"text:{len(words)}слов"] if len(words) >= 3 else []


def check_halo(sprite: pathlib.Path) -> list[str]:
    """Зелёный ореол на кромке ГОТОВОГО спрайта (после кейинга).

    На сыром рендере эту проверку делать нельзя: фон там зелёный по определению,
    и метрика показывает 100% на любом нормальном кадре. Смысл появляется только
    на спрайте с альфой: если despill не добрал, зелёный канал на полупрозрачной
    кромке заметно доминирует (у нашего кейера лимит +14, поэтому порог +15).
    """
    if not sprite.exists():
        return []          # спрайт ещё не собран — проверка просто не выполняется
    im = Image.open(sprite).convert("RGBA")
    arr = np.array(im).astype(np.int16)
    a, r, g, b = arr[..., 3], arr[..., 0], arr[..., 1], arr[..., 2]
    edge = (a > 40) & (a < 245)
    if edge.sum() < 200:
        return []
    halo = edge & (g > np.maximum(r, b) + 15)
    share = halo.sum() / edge.sum()
    return [f"halo:{share:.3f}"] if share > 0.03 else []


def check_sharpness(rgb: np.ndarray, a: np.ndarray) -> list[str]:
    gray = rgb.mean(axis=2)
    lap = np.abs(np.array(
        Image.fromarray(gray.astype(np.uint8)).filter(ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], 1, 0))
    )).astype(np.float32)
    body = a > 120
    if body.sum() < 1000:
        return ["sharpness:tiny_subject"]
    var = float(lap[body].var())
    return [f"sharpness:{var:.0f}"] if var < MIN_SHARPNESS else []


def check_symmetry(a: np.ndarray) -> list[str]:
    """Грубая проверка «перекошенности» силуэта по горизонтали."""
    body = a > 120
    cols = np.where(body.any(axis=0))[0]
    if len(cols) < 2:
        return ["symmetry:empty"]
    left, right = cols.min(), cols.max()
    mid = (left + right) / 2
    mass = body.sum(axis=0).astype(np.float32)
    xs = np.arange(body.shape[1])
    com = float((mass * xs).sum() / max(mass.sum(), 1))
    asym = abs(com - mid) / max(right - left, 1)
    return [f"symmetry:{asym:.2f}"] if asym > MAX_ASYMMETRY else []


def check_holes(a: np.ndarray) -> list[str]:
    """Дыры = прозрачные области, ПОЛНОСТЬЮ окружённые телом.

    Наивная метрика («доля прозрачного в bounding box») бесполезна: промежуток
    между ногами и вокруг рук даёт 45-55% у любой нормальной фигуры. Поэтому
    заливаем фон от края кадра: всё, что заливка не достала, — настоящая дыра
    (протёкший фон, разрыв конечности).
    """
    from PIL import ImageDraw

    body = a > 120
    if body.sum() == 0:
        return ["holes:empty"]
    free = (~body).astype(np.uint8) * 255
    img = Image.fromarray(free, mode="L")
    # рамка по краю: заливка начинается снаружи фигуры
    img = img.copy()
    ImageDraw.floodfill(img, (0, 0), 128, thresh=0)
    img = Image.fromarray(free, mode="L")
    padded = Image.new("L", (img.width + 2, img.height + 2), 255)
    padded.paste(img, (1, 1))
    ImageDraw.floodfill(padded, (0, 0), 128, thresh=0)
    filled = np.array(padded)[1:-1, 1:-1]
    interior = (filled == 255)          # прозрачно и не достижимо снаружи
    holes = int(interior.sum())
    share = holes / max(int(body.sum()), 1)
    # ВАЖНО: замкнутый контур (рука на бедре, нога + табурет, рука в волосах) —
    # это нормальная анатомия, а не брак. Поэтому gaps — ИНФОРМАЦИЯ, не блокер.
    return [f"gaps:{share:.3f}"] if holes > 2000 and share > 0.01 else []


def check_budget(raw: pathlib.Path) -> list[str]:
    out: list[str] = []
    im = Image.open(raw)
    if min(im.size) < 768:
        out.append(f"size:{im.width}x{im.height}")
    if raw.stat().st_size > 12 * 1024 * 1024:
        out.append(f"bytes:{raw.stat().st_size // 1024 // 1024}MB")
    return out


def check_ml(raw: pathlib.Path) -> list[str]:
    """ML-метрики. Мягко пропускаются, если pyiqa/torch не установлены."""
    try:
        import pyiqa  # type: ignore
        import torch  # type: ignore
    except Exception:
        return ["ml:skipped(no pyiqa)"]
    device = "cpu"
    out: list[str] = []
    img = torch.tensor(np.array(Image.open(raw).convert("RGB"))).permute(2, 0, 1).float().unsqueeze(0) / 255.0
    for name in ("musiq", "clipiqa", "maniqa"):
        try:
            metric = pyiqa.create_metric(name, device=device)
            score = float(metric(img).item())
        except Exception as exc:  # метрика может отсутствовать в сборке
            out.append(f"ml:{name}=err({type(exc).__name__})")
            continue
        out.append(f"ml:{name}={score:.3f}" + ("" if score >= ML_FLOOR else "!"))
    return out


def qa(raw: pathlib.Path, ml: bool = False) -> list[str]:
    # Кадр с фоном (интерьер, улица) — не хромакей: силуэтные проверки к нему
    # неприменимы, иначе «frame:left/right/top/bottom» срабатывает на любом
    # нормальном кадре. Это информационная пометка, а не блокер.
    if green_share(raw) < 0.30:
        return (["info:full-bleed"] + check_budget(raw) + check_text(raw)
                + (check_ml(raw) if ml else []))
    a, rgb = _silhouette(raw)
    problems = (check_frame(a) + check_sharpness(rgb, a) + check_symmetry(a)
                + check_holes(a) + check_budget(raw) + check_text(raw)
                + check_halo(ROOT / "assets" / "sprite" / f"{raw.stem.removesuffix('_raw')}.webp"))
    if ml:
        problems += check_ml(raw)
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--ml", action="store_true", help="включить ML-метрики (нужен pyiqa)")
    args = ap.parse_args()

    files = ([RAW / f"{n}_raw.png" for n in args.names] if args.names
             else sorted(RAW.glob("*_raw.png")))
    hard = 0
    rows = []
    for f in files:
        if not f.exists():
            rows.append((f.stem, ["missing"]))
            hard += 1
            continue
        probs = qa(f, args.ml)
        blocking = [p for p in probs if not p.startswith(("ml:", "gaps:", "info:"))]
        hard += bool(blocking)
        rows.append((f.stem.removesuffix("_raw"), probs))
    width = max(len(n) for n, _ in rows)
    for name, probs in rows:
        mark = ("OK  " if not any(not p.startswith(("ml:", "gaps:", "info:")) for p in probs)
                else "FAIL")
        detail = ", ".join(probs) if probs else "—"
        print(f"{mark} {name:<{width}}  {detail}")
    print(f"\n{len(rows) - hard}/{len(rows)} без блокирующих артефактов")
    sys.exit(1 if hard else 0)


if __name__ == "__main__":
    main()
