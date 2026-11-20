"""
boldness.py — арена откровенности: измерять смелость кадра числом, а не на глаз.

Зачем. «Смелее» — это не один тег. Кадр становится смелее, когда растёт
одновременно кожа, ткань, ракурс и взгляд. Если тянуть только один рычаг,
получается вульгарно; если тянуть все сразу без учёта предела — получается
порно, которое владелец не заказывал и которое не пройдёт политику игры.

Поэтому здесь шкала из шести ступеней и счёт по рычагам. Арена берёт варианты
одной сцены, считает смелость каждого и выбирает самый смелый из тех, что
остались в пределах политики (L2+ для каста, L3 только по отдельному разрешению).

Жёсткие пределы — не рекомендации, а стоп-кран: если в промпте есть маркер
несовершеннолетнего вида, реального человека или неконсентного сценария,
счёт не считается вообще.

    python3 tools/boldness.py --heroine selena --heat 2
    python3 tools/boldness.py --prompt "sheer wet blouse, underboob, low angle"
    python3 tools/boldness.py --rank variants.jsonl      # выбрать самый смелый
    python3 tools/boldness.py --ladder                   # таблица ступеней
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# --- жёсткие пределы --------------------------------------------------------
HARD_LIMITS = {
    "minor_markers": ["loli", "shota", "child", "little girl", "kid", "toddler",
                      "underage", "schoolgirl uniform, small", "flat chest, child"],
    "real_person": ["celebrity", "real person", "likeness of", "deepfake", "photo of"],
    "non_consent": ["rape", "non-consensual", "drugged", "unconscious", "forced",
                    "crying, bound"],
    "illegal": ["bestiality", "gore", "torture", "snuff"],
}

# --- рычаги смелости --------------------------------------------------------
# вес = насколько тег двигает кадр по шкале
LEVERS: dict[str, dict[str, int]] = {
    "skin": {
        "bare shoulders": 6, "cleavage": 8, "underboob": 16, "sideboob": 12,
        "midriff": 8, "bare back": 8, "high side slit": 12, "bare thighs": 10,
        "thigh gap": 6, "navel": 5, "bare feet": 6, "toes": 5,
    },
    "fabric": {
        "sheer": 14, "translucent fabric": 12, "wet clothes": 16, "wet blouse": 16,
        "wet shirt": 16, "wet hair": 8, "fabric tension": 12,
        "clinging": 10, "lingerie visible": 16, "garter straps": 12, "unbuttoned": 10,
        "pantyhose": 6, "stocking tops": 10, "no bra": 14, "dress strap slipping": 10,
    },
    "pose": {
        "arched back": 8, "legs crossed": 5, "one knee raised": 8, "lying on back": 10,
        "legs apart": 14, "on all fours": 16, "looking over shoulder": 8,
        "heel raised": 5, "toes pointed": 5, "kneeling": 8,
    },
    "camera": {
        "low angle": 8, "from below": 8, "close-up on legs": 8, "foot focus": 8,
        "cowboy shot": 5, "full body": 2, "high angle": 4,
    },
    "gaze": {
        "eye contact": 6, "half-closed eyes": 8, "parted lips": 6, "blush": 5,
        "looking at viewer": 4, "sweat on skin": 10, "glossy skin": 6,
    },
}

# --- ступени ----------------------------------------------------------------
# Границы не выдуманы: они сняты с наших же промптов. Семь героинь на heat 1
# дают сырой балл 19–54 (в среднем 39), на heat 2 — 94–144 (в среднем 119).
# Отсюда B1 кончается на 74, B2 — на 129, дальше начинается грань.
TIERS = [
    (0, 24, "B0 · промо", "героиня в кадре как персонаж: костюм, поза, свет. Ноль провокации"),
    (25, 74, "B1 · поддразнивание", "кожа или ткань открывают одну зону; работает взгляд"),
    (75, 129, "B2 · канон L2", "потолок для каста в игре: прозрачное, натянутое, акцент на ноги и стопы"),
    (130, 164, "B2+ · грань", "бельё как верхний слой, мокрый шёлк, сползшая бретель. Только по разрешению"),
    (165, 999, "B3 · вне политики", "кадр держится на теле, а не на сцене; в канон не ставим"),
]
CANON_BASELINE = 119   # средний сырой балл каста на L2 — база для индекса
POLICY_CEILING = 164   # выше — только с отдельного разрешения владельца


def gate(prompt: str) -> list[str]:
    """Жёсткие пределы. Возвращает список нарушений (пусто — чисто)."""
    low = (prompt or "").lower()
    bad = []
    for rule, markers in HARD_LIMITS.items():
        hit = [m for m in markers if m in low]
        if hit:
            bad.append(f"{rule}: {', '.join(hit)}")
    return bad


def score(prompt: str) -> dict:
    """Счёт смелости по рычагам + ступень + что добавить, чтобы стать смелее."""
    low = (prompt or "").lower().replace("_", " ")
    total, hits = 0, []
    for lever, tags in LEVERS.items():
        for tag, weight in tags.items():
            if tag in low:
                total += weight
                hits.append({"lever": lever, "tag": tag, "weight": weight})
    tier = next((row for row in TIERS if row[0] <= total <= row[1]), TIERS[-1])
    tier_name, tier_note = tier[2], tier[3]
    used = {h["lever"] for h in hits}

    # что даст прирост при том же стиле: берём сильнейший неиспользованный тег
    proposals = []
    for lever, tags in LEVERS.items():
        for tag, weight in sorted(tags.items(), key=lambda kv: -kv[1]):
            if tag not in low:
                proposals.append({"lever": lever, "tag": tag, "delta": weight,
                                  "covers_lever": lever in used})
                break
    proposals.sort(key=lambda p: (not p["covers_lever"], p["delta"]))
    return {
        "score": total,
        "index": round(total / CANON_BASELINE * 100),
        "vs_canon": round(total / CANON_BASELINE * 100) - 100,
        "tier": tier_name,
        "tier_note": tier_note,
        "policy_ok": total <= POLICY_CEILING,
        "levers_used": sorted(used),
        "levers_idle": sorted(set(LEVERS) - used),
        "hits": hits,
        "next_moves": proposals[:3],
        "violations": gate(prompt),
    }


def suggest(prompt: str, target: int = 130) -> list[str]:
    """Теги, которые поднимут кадр до целевой ступени, без перелома через предел."""
    cur = score(prompt)
    out, total = [], cur["score"]
    for mv in cur["next_moves"]:
        if total >= target:
            break
        out.append(mv["tag"])
        total += mv["delta"]
    return out


def rank(prompts: list[dict]) -> list[dict]:
    """Выбрать самые смелые варианты, отбросив нарушителей пределов."""
    scored = []
    for p in prompts:
        text = p.get("prompt") or p.get("text") or ""
        s = score(text)
        if s["violations"]:
            continue
        if not s["policy_ok"]:
            continue
        scored.append({**p, "boldness": s})
    scored.sort(key=lambda x: -x["boldness"]["score"])
    return scored


def build_task(heroine: str, heat: int = 2, n: int = 12) -> str:
    """Самодостаточная задача «арена откровенности» для чужой сессии агента."""
    from prompt_forge import forge

    base = forge(heroine, heat=heat)
    b = score(base["prompt"])
    tiers = "\n".join(f"| {name} | {lo}–{hi} | {note} |"
                       for lo, hi, name, note in TIERS if lo <= POLICY_CEILING)
    levers = "\n".join(f"- **{k}**: " + ", ".join(f"{t} ({w})" for t, w in v.items())
                        for k, v in LEVERS.items())
    return f"""# Задача: арена откровенности для {heroine}

## Цель
Собрать {n} вариантов одного кадра {heroine} разной смелости и выбрать самый смелый из тех,
кто остался в пределах политики игры. Кадр на грани, а не порно: героиня одета, но подача
доведена до предела.

## Что уже есть
- базовый кадр (L{heat}) даёт балл **{b['score']}**, это ступень **{b['tier']}**;
- канонный кадр каста в среднем = 119 баллов, значит база считается как 100%;
- потолок политики — **{POLICY_CEILING} баллов**. Выше — не принимается, даже если красиво.

## Как меряется смелость
Счёт = сумма весов тегов по пяти рычагам. Растёт не от одного тега, а от согласия рычагов.

{levers}

## Ступени
| ступень | баллы | смысл |
|---|---|---|
{tiers}

## Требования к вариантам
1. Ровно {n} вариантов, каждый — полный промпт (позитив + негатив) в одной строке JSONL:
   `{{"id": "...", "prompt": "...", "negative": "...", "lever": "какой рычаг усилили"}}`.
2. Каждый вариант обязан содержать стилевое ядро регистра hentai-render:
   `clean thin lineart, tapered line ends, soft gradient shading, saturated red-violet skin shadows, glossy specular highlights`.
3. Стопа: `petite feet, high arch, defined instep, long slender toes, groomed toenails`,
   ракурс — профиль или три четверти. `soles toward camera` — запрещено.
4. Жёсткие пределы: несовершеннолетний вид, реальные люди, неконсентные сценарии,
   расчленёнка — не обсуждаются, вариант выбрасывается целиком.

## Приёмка (выполнить буквально)
    python3 tools/boldness.py --rank variants.jsonl
    python3 tools/foot_spec.py --check "<prompt>" "<negative>"
    python3 -m pytest tests/ -q
Победитель — первый в выводе `--rank`, у которого `foot_spec` не даёт ошибок.

## Рубрика судьи
| критерий | вес |
|---|---|
| смелость в пределах потолка (не выше {POLICY_CEILING}) | 30 |
| согласие рычагов, а не один тег | 20 |
| стиль hentai-render: линия, градиент, тень, блик | 20 |
| анатомия и стопа (petite, арка, пальцы, ногти) | 20 |
| промпт исполним как есть (полный, без заглушек) | 10 |
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt")
    ap.add_argument("--heroine")
    ap.add_argument("--heat", type=int, default=2)
    ap.add_argument("--rank", metavar="JSONL")
    ap.add_argument("--ladder", action="store_true")
    ap.add_argument("--target", type=int, default=130)
    a = ap.parse_args()

    if a.ladder:
        print(f"{'счёт':>6}  ступень{'':<22} смысл")
        for lo, hi, name, note in TIERS:
            mark = " ← потолок политики" if lo <= POLICY_CEILING <= hi else ""
            print(f"{lo:>3}–{hi:<3} {name:<26} {note}{mark}")
        return

    if a.rank:
        rows = [json.loads(line) for line in
                pathlib.Path(a.rank).read_text(encoding="utf-8").splitlines() if line.strip()]
        ranked = rank(rows)
        if not ranked:
            print("нет вариантов, прошедших пределы")
            return
        for i, r in enumerate(ranked, 1):
            b = r["boldness"]
            print(f"{i}. {b['score']:>3} {b['tier']:<24} {(r.get('id') or '')[:24]}")
        best = ranked[0]
        print(f"\nпобедитель: {best['boldness']['score']} · {best['boldness']['tier']}")
        print(f"рычаги: {', '.join(best['boldness']['levers_used'])}")
        return

    text = a.prompt
    if not text and a.heroine:
        from prompt_forge import forge
        text = forge(a.heroine, heat=a.heat)["prompt"]

    s = score(text)
    print(f"счёт: {s['score']} · индекс {s['index']} к канону ({s['vs_canon']:+d}%) · {s['tier']}")
    print(f"в политике: {'да' if s['policy_ok'] else 'НЕТ'}")
    if s["violations"]:
        print("жёсткий предел:", "; ".join(s["violations"]))
    print("рычаги:", ", ".join(s["levers_used"]) or "—")
    print("простаивают:", ", ".join(s["levers_idle"]) or "—")
    print("до смелее:", ", ".join(suggest(text, a.target)) or "уже на цели")


if __name__ == "__main__":
    main()
