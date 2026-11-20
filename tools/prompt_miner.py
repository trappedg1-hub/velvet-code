"""
prompt_miner.py — что реально пишут в промптах, посчитанное по корпусу.

Идея простая и жестокая: не надо угадывать «как делают стиль». Берём корпус
реальных промптов, считаем частоты и смотрим, чем люди начинают строку, какие
блоки качества повторяются, какие негативы действительно массовые, какие
художники и LoRA всплывают рядом с нужным жанром.

Что достаём:
  quality    первые блоки промпта (то, чем задают «дорогой» вид)
  negative   частотные негативы — что люди реально защищают
  style      слова о манере: линия, свет, материал, кожа
  lora       имена LoRA и типичные веса
  artist     художники, на которых ссылаются (для ориентации, не для копирования)
  cooccur    что встречается вместе с manhwa / webtoon / korean / comic

    python3 tools/prompt_miner.py --top 25
    python3 tools/prompt_miner.py --fingerprint          # assets/prompts/fingerprint.json
    python3 tools/prompt_miner.py --cooccur manhwa
    python3 tools/prompt_miner.py --wildcards            # обновить wildcards из корпуса
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORPUS = ROOT / "assets" / "prompts"
FP = CORPUS / "fingerprint.json"
WILD = ROOT / "assets" / "wildcards"

WEIGHT_RE = re.compile(r"[()\[\]{}]|:\s?\d+(?:\.\d+)?")
LORA_RE = re.compile(r"<lora:([^:>]+)(?::([\d.]+))?>", re.I)
ARTIST_RE = re.compile(r"(?:by\s+([a-z0-9_\- .]{3,40})|artist:([a-z0-9_\- .]{3,40}))", re.I)

STYLE_WORDS = {
    "line", "lineart", "outline", "cel", "shading", "shadow", "light", "lighting",
    "rim", "contrast", "saturation", "glossy", "gloss", "sheen", "texture", "detail",
    "detailed", "realistic", "anime", "manga", "manhwa", "webtoon", "comic", "illustration",
    "painting", "watercolor", "sketch", "ink", "halftone", "vibrant", "cinematic",
}


def load(source: str | None = None) -> list[dict]:
    rows = []
    for path in sorted(CORPUS.glob("*.jsonl")):
        if source and path.stem != source:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def tokens(prompt: str) -> list[str]:
    """Разбить промпт на «теги»: запятые, но без весов и мусора."""
    out = []
    for raw in re.split(r"[,\n]", prompt):
        t = WEIGHT_RE.sub("", raw).strip().lower()
        t = re.sub(r"\s+", " ", t)
        if 2 <= len(t) <= 60:
            out.append(t)
    return out


def _counter(rows: list[dict], field: str) -> collections.Counter:
    c: collections.Counter = collections.Counter()
    for r in rows:
        c.update(tokens(r.get(field, "")))
    return c


def mine(rows: list[dict]) -> dict:
    total = len(rows)
    pos, neg = _counter(rows, "prompt"), _counter(rows, "negative")

    firsts: collections.Counter = collections.Counter()
    for r in rows:
        toks = tokens(r.get("prompt", ""))
        if toks:
            firsts[toks[0]] += 1

    loras: collections.Counter = collections.Counter()
    weights: dict[str, list[float]] = collections.defaultdict(list)
    artists: collections.Counter = collections.Counter()
    for r in rows:
        for name, w in LORA_RE.findall(r.get("prompt", "")):
            loras[name.strip()] += 1
            if w:
                weights[name.strip()].append(float(w))
        for a, b in ARTIST_RE.findall(r.get("prompt", "")):
            artists[(a or b).strip().rstrip(".")] += 1

    style = {t: n for t, n in pos.items() if any(w in t for w in STYLE_WORDS)}

    def share(d: dict, n: int) -> dict:
        return {k: round(100 * v / total, 2) for k, v in
                sorted(d.items(), key=lambda kv: -kv[1])[:n]}

    return {
        "total": total,
        "quality_first": share(dict(firsts), 25),
        "top_positive": share(dict(pos), 80),
        "top_negative": share(dict(neg), 40),
        "style": share(style, 60),
        "lora": {k: {"n": v, "mean_weight": round(sum(weights[k]) / len(weights[k]), 2)
                     if weights.get(k) else None}
                 for k, v in loras.most_common(20)},
        "artist": share(dict(artists), 20),
    }


def cooccur(rows: list[dict], anchor: str, n: int = 20) -> list[tuple[str, int, int]]:
    """Что встречается вместе с якорем: (тег, вместе, всего) — ищем по подстроке."""
    a = anchor.lower()
    with_a = [r for r in rows if a in r.get("prompt", "").lower()]
    c_with = collections.Counter()
    for r in with_a:
        # set() — иначе тег, повторённый в строке дважды, даёт >100%
        c_with.update(set(tokens(r.get("prompt", ""))))
    c_with.pop(anchor, None)
    return [(t, k, len(with_a)) for t, k in c_with.most_common(n)]


def wildcards(rows: list[dict]) -> dict[str, int]:
    WILD.mkdir(parents=True, exist_ok=True)
    pos, neg = _counter(rows, "prompt"), _counter(rows, "negative")
    sets = {
        "corpus_quality.txt": [t for t in pos if any(
            w in t for w in ("masterpiece", "best quality", "high quality", "detailed",
                             "8k", "absurdres", "aesthetic", "quality"))][:40],
        "corpus_negative.txt": [t for t, _ in neg.most_common(60)],
        "corpus_style.txt": [t for t in pos if any(w in t for w in STYLE_WORDS)][:40],
    }
    counts = {}
    for name, lines in sets.items():
        (WILD / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        counts[name] = len(lines)
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source")
    ap.add_argument("--top", type=int)
    ap.add_argument("--fingerprint", action="store_true")
    ap.add_argument("--cooccur")
    ap.add_argument("--wildcards", action="store_true")
    a = ap.parse_args()

    rows = load(a.source)
    if not rows:
        print("корпус пуст — сначала python3 tools/corpus_fetch.py --source <name>")
        return

    if a.cooccur:
        res = cooccur(rows, a.cooccur)
        print(f"вместе с «{a.cooccur}» (всего промптов с якорем: {res[0][2] if res else 0}):")
        for t, k, total in res:
            print(f"  {k:>5}  {100*k/total:5.1f}%  {t}")
        return

    fp = mine(rows)
    if a.wildcards:
        for name, n in wildcards(rows).items():
            print(f"{name}: {n} строк")
    if a.fingerprint:
        CORPUS.mkdir(parents=True, exist_ok=True)
        FP.write_text(json.dumps(fp, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"фингерпринт → {FP.relative_to(ROOT)} ({fp['total']} промптов)")
    if a.top:
        print(f"\nкорпус: {fp['total']} промптов")
        print("\nчем начинают:");
        for t, s in list(fp["quality_first"].items())[:a.top]:
            print(f"  {s:5.1f}%  {t}")
        print("\nтоп позитив:")
        for t, s in list(fp["top_positive"].items())[:a.top]:
            print(f"  {s:5.1f}%  {t}")
        print("\nтоп негатив:")
        for t, s in list(fp["top_negative"].items())[:a.top]:
            print(f"  {s:5.1f}%  {t}")
    if not (a.top or a.fingerprint or a.wildcards or a.cooccur):
        ap.print_help()


if __name__ == "__main__":
    main()
