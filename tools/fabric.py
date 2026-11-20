"""
fabric.py — ткань как физика, а не как слово.

Проблема, которую это решает. Если написать «silk dress», модель нарисует
материал, который выглядит как пластик: он не мнётся, не натягивается и не
просвечивает. Ткань оживает, когда в промпте есть четыре вещи:

    материал + плетение/плотность + как ведёт себя под телом + как ловит свет

Отсюда и три обещанных поведения:

  cling  — облегает: натяжение, складки от натяжения, повторяет контур;
  sheer  — просвечивает: тонкость, свет сквозь волокно, силуэт под тканью;
  tear   — рвётся: спущенная петля, разошедшийся шов, бахрома, зацепка.

Плюс отдельный словарь негатива: «пластиковая ткань», «плывущая ткань»,
«слипание ткани с кожей» — это те дефекты, которые ломают кадр.

    python3 tools/fabric.py --list
    python3 tools/fabric.py --build "black off-shoulder bodycon dress, sheer black pantyhose"
    python3 tools/fabric.py --check "<prompt>"
    python3 tools/fabric.py --for selena
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Материал: теги, как ловит свет, как движется.
MATERIALS: dict[str, dict] = {
    "silk": {"tags": ["silk habotai", "fine silk weave"], "light": ["soft specular roll-off", "liquid sheen"],
             "motion": ["fluid folds", "rippling"]},
    "satin": {"tags": ["heavy satin", "smooth satin face"], "light": ["highlight streak along the fold"],
              "motion": ["cascading folds"]},
    "chiffon": {"tags": ["gossamer chiffon", "diaphanous weave"], "light": ["light bleed through fibers"],
                "motion": ["floating hem", "drifting"]},
    "organza": {"tags": ["crisp organza", "hexagonal weave visible"], "light": ["refracted edge glow"],
                "motion": ["holding shape", "crisp pleats"]},
    "tulle": {"tags": ["fine tulle mesh"], "light": ["diffuse soft glow"],
              "motion": ["airy layers"]},
    "mesh": {"tags": ["fishnet mesh", "uniform diamond weave"], "light": ["micro-shadows in the gaps"],
             "motion": ["following the body"]},
    "lace": {"tags": ["floral lace with openwork"], "light": ["patterned shadow on skin"],
             "motion": ["delicate drape"]},
    "jersey": {"tags": ["fine-gauge jersey knit"], "light": ["matte with soft sheen"],
               "motion": ["stretched over curves", "tension folds"]},
    "knit": {"tags": ["fine-gauge knit with visible rib"], "light": ["halo from fiber ends"],
             "motion": ["stretched ribbing"]},
    "velvet": {"tags": ["crushed velvet pile"], "light": ["directional sheen, deep absorption"],
               "motion": ["heavy drape"]},
    "leather": {"tags": ["supple lambskin leather"], "light": ["tight glossy highlight"],
                "motion": ["creased at the hip"]},
    "latex": {"tags": ["polished latex"], "light": ["mirror-like specular"],
              "motion": ["vacuum fit"]},
    "denim": {"tags": ["rigid cotton denim, visible twill"], "light": ["low sheen, seam highlights"],
              "motion": ["creasing at the hip"]},
    "wool": {"tags": ["wool crepe, visible grain"], "light": ["matte, side-lit grain"],
             "motion": ["structured drape"]},
    "linen": {"tags": ["slubby linen weave"], "light": ["matte, soft edge"],
              "motion": ["relaxed folds"]},
    "nylon": {"tags": ["12 denier sheer nylon", "sheer black pantyhose"],
              "light": ["glossy sheen over the shin", "thin highlight along the arch"],
              "motion": ["clinging to the leg"]},
    "spandex": {"tags": ["stretch spandex"], "light": ["satin-like sheen"],
                "motion": ["bodycon fit"]},
}

# Поведение ткани. Ключевые слова, по которым узнаём материал в костюме.
BEHAVIORS: dict[str, dict] = {
    "cling": {
        "tags": ["fabric clinging to the body", "tension folds radiating from the hip",
                 "fabric stretched taut across the thigh", "bodycon fit following every curve"],
        "why": "облегание читается по натяжению и по складкам, которые идут ОТ точки натяжения",
    },
    "sheer": {
        "tags": ["sheer to the point of silhouette", "light bleeding through the fibers",
                 "skin tone visible beneath the weave", "thin fabric with subsurface light scatter"],
        "why": "просвечивает не «прозрачность», а свет: нужен свет сквозь волокно и силуэт под тканью",
    },
    "tear": {
        "tags": ["ladder run in the stocking", "split seam at the thigh",
                 "frayed hem with loose threads", "snagged weave, pulled thread"],
        "why": "разрыв должен быть физическим: петля, шов, зацепка — а не абстрактная «дырка»",
    },
    "wet": {
        "tags": ["damp fabric clinging transparently", "water droplets refracting light",
                 "semi-opaque where soaked"],
        "why": "мокрая ткань = облегание + просвет + преломление одновременно",
    },
}

NEGATIVE = ["plastic fabric", "melted cloth", "cloth merging with skin", "floating fabric",
            "undifferentiated cloth", "stiff cardboard fabric", "cloth texture noise",
            "random wrinkles", "fabric clipping through the body"]

# Как узнать материал по тегам костюма из карточки.
DETECT = [
    ("nylon", ("pantyhose", "tights", "stockings")),
    ("leather", ("leather",)),
    ("latex", ("latex", "pvc")),
    ("denim", ("denim", "jeans")),
    ("knit", ("knit", "turtleneck")),
    ("jersey", ("bodycon", "jersey", "tee", "t-shirt")),
    ("satin", ("satin",)),
    ("chiffon", ("chiffon",)),
    ("mesh", ("mesh", "fishnet")),
    ("lace", ("lace",)),
    ("silk", ("silk", "blouse", "shirt")),
    ("wool", ("wool", "trousers", "pencil skirt")),
    ("tulle", ("tulle",)),
]


def detect_materials(outfit: str) -> list[str]:
    low = (outfit or "").lower()
    found = [mat for mat, keys in DETECT if any(k in low for k in keys)]
    return found or ["silk"]


def behaviors_for(outfit: str, allowed: tuple[str, ...] = ("cling", "sheer", "tear")) -> list[str]:
    low = (outfit or "").lower()
    out = []
    if any(k in low for k in ("bodycon", "tight", "pencil", "body-hugging", "mini")):
        out.append("cling")
    sheer_hit = any(k in low for k in ("sheer", "tulle", "mesh", "chiffon", "lace"))
    hosiery = any(k in low for k in ("pantyhose", "tights", "stockings"))
    opaque = "opaque" in low
    if sheer_hit or (hosiery and not opaque):
        out.append("sheer")
    if "rip" in low or "torn" in low:
        out.append("tear")
    return [b for b in out if b in allowed]


def build(outfit: str, behaviors: list[str] | None = None) -> str:
    """Собрать блок ткани: материал + свет + движение + поведение."""
    mats = detect_materials(outfit)
    behs = behaviors if behaviors is not None else behaviors_for(outfit)
    parts: list[str] = []
    for m in mats[:2]:
        info = MATERIALS[m]
        parts += info["tags"][:1] + info["light"][:1] + info["motion"][:1]
    for b in behs:
        parts += BEHAVIORS[b]["tags"][:2]
    return ", ".join(dict.fromkeys(parts))


def check(prompt: str) -> list[str]:
    """Есть ли в промпте физика ткани и защита от «пластика»."""
    low = (prompt or "").lower()
    problems = []
    has_material = any(t for m in MATERIALS.values() for t in m["tags"] if t.lower() in low)
    has_behavior = any(t.lower() in low for b in BEHAVIORS.values() for t in b["tags"])
    has_light = any(t.lower() in low for m in MATERIALS.values() for t in m["light"])
    if not has_material:
        problems.append("нет названия материала с плетением (silk habotai, fine-gauge jersey…)")
    if not has_behavior:
        problems.append("нет поведения ткани (clinging / light bleeding / ladder run)")
    if not has_light:
        problems.append("нет описания, как ткань ловит свет — будет пластик")
    if not any(t in low for t in ("plastic fabric", "melted cloth")):
        problems.append("в негативе нет защиты от пластиковой ткани")
    return problems


def for_heroine(cid: str) -> dict:
    card = json.loads((ROOT / "content" / "characters" / f"{cid}.json").read_text(encoding="utf-8"))
    outfit = ", ".join((card.get("wardrobe_default") or {}).get("prompt_tags", []))
    mats = detect_materials(outfit)
    behs = behaviors_for(outfit)
    return {"heroine": cid, "outfit": outfit, "materials": mats, "behaviors": behs,
            "block": build(outfit, behs), "negative": ", ".join(NEGATIVE)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--build")
    ap.add_argument("--check")
    ap.add_argument("--for", dest="heroine")
    a = ap.parse_args()

    if a.list:
        print("материалы:")
        for name, info in MATERIALS.items():
            print(f"  {name:<9} {info['tags'][0]:<32} свет: {info['light'][0]}")
        print("\nповедение:")
        for name, info in BEHAVIORS.items():
            print(f"  {name:<6} {info['why']}")
        return

    if a.heroine:
        res = for_heroine(a.heroine)
        print(f"{res['heroine']}: {', '.join(res['materials'])} · поведение: {', '.join(res['behaviors']) or '—'}")
        print("блок:", res["block"])
        print("негатив:", res["negative"])
        return

    if a.check:
        problems = check(a.check)
        print("\n".join(f"  ✗ {p}" for p in problems) if problems else "  ✓ физика ткани задана")
        return

    if a.build:
        print(build(a.build))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
