"""
corpus_fetch.py — сборка локального корпуса промптов из открытых датасетов.

Зачем: «база NSFW-промптов» не может быть списком, который кто-то придумал в
чате. Нужны реальные строки, которые люди писали руками и которыми получали
результат. Из них добываются: чем реально начинают промпт, какие негативы
работают, какие связки тегов встречаются вместе, какие модели и настройки
стоят за удачными кадрами.

Источники (лицензии см. docs/14):
  jtatman/stable-diffusion-prompts-uncensored — 851 568 строк, MIT,
      поля: model, prompt, negative_prompt
  laurajul/Civiverse-SFW — Civiverse 6M, метаданные: prompt, negativePrompt,
      Model, Meta (Size/Seed/Steps/Sampler), ресурсы (LoRA)

Тянем через datasets-server (постранично, без torch и без скачивания 647 МБ).

    python3 tools/corpus_fetch.py --source jtatman --pages 40
    python3 tools/corpus_fetch.py --source civiverse --pages 20
    python3 tools/corpus_fetch.py --stats
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "prompts"

SOURCES = {
    "jtatman": {
        "dataset": "jtatman/stable-diffusion-prompts-uncensored",
        "config": "default",
        "split": "train",
        "license": "MIT",
        "fields": {"model": "model", "prompt": "prompt", "negative": "negative_prompt"},
    },
    "civiverse": {
        "dataset": "laurajul/Civiverse-SFW",
        "config": "default",
        "split": "train",
        "license": "research / Civiverse 6M",
        "fields": {"model": "Model", "prompt": "positivePrompt",
                   "negative": "negativePrompt", "meta": "Meta"},
    },
}

PAGE = 20          # 100 строк сервер отдаёт обрезанным JSON


def _get(url: str, tries: int = 5) -> dict:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "velvet-code/1.0"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = 15 * (i + 1)
                print(f"  rate-limit (429), ждём {wait} с")
                time.sleep(wait)
                continue
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if i == tries - 1:
                raise
            print(f"  повтор после {exc!r}"[:120])
            time.sleep(2 * (i + 1))
    return {}


def page(source: str, offset: int, length: int = PAGE) -> list[dict]:
    cfg = SOURCES[source]
    q = urllib.parse.urlencode({"dataset": cfg["dataset"], "config": cfg["config"],
                                "split": cfg["split"], "offset": offset, "length": length})
    try:
        data = _get(f"https://datasets-server.huggingface.co/rows?{q}")
    except json.JSONDecodeError:
        # сервер иногда отдаёт обрезанный JSON на длинных промптах:
        # добираем эту же страницу мелкими кусками, а не теряем её целиком
        if length <= 5:
            print(f"  страница offset={offset}: битый ответ, пропуск")
            return []
        out = []
        for sub in range(0, length, 5):
            out += page(source, offset + sub, 5)
        return out
    rows = []
    f = cfg["fields"]
    for item in data.get("rows", []):
        row = item.get("row", {})
        rec = {
            "source": source,
            "license": cfg["license"],
            "model": str(row.get(f["model"], "") or "")[:120],
            "prompt": str(row.get(f["prompt"], "") or ""),
            "negative": str(row.get(f["negative"], "") or ""),
        }
        if "meta" in f:
            rec["meta"] = str(row.get(f["meta"], "") or "")[:300]
        if rec["prompt"].strip():
            rows.append(rec)
    return rows


def fetch(source: str, pages: int, start: int = 0) -> pathlib.Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{source}.jsonl"
    seen: set[str] = set()
    good: list[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                seen.add(json.loads(line)["prompt"])
                good.append(line)
            except Exception:
                continue          # недописанная строка после падения — выбрасываем
        # переписываем файл без битых строк, иначе они отравляют все прогоны
        path.write_text("\n".join(good) + ("\n" if good else ""), encoding="utf-8")
    added = 0
    with path.open("a", encoding="utf-8") as fh:
        for p in range(start, start + pages):
            rows = page(source, p * PAGE)
            if not rows:
                print(f"  страница {p}: пусто — стоп")
                break
            for rec in rows:
                key = rec["prompt"]
                if key in seen:
                    continue
                seen.add(key)
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                added += 1
            print(f"  страница {p}: +{len(rows)} (всего новых {added})")
            time.sleep(1.2)      # 429 иначе прилетает сразу
    print(f"{path.relative_to(ROOT)}: +{added} строк, всего {len(seen)}")
    return path


def stats() -> None:
    for src in SOURCES:
        path = OUT / f"{src}.jsonl"
        if not path.exists():
            print(f"{src}: нет файла")
            continue
        rows = []
        for l in path.read_text(encoding="utf-8").splitlines():
            if not l.strip():
                continue
            try:
                rows.append(json.loads(l))
            except Exception:
                continue
        models: dict[str, int] = {}
        for r in rows:
            models[r["model"]] = models.get(r["model"], 0) + 1
        top = sorted(models.items(), key=lambda kv: -kv[1])[:5]
        print(f"{src}: {len(rows)} строк, {round(path.stat().st_size/1024)} КБ")
        print("  модели:", ", ".join(f"{m or '—'} ({n})" for m, n in top))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=sorted(SOURCES))
    ap.add_argument("--pages", type=int, default=20)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--stats", action="store_true")
    a = ap.parse_args()
    if a.stats:
        stats()
        return
    if not a.source:
        ap.print_help()
        return
    fetch(a.source, a.pages, a.start)
    stats()


if __name__ == "__main__":
    main()
