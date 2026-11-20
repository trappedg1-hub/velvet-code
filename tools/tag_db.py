"""
tag_db.py — локальная база тегов Danbooru с частотами.

Зачем: промпт «из головы» даёт усреднённый результат, потому что модель
взвешивает теги по их частоте в обучении. Полезно видеть эту частоту и выбирать
теги осознанно: `blush` (3.6M постов) работает иначе, чем редкий тег на 800 постов.

Данные: `assets/tags/{feature,action,expression,attire,style}.csv` — выгрузка
классифицированных тегов Danbooru (tag,count), ~10 тысяч строк.
Схема категорий: feature (тело/лицо/волосы) · action (позы/действия) ·
expression (эмоции) · attire (одежда) · style (художественные стили).

Команды:
    python3 tools/tag_db.py --top action 25
    python3 tools/tag_db.py --search thigh
    python3 tools/tag_db.py --search breast --cat feature --limit 30
    python3 tools/tag_db.py --export          # пересобрать wildcards из реальных данных
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TAGS = ROOT / "assets" / "tags"
WILD = ROOT / "assets" / "wildcards"
CATS = ("feature", "action", "expression", "attire", "style")

_cache: dict[str, list[tuple[str, int]]] = {}


def load(cat: str) -> list[tuple[str, int]]:
    if cat in _cache:
        return _cache[cat]
    path = TAGS / f"{cat}.csv"
    if not path.exists():
        raise FileNotFoundError(f"нет файла тегов: {path} (см. docs/13, раздел «данные»)")
    rows: list[tuple[str, int]] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                rows.append((row["tag"].strip(), int(row["count"])))
            except (KeyError, ValueError):
                continue
    rows.sort(key=lambda r: -r[1])
    _cache[cat] = rows
    return rows


def search(query: str, cat: str | None = None, limit: int = 20) -> list[tuple[str, int, str]]:
    q = query.lower().replace("_", " ")
    out: list[tuple[str, int, str]] = []
    for c in ([cat] if cat else CATS):
        for tag, count in load(c):
            if q in tag.replace("_", " "):
                out.append((tag, count, c))
    out.sort(key=lambda r: -r[1])
    return out[:limit]


def top(cat: str, n: int = 20) -> list[tuple[str, int]]:
    return load(cat)[:n]


# --- экспорт wildcards из реальных данных -----------------------------------
# Отбираем не «топ по частоте», а ОСМЫСЛЕННЫЕ строки: символьные теги (":d"),
# имена артистов и мусор отбрасываем, остальное фильтруем по смыслу.
EXPR_KEEP = ("blush", "smile", "parted lips", "open mouth", "closed eyes", "half-closed eyes",
             "light smile", "smirk", "grin", "tongue out", "sweatdrop", "heavy breathing",
             "one eye closed", "naughty face", "seductive smile", "looking down", "looking up",
             "eye contact", "empty eyes", "teary eyes", "embarrassed")
ACTION_KEEP = ("sitting", "standing", "leaning forward", "leaning back", "on side", "on stomach",
               "crossed legs", "legs together", "legs apart", "kneeling", "squatting", "tiptoes",
               "walking", "running", "jumping", "arched back", "head tilt", "hand on own hip",
               "hand on own thigh", "hand on own chest", "arms behind back", "stretching",
               "bent over", "looking over shoulder", "crouching", "sitting on chair",
               "feet up", "foot focus", "presenting foot", "spread legs", "clothed")
ATTIRE_KEEP = ("mini skirt", "pencil skirt", "pantyhose", "thighhighs", "garter straps",
               "leotard", "bandeau", "tube top", "crop top", "off-shoulder", "backless",
               "see-through", "wet clothes", "torn clothes", "underwear", "lace",
               "high heels", "stiletto heels", "boots", "knee boots", "loafers", "glasses",
               "choker", "necklace", "earrings", "belt", "vest", "suit")


def _select(cat: str, wanted: tuple[str, ...], min_count: int = 400) -> list[str]:
    pool = {t.replace("_", " "): c for t, c in load(cat)}
    picked = [w for w in wanted if pool.get(w, 0) >= min_count]
    return picked


# --- атлас явной лексики -----------------------------------------------------
# Группы собраны по смыслу, но ЧАСТОТЫ берутся из реальных данных: видно, что
# массово, а что ниша. Это и есть «база NSFW-промптов», проверяемая цифрами.
ATLAS = {
    "act_solo": ("masturbation", "spread legs", "presenting", "presenting pussy", "legs up",
                 "knees up", "on back", "top-down bottom-up", "against wall"),
    "act_pair": ("sex", "vaginal", "sex from behind", "cowgirl position", "missionary",
                 "girl on top", "standing sex", "group sex", "fellatio", "paizuri",
                 "handjob", "all fours", "bent over", "straddling"),
    "fluids": ("cum", "cum in pussy", "cum on body", "cum on breasts", "facial",
               "ejaculation", "sweat", "drooling", "saliva", "tears"),
    "body_explicit": ("nude", "completely nude", "nipples", "areolae", "pussy", "anus",
                      "ass", "cleavage", "underboob", "sideboob", "spread pussy"),
    "clothing_state": ("clothed", "partially undressed", "clothes lift", "bra lift",
                       "panties aside", "torn clothes", "wet clothes", "see-through",
                       "undressing", "shirt lift", "skirt lift"),
    "fetish_feet": ("foot focus", "presenting foot", "barefoot", "soles", "toes",
                    "footjob", "toe rings", "anklet", "high heels", "stiletto heels",
                    "shoe dangle", "pantyhose feet"),
    "restraint_pressure": ("restrained", "bound wrists", "against wall", "pinned",
                           "holding wrists", "forced", "struggling", "crying"),
    "face_heat": ("blush", "parted lips", "half-closed eyes", "heavy breathing",
                  "tongue out", "naughty face", "seductive smile", "ahegao",
                  "looking down at viewer", "eye contact"),
}


def atlas() -> dict[str, list[tuple[str, int]]]:
    """Явные темы с реальными частотами. Тег, которого нет в данных, — не выдумываем."""
    pool: dict[str, int] = {}
    for cat in ("action", "attire", "feature", "expression", "other"):
        try:
            pool.update({t.replace("_", " "): c for t, c in load(cat)})
        except FileNotFoundError:
            continue
    out: dict[str, list[tuple[str, int]]] = {}
    for group, wanted in ATLAS.items():
        rows = [(w, pool[w]) for w in wanted if w in pool]
        rows.sort(key=lambda r: -r[1])
        out[group] = rows
    return out


def export_wildcards() -> dict[str, int]:
    WILD.mkdir(parents=True, exist_ok=True)
    sets = {
        "db_expressions.txt": _select("expression", EXPR_KEEP, 1000),
        "db_actions.txt": _select("action", ACTION_KEEP, 300),
        "db_attire.txt": _select("attire", ATTIRE_KEEP, 200),
    }
    counts = {}
    for name, lines in sets.items():
        (WILD / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        counts[name] = len(lines)
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top")
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--search")
    ap.add_argument("--cat", choices=CATS)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--atlas", action="store_true")
    a = ap.parse_args()

    if a.atlas:
        data = atlas()
        (TAGS / "atlas.json").write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
        WILD.mkdir(parents=True, exist_ok=True)
        for group, rows in data.items():
            (WILD / f"atlas_{group}.txt").write_text("\n".join(t for t, _ in rows) + "\n",
                                                     encoding="utf-8")
            print(f"{group}: {len(rows)} тегов")
            for t, c in rows[:4]:
                print(f"    {c:>9}  {t}")
        print(f"→ assets/tags/atlas.json + assets/wildcards/atlas_*.txt")
        return
    if a.export:
        for name, n in export_wildcards().items():
            print(f"{name}: {n} строк из реальных тегов")
        return
    if a.search:
        for tag, count, cat in search(a.search, a.cat, a.limit):
            print(f"{count:>9}  {cat:<11} {tag}")
        return
    if a.top:
        for tag, count in top(a.top, a.n):
            print(f"{count:>9}  {tag}")
        return
    ap.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
