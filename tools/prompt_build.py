"""
prompt_build.py — tiny, dependency-free prompt expander built on the syntax that
actually ships in the wild (see canon item `prompt-stack`).

Supported, in the order they are resolved:

  __name__          -> one random line from assets/wildcards/name.txt
  __name*__         -> one random line from a glob of wildcard files
  {2$$__name__}     -> N distinct lines from that wildcard, comma-joined, no dupes
  {a|b|c}           -> one random variant
  {a|b|c}           -> nested forms work too: {a|{2$$__body_curvy__}} is allowed
  {x        ^       -> whitespace and newlines inside a template are collapsed

Why not just use Dynamic Prompts? We do, in the real render farm (Anima Turbo /
ComfyUI). This module exists so the *repo* can validate prompt templates, unit
test them, and reproduce a batch from a seed without a 300 MB dependency. It is
the same semantics, ~120 lines, no network.

Usage:
    python3 tools/prompt_build.py --template "{2$$__body_curvy__}, __pose_ecchi__, {red|black} dress" -n 3 --seed 7
    python3 tools/prompt_build.py --file prompts/selena.txt -n 5
"""
from __future__ import annotations

import argparse
import pathlib
import random
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
WILD = ROOT / "assets" / "wildcards"

WS = re.compile(r"[ \t]*\n[ \t]*")
MULTI = re.compile(r"\s*,\s*")


def _lines(name: str) -> list[str]:
    """Lines of assets/wildcards/<name>.txt (a glob is allowed)."""
    if name.endswith("*"):
        files = sorted(WILD.glob(name + ".txt"))
    else:
        files = [WILD / f"{name}.txt"]
    out: list[str] = []
    for f in files:
        if not f.exists():
            raise FileNotFoundError(f"wildcard not found: {f}")
        out += [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not out:
        raise ValueError(f"wildcard empty: {name}")
    return out


def _find_block(s: str, start: int) -> tuple[str, int]:
    """Return (body, index-after-closing-brace) for the block opening at `start`."""
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return s[start + 1 : i], i + 1
    raise ValueError(f"unbalanced braces at {start}: {s[start:start + 40]!r}")


def expand(template: str, rng: random.Random, depth: int = 0) -> str:
    """Expand one prompt. `depth` guards against self-referencing wildcards."""
    if depth > 8:
        raise RecursionError("wildcard nesting too deep")

    # 1. innermost brace blocks first, so nesting resolves bottom-up
    while "{" in template:
        innermost = None
        for m in re.finditer(r"\{[^{}]*\}", template):
            innermost = m
        if innermost is None:
            raise ValueError("unbalanced braces in template")
        body, _ = _find_block(template, innermost.start())
        template = (template[: innermost.start()]
                    + _resolve(body, rng, depth)
                    + template[innermost.end():])

    # 2. bare wildcards
    def _wild(m: re.Match[str]) -> str:
        return rng.choice(_lines(m.group(1)))

    template = re.sub(r"__([A-Za-z0-9_\-*]+)__", _wild, template)
    return WS.sub(" ", template).strip()


def _resolve(body: str, rng: random.Random, depth: int) -> str:
    """Resolve the content of one {…} block."""
    # {N$$__name__} — N distinct picks, no duplicates
    m = re.fullmatch(r"\s*(\d+)\s*\$\$\s*(.+?)\s*", body, re.S)
    if m:
        n = int(m.group(1))
        pool = _lines(m.group(2).replace("__", "").strip())
        if m.group(2).strip().startswith("__"):
            picks = rng.sample(pool, min(n, len(pool)))
        else:  # not a wildcard reference: treat the body as a variant list
            picks = rng.sample([v.strip() for v in m.group(2).split("|")], min(n, len(m.group(2).split("|"))))
        return MULTI.sub(", ", ", ".join(picks))

    # {a|b|c} — one variant, sub-variants expanded recursively
    variants = [v.strip() for v in body.split("|")]
    return expand(rng.choice(variants), rng, depth + 1)


def build(template: str, n: int = 1, seed: int | None = None) -> list[str]:
    rng = random.Random(seed)
    seen: set[str] = set()
    out: list[str] = []
    guard = 0
    # distinct prompts within a batch: @once-like distribution without dupes
    while len(out) < n and guard < n * 40:
        guard += 1
        p = expand(template, rng)
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


# --- валидация: какие оси взаимоисключающие ---------------------------------
# Ось «фигура», «поза», «обувь» — исключительные: в одном промпте должна быть
# РОВНО ОДНА строка из файла. Иначе модель получает «MILF + athletic» и рисует
# усреднённое тело — та самая болезнь «все на одно лицо».
EXCLUSIVE = ("figure_types", "feet_poses", "footwear", "pose_ecchi", "camera")


def validate(prompt: str) -> list[str]:
    """Вернуть список проблем в готовом промпте (пусто = ок)."""
    problems: list[str] = []
    for name in EXCLUSIVE:
        try:
            lines = _lines(name)
        except FileNotFoundError:
            continue
        hits = [ln for ln in lines if ln and ln in prompt]
        if len(hits) > 1:
            problems.append(f"{name}: {len(hits)} взаимоисключающих строк -> " + " | ".join(hits[:3]))
    # стопа «заявлена» (подошва/поданная стопа/поджатые пальцы), но камера не работает на неё
    focus_tokens = ("presenting own foot", "soles", "toe scrunch", "shoe dangle", "plantar flexion", "arched soles")
    camera_tokens = ("foot focus", "low angle", "from below", "camera at knee", "near floor")
    if any(t in prompt for t in focus_tokens) and not any(c in prompt for c in camera_tokens):
        problems.append("стопа заявлена, но камера не на уровне стопы (нужен low angle / foot focus)")
    return problems


# --- сборка промпта ПОД ГЕРОИНЮ --------------------------------------------
# Фигура и костюм НЕ рандомизируются: они приходят из content/characters/<id>.json.
# Wildcard-выбор идёт только по позе и камере, причём глубина фут-акцента
# ограничена полем body.feet_focus_level (1 — без акцента, 3 — поза целиком о стопе).
FEET_LEVELS = {
    3: None,          # все строки feet_poses
    2: ("tiptoes", "heel pop", "perched", "crossed ankles", "standing"),
    1: ("crossed ankles", "standing"),
}


def build_heroine(char_id: str, n: int = 1, seed: int | None = None) -> list[str]:
    import json

    card = json.loads((ROOT / "content" / "characters" / f"{char_id}.json").read_text(encoding="utf-8"))
    body = card["body"]
    level = int(body.get("feet_focus_level", 1))
    allow = FEET_LEVELS.get(level, FEET_LEVELS[1])
    poselines = _lines("feet_poses")
    if allow:
        poselines = [ln for ln in poselines if any(k in ln for k in allow)] or poselines

    # уровень 1 = «стопа без акцента»: убираем кадры, которые сами создают акцент
    camlines = _lines("camera")
    if level <= 1:
        camlines = [ln for ln in camlines if "footwear focus" not in ln and "over shoulder" not in ln] or camlines

    # уровень 1 = «стопа без акцента»: убираем кадры, которые сами создают акцент
    camlines = _lines("camera")
    if level <= 1:
        camlines = [ln for ln in camlines if "footwear focus" not in ln and "over shoulder" not in ln] or camlines

    rng = random.Random(seed)
    head = [
        "masterpiece", "best quality", "manhwa style",
        ", ".join(body.get("figure_tags", [])),
        card.get("pose_prompt") or card.get("pose_language", ""),
        ", ".join(card.get("wardrobe_default", {}).get("prompt_tags", [])[:6]),
    ]
    out: list[str] = []
    seen: set[str] = set()
    guard = 0
    while len(out) < n and guard < n * 40:
        guard += 1
        # если у героини задана авторская поза (pose_prompt) — она главная,
        # wildcard-поза не добавляется, иначе получаем две несовместимые позы
        pose = "" if card.get("pose_prompt") else rng.choice(poselines)
        cam = rng.choice(camlines)
        prompt = ", ".join(x for x in (*head, pose, cam) if x)
        if prompt in seen:
            continue
        seen.add(prompt)
        out.append(prompt)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template")
    ap.add_argument("--file")
    ap.add_argument("-n", type=int, default=1)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--validate", action="store_true", help="проверить промпты на конфликты осей")
    ap.add_argument("--heroine", help="собрать промпт под героиню из content/characters/<id>.json")
    a = ap.parse_args()
    if a.heroine:
        prompts = build_heroine(a.heroine, a.n, a.seed)
    else:
        tpl = a.template if a.template else pathlib.Path(a.file).read_text(encoding="utf-8").strip()
        prompts = build(tpl, a.n, a.seed)
    bad = 0
    for i, p in enumerate(prompts, 1):
        print(f"[{i}] {p}")
        if a.validate:
            for prob in validate(p):
                bad += 1
                print(f"    ! {prob}")
    if a.validate:
        print(f"\nконфликтов: {bad}")


if __name__ == "__main__":
    main()
