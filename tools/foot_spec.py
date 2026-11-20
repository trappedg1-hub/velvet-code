"""
foot_spec.py — анатомия стопы как спецификация, а не «на глаз».

Почему это вообще нужно. На рендерах стопа выходила «ластой»: длинной и плоской.
Причина не в модели, а в задании: когда просишь «стопу подошвой в камеру», модель
берёт ракурс с сильным перспективным сокращением и растягивает форму — а длинные
пальцы в негативе не указаны, и получается ласт.

Что здесь есть:
  1. PROPORTIONS — числа из анатомии для рисования:
       длина стопы ≈ длина головы ≈ предплечье (запястье→локоть);
       стопа делится на три РАВНЫХ блока: пальцы / свод / пятка;
       высота ≈ ширине, длина ≈ 3 высотам;
       у женской стопы уже пятка и лодыжка, выше свод, круче подъём, тоньше пальцы.
  2. VIEWS — какие ракурсы дают привлекательную стопу, а какие превращают её в ласт.
  3. PROMPT — готовые блоки для позитива и негатива.
  4. check() — валидатор промпта: ловит «подошву в камеру» и отсутствие анти-ласт негатива.

    python3 tools/foot_spec.py --block            # блоки для промпта
    python3 tools/foot_spec.py --check "barefoot, soles, soles toward camera"
    python3 tools/foot_spec.py --views
"""
from __future__ import annotations

import argparse
import re

# 1. числа -------------------------------------------------------------------
PROPORTIONS = {
    "length": "длина стопы ≈ длина головы ≈ предплечье (запястье→локоть)",
    "stylized": "в манхва-подаче стопа МЕНЬШЕ анатомической: 0.75–0.85 головы; крупная стопа читается как мужская",
    "thirds": "пальцы / свод / пятка — три равных блока по 1/3 длины",
    "ratio": "высота ≈ ширина, длина ≈ 3 высоты",
    "female": "уже пятка и лодыжка, выше свод, круче подъём, тоньше и короче пальцы",
    "ankles": "внутренняя лодыжка выше наружной",
    "toe_shape": "большой палец отделён и слегка вздёрнут; средние три чуть вниз; мизинец уходит вниз и внутрь",
    "toe_scale": "каждый следующий палец ≈ 1/3 предыдущего по объёму",
    "foreshortening": "стопа, направленная в камеру, КОРОЧЕ и ШИРЕ — отсюда и берутся ласты",
}

# 2. ракурсы -----------------------------------------------------------------
VIEWS = {
    "side": {"name": "профиль", "rating": "лучший",
             "why": "читаются свод, подъём и линия пальцев без искажений"},
    "three_quarter": {"name": "три четверти", "rating": "хороший",
                      "why": "видно и подъём, и пальцы, сокращение умеренное"},
    "from_behind": {"name": "сзади", "rating": "хороший",
                    "why": "пятка и ахилл, сильный силуэт на каблуке"},
    "front_toes": {"name": "спереди на пальцы", "rating": "осторожно",
                   "why": "пальцы доминируют, легко получить «лопату»"},
    "sole_to_camera": {"name": "подошвой в камеру", "rating": "опасный",
                       "why": "максимальное сокращение: длина и ширина раздуваются — главная причина ласт"},
}

# 3. промпт ------------------------------------------------------------------
POSITIVE = {
    "size": ["petite feet", "small dainty feet", "slim ankles", "delicate feet"],
    "anatomy": ["slender foot", "high arch", "defined instep", "narrow ankle",
                "tapered toes", "graceful foot line",
                "long slender toes", "even toe taper", "groomed toenails"],
    "presentation": ["foot in three-quarter view", "side view of the foot",
                     "heel raised", "toes pointed", "weight on the ball of the foot"],
    "surface": ["soft skin shading on the foot", "subtle sheen on the instep",
                "painted toenails"],
}

NEGATIVE = ["large feet", "big feet", "oversized feet", "broad feet", "clown feet",
            "long feet", "flat feet", "wide foot", "splayed toes",
            "fused toes", "extra toes", "missing toes", "sausage toes",
            "oversized foot", "shoe too big", "clown shoes", "deformed toes"]

# «Опасные» формулировки: их присутствие без страховки даёт ласт
RISKY = ("sole toward camera", "soles toward camera", "sole presented",
         "presenting foot", "soles", "sole focus", "foot sole")


def blocks() -> dict[str, str]:
    return {
        "positive": ", ".join(p for group in POSITIVE.values() for p in group),
        "negative": ", ".join(NEGATIVE),
    }


def check(prompt: str, negative: str = "") -> list[str]:
    """Вернуть список проблем в промпте с точки зрения анатомии стопы."""
    p = prompt.lower().replace("_", " ")
    n = negative.lower().replace("_", " ")
    problems: list[str] = []

    risky = [t for t in RISKY if t in p]
    if risky:
        guarded = any(k in p for k in ("three-quarter", "side view", "short foot",
                                       "fore-shortened", "foreshortened"))
        if not guarded:
            problems.append(
                f"ракурс подошвы без страховки ({', '.join(risky[:2])}) — "
                "добавь 'foot in three-quarter view' или 'side view of the foot'")
    missing = [t for t in ("long feet", "flat feet", "splayed toes") if t not in n]
    if missing and risky:
        problems.append(f"в негативе нет анти-ласт тегов: {', '.join(missing)}")
    if not any(t in p for t in ("high arch", "defined instep", "slender foot")):
        problems.append("нет анатомического якоря стопы (high arch / defined instep)")
    if not any(t in p for t in ("petite feet", "small dainty feet", "delicate feet")):
        problems.append("стопа не задана как небольшая (petite feet) — выйдет крупной")
    if not any(t in p for t in ("groomed toenails", "painted toenails", "polished nails")):
        problems.append("нет ухоженных ногтей — теряется главный сигнал фут-контента")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", action="store_true")
    ap.add_argument("--views", action="store_true")
    ap.add_argument("--check", nargs=2, metavar=("PROMPT", "NEGATIVE"), default=None)
    ap.add_argument("--check-prompt", metavar="PROMPT")
    a = ap.parse_args()

    if a.views:
        for key, v in VIEWS.items():
            print(f"{v['rating']:<9} {v['name']:<18} {v['why']}")
        return
    if a.check or a.check_prompt:
        prompt, negative = (a.check if a.check else (a.check_prompt, ""))
        problems = check(prompt, negative)
        print("\n".join(f"  ✗ {p}" for p in problems) if problems else "  ✓ стопа задана корректно")
        return
    b = blocks()
    print("POSITIVE:", b["positive"])
    print("\nNEGATIVE:", b["negative"])
    print("\nпропорции:")
    for k, v in PROPORTIONS.items():
        print(f"  {k:<14} {v}")


if __name__ == "__main__":
    main()
