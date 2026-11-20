"""
neg_audit.py — негативный промпт, который сам себя блокирует.

Проблема, которую этот инструмент решает, звучит на форумах как «модель
отказывается рисовать кожу». Причины обычно две, и обе лежат в негативе:

1. ТЕКСТОВЫЙ САБОТАЖ. В негатив попадают слова `nsfw`, `nude`, `naked`,
   `nudity`, `explicit`, `censored` (в смысле «не показывай цензуру» его как раз
   ставят, но рядом с nude оно тянет кожу вниз). Это не безобидно: в SD
   негативный промпт — это concept suppression, он вычитает понятие из
   результата. Сообщество применяет это сознательно в обратную сторону:
   чтобы НЕ получить наготу, ставят `(NSFW, naked, nude, nudity:1.8)`
   (обсуждение в lllyasviel/Fooocus #3265). Значит те же слова в нашем
   негативе вычитают то, что нам нужно.

2. ЭМБЕДДИНГ-САБОТАЖ. Готовые negative-эмбеддинги (EasyNegative, bad_prompt v2,
   DeepNegative и родня) обучены на «плохих» картинках и содержат десятки
   токенов; у части внутри есть `nsfw/nude`, и они глушат кожу сильнее, чем
   отдельные слова. Инструменты инспекции существуют и лежат на GitHub:
   `tkalayci71/embedding-inspector` (показывает векторы и ближайшие токены,
   умеет смешивать), `klimaleksus/stable-diffusion-webui-embedding-merge`
   (парсит промпт и собирает эмбеддинг из литералов), `mykeehu/embedding-inspector`
   (экономичная по памяти инспекция/слияние). Ими можно вычесть концепт из
   эмбеддинга и получить «вычищенный» негатив.

Что делает этот файл:
  - держит словарь слов-саботажников и делит их на категории;
  - считает индекс саботажа негатива;
  - отдаёт вычищенный негатив (убирает только саботаж, качество и
    анти-цензуру не трогает);
  - сканирует папки с промптами и находит, где саботаж уже вписан;
  - проверяет имена эмбеддингов на известные «тяжёлые» негативы.

    python3 tools/neg_audit.py --check "lowres, nsfw, nude, bad anatomy"
    python3 tools/neg_audit.py --clean   "lowres, nsfw, bad anatomy, censored"
    python3 tools/neg_audit.py --scan assets/prompts
    python3 tools/neg_audit.py --embeddings
    python3 tools/neg_audit.py --league
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Категории. Вес — насколько слово реально режет кадр.
LEXICON: dict[str, dict[str, int]] = {
    # прямое вычитание наготы и кожи
    "explicit": {"nsfw": 10, "nude": 10, "naked": 9, "nudity": 10, "explicit": 8,
                 "porn": 8, "erotic": 5, "sex": 6, "topless": 7, "nipples": 6,
                 "genitals": 5, "lewd": 5, "hentai": 6},
    # вычитание тела и подачи
    "body": {"cleavage": 6, "underboob": 6, "thighs": 4, "bare skin": 6,
             "barefoot": 4, "feet": 3, "lingerie": 5, "panties": 4, "bra": 4,
             "stockings": 3, "high heels": 2, "wet": 3, "sweat": 3},
    # вычитание возраста/взрослости (частая ошибка в детских негативах)
    "age": {"adult": 4, "mature": 2, "milf": 3},
    # анти-цензура: это НЕ саботаж, наоборот — нужное
    "anti_censor": {"censored": 0, "mosaic censoring": 0, "bar censor": 0,
                    "pixelated": 0, "steam": 0, "hair over breasts": 0},
    # качество: не трогаем
    "quality": {"lowres": 0, "worst quality": 0, "bad anatomy": 0, "bad hands": 0,
                "jpeg artifacts": 0, "watermark": 0, "signature": 0},
}

KNOWN_SUPPRESSOR_EMBEDDINGS = {
    "easynegative": "обучен на «плохих» картинках; содержит широкий набор негативных токенов, у части сборок внутри nsfw/nude",
    "bad_prompt": "то же семейство: общий негатив по качеству, тянет и кожу",
    "badprompt": "то же семейство",
    "deepnegative": "многотокенный негатив, в том числе по телу",
    "negative_hand": "только кисти — безопасен",
    "bad-hands-5": "только кисти — безопасен",
    "verybadimagenegative": "общий негатив по качеству",
}


def _flatten() -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for cat, words in LEXICON.items():
        for w, weight in words.items():
            out[w] = (cat, weight)
    return out


FLAT = _flatten()


def _terms(text: str) -> list[str]:
    parts = re.split(r"[,\n]", text or "")
    return [p.strip().lower() for p in parts if p.strip()]


def _strip_weight(term: str) -> str:
    """`(nsfw:1.4)` → `nsfw`, `[nude]` → `nude`."""
    t = term.strip()
    t = re.sub(r"[\[\](){}]", "", t)
    t = re.sub(r":\s*[\d.]+$", "", t)
    return t.strip().lower()


def check(negative: str) -> dict:
    hits, sabotage = [], 0
    for term in _terms(negative):
        key = _strip_weight(term)
        if key in FLAT:
            cat, weight = FLAT[key]
            if weight > 0:
                sabotage += weight
                hits.append({"term": term, "category": cat, "weight": weight})
    if sabotage == 0:
        verdict = "чисто"
    elif sabotage < 10:
        verdict = "лёгкий саботаж"
    elif sabotage < 25:
        verdict = "саботаж: кожа будет глушиться"
    else:
        verdict = "тяжёлый саботаж: кадр будет «одетым» независимо от промпта"
    return {"index": sabotage, "verdict": verdict, "hits": hits}


def clean(negative: str) -> tuple[str, list[str]]:
    """Убрать только слова-саботажники. Качество и анти-цензуру не трогаем."""
    kept, removed = [], []
    for term in _terms(negative):
        key = _strip_weight(term)
        cat, weight = FLAT.get(key, ("", 0))
        if weight > 0:
            removed.append(term)
        else:
            kept.append(term)
    return ", ".join(kept), removed


def scan(path: pathlib.Path) -> list[dict]:
    """Найти промпты, где саботаж уже вписан (jsonl / csv / txt)."""
    rows = []
    files = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file()]
    for f in files:
        if f.suffix.lower() not in {".jsonl", ".json", ".csv", ".txt"}:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if f.suffix == ".jsonl":
            for i, line in enumerate(text.splitlines(), 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                neg = obj.get("negative_prompt") or obj.get("negative") or ""
                res = check(neg)
                if res["index"]:
                    rows.append({"file": str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else str(f),
                                 "line": i, **res})
        elif f.suffix in {".txt", ".csv"}:
            res = check(text)
            if res["index"]:
                rows.append({"file": str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else str(f),
                             "line": 0, **res})
    return rows


def embeddings(dirpath: pathlib.Path | None = None) -> list[dict]:
    """Проверить имена файлов эмбеддингов на известные «тяжёлые» негативы."""
    dirpath = dirpath or (ROOT / "assets" / "embeddings")
    found = []
    if not dirpath.exists():
        return found
    for f in dirpath.iterdir():
        if f.suffix.lower() not in {".pt", ".bin", ".safetensors"}:
            continue
        stem = f.stem.lower().replace("-", "").replace("_", "")
        for name, why in KNOWN_SUPPRESSOR_EMBEDDINGS.items():
            if name.replace("-", "").replace("_", "") in stem:
                found.append({"file": f.name, "known": name, "why": why,
                              "safe": "кисти" in why})
                break
    return found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", metavar="NEGATIVE")
    ap.add_argument("--clean", metavar="NEGATIVE")
    ap.add_argument("--scan", metavar="PATH")
    ap.add_argument("--embeddings", action="store_true")
    ap.add_argument("--league", action="store_true")
    a = ap.parse_args()

    if a.league:
        for cat, words in LEXICON.items():
            mark = "саботаж" if any(w > 0 for w in words.values()) else "нейтрально"
            print(f"{cat:<12} [{mark}] " + ", ".join(f"{w}({n})" for w, n in words.items()))
        return

    if a.embeddings:
        rows = embeddings()
        if not rows:
            print("эмбеддингов в assets/embeddings нет — проверять нечего")
            return
        for r in rows:
            print(f"{r['file']}: {r['known']} — {r['why']}")
        return

    if a.scan:
        rows = scan(pathlib.Path(a.scan))
        if not rows:
            print("саботажа не найдено")
            return
        print(f"найдено {len(rows)} промптов с саботажем в негативе:\n")
        for r in rows[:20]:
            terms = ", ".join(h["term"] for h in r["hits"][:5])
            print(f"  {r['file']}:{r['line']}  индекс {r['index']:<3} {r['verdict']}  ← {terms}")
        if len(rows) > 20:
            print(f"  … и ещё {len(rows) - 20}")
        return

    if a.clean:
        cleaned, removed = clean(a.clean)
        print("вычищено:", ", ".join(removed) or "—")
        print("негатив:", cleaned or "(пусто)")
        return

    text = a.check if a.check is not None else ""
    res = check(text)
    print(f"индекс саботажа: {res['index']} · {res['verdict']}")
    for h in res["hits"]:
        print(f"  {h['term']:<24} {h['category']:<12} +{h['weight']}")


if __name__ == "__main__":
    main()
