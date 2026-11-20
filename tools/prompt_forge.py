"""
prompt_forge.py — сборка промпта под героиню, модель и уровень «горячести».

Три идеи, которые здесь зашиты:

1. ФИГУРА И КОСТЮМ НЕ РАНДОМИЗИРУЮТСЯ. Они приходят из карточки героини
   (`content/characters/<id>.json`). Случайность — только в позе/камере/аксессуарах.

2. У КАЖДОЙ МОДЕЛИ СВОЙ ЯЗЫК. Anima ждёт теги строчными с пробелами, артистов
   через `@` и веса примерно вдвое выше SDXL. Pony требует score-тиры. Illustrious
   любит боро-теги и тег `manhwa_style`. Flux вообще не понимает теги.

3. «ГОРЯЧЕЕ» — ЭТО НЕ КОЛИЧЕСТВО ТЕГОВ, А ЧЕТЫРЕ РЫЧАГА: близость кадра,
   физика ткани, сигналы кожи и направление взгляда. Уровень L2 добавляет
   натяжение и полупрозрачность, L3 — только в отдельном age-gated канале.

Использование:
    python3 tools/prompt_forge.py --heroine selena --model anima --heat 2
    python3 tools/prompt_forge.py --heroine reika --model pony --heat 3 --json
    python3 tools/prompt_forge.py --heroine yuna --ladder          # L1/L2/L3 разом
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

sys.path.insert(0, str(ROOT))
from prompt_build import _lines  # noqa: F401  (проверка, что модуль на месте)

# --- профили моделей --------------------------------------------------------
MODELS = {
    "anima": {
        "quality": "masterpiece, best quality, score_7",
        "weight_scale": 2.0,            # Anima: (tag:2), а не (tag:1.2)
        "artist_prefix": "@",
        "trigger": "",
        "params": {"steps": 32, "cfg": 4.5, "sampler": "euler", "clip_skip": 1,
                   "resolution": "1024x1536"},
    },
    "illustrious": {
        "quality": "masterpiece, best quality, very aesthetic, absurdres",
        "weight_scale": 1.2,
        "artist_prefix": "",
        "trigger": "manhwa_style",      # LoRA-триггер стиля манхвы, сила 0.75–1.0
        "params": {"steps": 30, "cfg": 4.5, "sampler": "dpmpp_2m_karras", "clip_skip": 2,
                   "resolution": "832x1216", "lora": {"manhwa_style_lora": 0.85}},
    },
    "pony": {
        "quality": "score_9, score_8_up, score_7_up, score_6_up, source_anime",
        "weight_scale": 1.2,
        "artist_prefix": "",
        "trigger": "manhwastyle",
        "params": {"steps": 28, "cfg": 6.5, "sampler": "euler_a", "clip_skip": 2,
                   "resolution": "832x1216"},
    },
    "flux": {
        "quality": "",
        "weight_scale": 1.0,
        "artist_prefix": "",
        "trigger": "",
        "params": {"steps": 28, "cfg": 3.5, "sampler": "euler", "clip_skip": 0,
                   "resolution": "1024x1536"},
    },
}

RATING = {"pony": {1: "rating_safe", 2: "rating_questionable", 3: "rating_explicit"}}

# --- уровни «горячести» -----------------------------------------------------
# Рычаги: близость, ткань, кожа, взгляд. Ничего лишнего — каждый тег проверяем.
HEAT = {
    1: {  # намекающая: одежда целиком, никакой кожи сверх обычного
        "tags": ["form-fitting", "sheer legwear", "high heels", "confident posture"],
        "camera": "cowboy shot",
        "expression": ["light smile", "smirk", "looking at viewer"],
        "note": "база для соцсетей и сторов",
    },
    2: {  # горячо в рамках одежды (целевой уровень проекта)
        "tags": ["(fabric tension:1.15)", "translucent fabric", "cleavage", "bare shoulders",
                 "glossy skin", "sweat on skin", "underboob" ],
        "camera": "full body, low angle, from below",
        "expression": ["blush", "parted lips", "half-closed eyes", "looking down at viewer"],
        "note": "мокрый шёлк, подвязки, разрез, видимая линия белья",
    },
    3: {  # только отдельный age-gated канал, не в базовой сборке
        "tags": ["nude", "nipples", "wet skin", "arched back", "spread legs"],
        "camera": "full body, low angle, extreme close-up",
        "expression": ["heavy breathing", "tongue out", "half-closed eyes", "blush"],
        "note": "L3: своя платёжка, своя модерация, без мобильных сторов",
    },
}

# --- фетиш героини из temperament → промпт-теги -----------------------------
FETISH_TAGS = {
    "selena": ["stiletto heels", "shoe dangle", "toes", "foot focus", "anklet"],
    "reika": ["tight dress", "mature female", "wide hips", "lipstick", "gold jewelry"],
    "yuna": ["engagement ring", "open back", "patterned sheer tights", "heel pop", "wide hips"],
    "irene": ["barefoot", "arched instep", "toes pointed", "abs", "toned", "sweat on skin"],
    "sora": ["shortstack", "denim jacket", "crossed ankles", "high ponytail"],
    "mika": ["glasses", "sheer black pantyhose", "pantyhose feet", "shoe off", "office lady"],
    "nova": ["tan skin", "long blonde hair", "belly chain", "hip sway", "looking over shoulder"],
}

# РЕГИСТРЫ СТИЛЯ. v6 был одним зашитым набором — теперь это параметр:
# владелец отверг «полуглянцевый AI-рендер», и лечится это не силой тегов,
# а сменой регистра. Каждый регистр — свой набор якорей и свой анти-якорь.
STYLES = {
    # ЦЕЛЕВОЙ регистр: топовый манхва/хентай-рендер (не комикс).
    # Принцип: тонкая чистая линия + МЯГКИЕ градиенты + насыщенные красно-
    # фиолетовые тени на коже + глянцевый блик. Плоский cel и толстый контур —
    # это комикс, владелец его отклонил.
    "hentai-render": {
        "anchors": ["clean thin lineart", "tapered line ends", "soft gradient shading",
                    "saturated red-violet skin shadows", "glossy specular highlights",
                    "detailed iris with layered highlights", "rim light",
                    "cinematic color grading", "fashion-detail fabric folds"],
        "neg": ["flat cel shading", "thick comic outline", "spot blacks", "screentone",
                "airbrushed plastic skin", "3d render", "chibi"],
        "note": "манхва/хентай-рендер: тонкая линия, мягкий градиент, глянец, насыщенная тень",
    },
    # A. чернильный кадр: ближе всего к печатной манге/манхве-панели
    "ink-panel": {
        "anchors": ["bold ink lineart", "variable line weight", "flat cel shading",
                    "spot blacks", "screentone accents", "limited palette",
                    "dramatic panel composition", "high contrast"],
        "neg": ["airbrushed", "3d render", "plastic skin", "soft focus", "gradient mesh"],
        "note": "печатная панель: чёрные плашки, тон, никакого глянца",
    },
    # B. цветная манхва: толстая линия + сдержанный цвет, «как вебтун-драма»
    "manhwa-color": {
        "anchors": ["thick lineart", "two-tone cel shading", "muted palette",
                    "cool violet shadow", "selective rim light", "detailed fabric folds",
                    "manhwa style"],
        "neg": ["airbrushed", "3d render", "oversaturated", "glossy plastic"],
        "note": "цветная манхва: линия главная, цвет подчинён",
    },
    # C. baseline v6 — то, что было и не понравилось; оставлен для сравнения
    "webtoon-drama": {
        "anchors": ["thick lineart", "soft cel shading", "detailed fabric folds",
                    "glossy highlights", "cinematic rim light", "manhwa style"],
        "neg": [],
        "note": "v6: полуглянцевый рендер — отклонён владельцем, нужен как baseline",
    },
}
DEFAULT_STYLE = "hentai-render"

# Тег, который тянет в противоположный регистр, выбрасываем — иначе «без глянца»
# и «glossy skin» стоят в одной строке и модель слушает обоих.
STYLE_VETO = {
    "ink-panel": {"glossy skin", "glossy highlights", "glossy hair"},
    "manhwa-color": {"glossy highlights"},
}

BASE_NEG = ["lowres", "worst quality", "bad anatomy", "bad hands", "extra digits",
            "fused fingers", "deformed feet", "broken heel", "cropped feet", "cropped hands",
            "jpeg artifacts", "watermark", "signature", "text"]
CANON_NEG = ["plump", "chubby", "soft belly", "same face syndrome",
             "identical body types", "child-like proportions", "chibi"]
# «short hair» в негатив попадает ТОЛЬКО если героиня длинноволосая:
# иначе инструмент сам запрещает то, чего владелец требует (короткостриженая tomboy).
SHORT_HAIR_NEG = "short hair"
CENSOR_NEG = ["mosaic censoring", "bar censor", "hair over breasts", "steam"]


def _w(tag: str, scale: float, weight: float | None = None) -> str:
    """Применить вес в синтаксисе конкретной модели."""
    if weight is None:
        return tag
    return f"({tag}:{weight * scale:.1f})"


def _dedupe(prompt: str) -> str:
    """Убрать повторы тегов, сохранив порядок и вес первого вхождения."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in prompt.split(","):
        tok = raw.strip()
        key = re.sub(r"^\(|\)$", "", tok).split(":")[0].strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(tok)
    return ", ".join(out)


def _is_short_haired(card: dict) -> bool:
    pool = " ".join(card["body"].get("figure_tags", []) +
                    card["body"].get("style_tags", []) +
                    card.get("pose_language", {}).get("silhouette", []) if isinstance(
                        card.get("pose_language"), dict) else card["body"].get("figure_tags", []))
    pool += " " + str(card.get("archetype", ""))
    return "short hair" in pool.lower() or "bob" in pool.lower()


def _maturity():
    try:
        import maturity
        return maturity
    except Exception:
        return None


def load_card(char_id: str) -> dict:
    path = ROOT / "content" / "characters" / f"{char_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"нет карточки героини: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _foot_block() -> tuple[str, list[str], list[str]]:
    """Анатомия стопы: позитив, негатив и предупреждения валидатора."""
    try:
        import foot_spec
    except Exception:
        return "", [], []
    b = foot_spec.blocks()
    return b["positive"], b["negative"].split(", "), []


def _fingerprint() -> dict:
    """Блоки, снятые с реального корпуса (см. tools/prompt_miner.py)."""
    import json as _json
    path = ROOT / "assets" / "prompts" / "fingerprint.json"
    if not path.exists():
        return {}
    try:
        return _json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def forge(char_id: str, model: str = "anima", heat: int = 2,
          seed: int | None = None, focus: str | None = None,
          style: str = DEFAULT_STYLE, from_fp: bool = False) -> dict:
    prof = MODELS[model]
    card = load_card(char_id)
    body = card["body"]
    level = HEAT[heat]
    rng = random.Random(seed)

    parts: list[str] = []
    if prof["quality"]:
        parts.append(prof["quality"])
    if prof["trigger"]:
        parts.append(prof["trigger"])
    if model == "pony":
        parts.append(RATING["pony"][heat])

    # субъект и фигура — из карточки, без рандома
    parts.append("1girl, solo, adult woman")
    parts.append(f"({', '.join(body.get('figure_tags', []))}:{1.25 * prof['weight_scale']:.1f})")

    # фетиш/фишка героини
    fetish = FETISH_TAGS.get(char_id, [])
    if focus and focus in fetish:
        parts.append(f"({focus}:{1.3 * prof['weight_scale']:.1f})")
    parts.append(", ".join(fetish))

    # режим Green/Mature: в green кадр не выходит за heat 1 и подписывается как «одета»
    mat = _maturity()
    maturity_note = ""
    if mat is not None:
        limit = mat.cap()
        if heat > limit["heat"]:
            maturity_note = f"heat {heat} → {limit['heat']} (режим {mat.load()['mode']})"
            heat = max(1, limit["heat"])
            level = HEAT[min(heat, 3)]
        suffix = mat.prompt_suffix()
        if suffix:
            parts.append(suffix)

    # стопа: у героинь с фут-акцентом анатомия задаётся явно, иначе модель
    # рисует «ласту» — длинную плоскую стопу с растопыренными пальцами
    foot_level = int(body.get("feet_focus_level") or 0)
    foot_warn: list[str] = []
    if foot_level >= 2:
        foot_pos, foot_neg, _ = _foot_block()
        if foot_pos:
            parts.append(foot_pos)
            negative_extra = list(foot_neg)
        else:
            negative_extra = []
    else:
        negative_extra = []

    # ткань как физика: материал + плетение + свет + поведение (облегает/просвечивает/рвётся)
    fabric_block, fabric_neg = "", []
    try:
        import fabric as _fabric
        outfit = ", ".join((card.get("wardrobe_default") or {}).get("prompt_tags", []))
        allowed = ("cling", "sheer", "tear", "wet") if heat >= 2 else ("cling", "sheer")
        beh = _fabric.behaviors_for(outfit, allowed)
        fabric_block = _fabric.build(outfit, beh)
        fabric_neg = list(_fabric.NEGATIVE)
    except Exception:
        pass

    # костюм
    wardrobe = card.get("wardrobe_default", {}).get("prompt_tags", [])[:6]
    parts.append(", ".join(wardrobe))
    if fabric_block:
        parts.append(fabric_block)

    # поза: авторская из карточки + уровневые теги
    if card.get("pose_prompt"):
        pose = card["pose_prompt"]
        # страховка: «подошвой в камеру» = максимальное сокращение = ласта.
        # Переписываем на трёхчетвертной ракурс, не теряя «фишку» позы.
        low = pose.lower()
        if any(t in low for t in ("sole presented", "sole toward", "soles toward",
                                  "foot presented toward", "presenting foot")):
            pose = (pose.replace("sole presented toward the camera",
                                 "the free foot turned three-quarter so the arch reads")
                        .replace("soles toward the camera", "the foot turned three-quarter")
                        .replace("one foot presented toward the camera",
                                 "one foot in three-quarter view, arch tensed")
                        .replace("presenting foot", "foot in three-quarter view"))
            parts.append("foot in three-quarter view, high arch, defined instep")
        parts.append(pose)
    parts.append(", ".join(level["tags"]))
    parts.append(rng.choice(level["expression"]))

    # камера и стиль
    parts.append(level["camera"])
    reg = STYLES[style]
    parts.append(", ".join(reg["anchors"]))

    # блоки из корпуса: качество и защита, проверенные на 2481 реальном промпте
    fp = _fingerprint() if from_fp else {}
    if from_fp:
        q = [t for t in ("masterpiece", "best quality", "highres") if
             t in (fp.get("top_positive") or {})]
        if q:
            parts.insert(1, ", ".join(q))

    negative = list(BASE_NEG) + list(CANON_NEG) + (list(CENSOR_NEG) if heat >= 2 else [])
    negative += list(reg["neg"]) + negative_extra + fabric_neg
    if not _is_short_haired(card):
        negative.append(SHORT_HAIR_NEG)

    raw = ", ".join(p for p in parts if p)
    veto = STYLE_VETO.get(style, set())
    if veto:
        raw = ", ".join(t for t in (x.strip() for x in raw.split(","))
                        if t.split(":")[0].strip("()").lower() not in veto)
    prompt = _dedupe(raw)
    if model == "flux":
        prompt = _to_natural(card, level, fetish)

    if foot_level >= 3:
        try:
            import foot_spec
            foot_warn = foot_spec.check(prompt, ", ".join(negative))
        except Exception:
            foot_warn = []

    return {
        "maturity": maturity_note or f"режим {mat.load()['mode']}" if mat is not None else "",
        "foot_warnings": foot_warn,
        "heroine": char_id,
        "model": model,
        "style": style,
        "style_note": reg["note"],
        "heat": heat,
        "focus": focus,
        "prompt": prompt,
        "negative": ", ".join(negative),
        "params": prof["params"],
        "note": level["note"],
    }


def _to_natural(card: dict, level: dict, fetish: list[str]) -> str:
    """Flux не понимает теги — то же содержание, но прозой."""
    body = card["body"]
    figure = ", ".join(body.get("figure_tags", [])[:5])
    wardrobe = ", ".join(card.get("wardrobe_default", {}).get("prompt_tags", [])[:4])
    return (
        f"Korean manhwa illustration of an adult woman, {card['age']} years old. "
        f"Her figure is {figure}. She wears {wardrobe}. "
        f"{card.get('pose_prompt', '')}. "
        f"The mood is {level['note']}; the framing is {level['camera']}. "
        f"Rendered with thick clean lineart, soft cel shading, glossy skin highlights and "
        f"a cinematic rim light, full body, head to toe, shoes fully inside the frame."
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--heroine", required=True)
    ap.add_argument("--model", default="anima", choices=sorted(MODELS))
    ap.add_argument("--heat", type=int, default=2, choices=[1, 2, 3])
    ap.add_argument("--focus")
    ap.add_argument("--style", default=DEFAULT_STYLE, choices=sorted(STYLES))
    ap.add_argument("--from-fp", action="store_true",
                    help="добавить блоки качества из корпуса (assets/prompts/fingerprint.json)")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--ladder", action="store_true", help="показать L1/L2/L3 разом")
    a = ap.parse_args()

    levels = [1, 2, 3] if a.ladder else [a.heat]
    results = [forge(a.heroine, a.model, h, a.seed, a.focus, a.style, a.from_fp)
               for h in levels]

    if a.json:
        print(json.dumps(results if a.ladder else results[0], ensure_ascii=False, indent=2))
        return
    for r in results:
        print(f"\n=== {r['heroine']} · {r['model']} · {r['style']} · L{r['heat']}")
        print(f"    стиль: {r['style_note']} · уровень: {r['note']}")
        print(f"PROMPT:   {r['prompt']}")
        print(f"NEGATIVE: {r['negative']}")
        for w in r.get("foot_warnings") or []:
            print(f"  ⚠ стопа: {w}")
        p = r["params"]
        print(f"PARAMS:   {p['steps']} steps · cfg {p['cfg']} · {p['sampler']} · "
              f"clip skip {p['clip_skip']} · {p['resolution']}")


if __name__ == "__main__":
    main()
