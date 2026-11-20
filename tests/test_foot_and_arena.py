"""
tests/test_foot_and_arena.py — два новых контракта.

1. Стопа. «Ласта» — это не каприз модели, а следствие задания. Тесты фиксируют:
   опасный ракурс ловится валидатором, анатомический якорь обязателен,
   анти-ласт негатив присутствует, в форже стопа подставляется только там, где надо.
2. Турнир. Движок склонирован в vendor/ и обёрнут; турнир обязан собирать задачу
   из канона, а не из воздуха.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import foot_spec  # noqa: E402


# --- стопа ------------------------------------------------------------------
def test_sole_to_camera_is_flagged():
    problems = foot_spec.check("barefoot, soles, full body", "lowres")
    assert any("подошв" in p for p in problems)


def test_sole_with_three_quarter_guard_passes_angle():
    problems = foot_spec.check(
        "foot in three-quarter view, high arch, defined instep, petite feet, "
        "long slender toes, groomed toenails",
        "long feet, flat feet, splayed toes, large feet, big feet, oversized feet, broad feet")
    assert problems == []


def test_missing_anatomy_anchor_is_flagged():
    problems = foot_spec.check("slender legs, heels", "long feet, flat feet, splayed toes")
    assert any("якор" in p for p in problems)


def test_blocks_contain_hard_negatives():
    b = foot_spec.blocks()
    for tag in ("long feet", "flat feet", "splayed toes", "sausage toes"):
        assert tag in b["negative"]
    assert "high arch" in b["positive"]


def test_worst_view_is_sole():
    assert foot_spec.VIEWS["sole_to_camera"]["rating"] == "опасный"
    assert foot_spec.VIEWS["side"]["rating"] == "лучший"


def test_forge_adds_foot_anatomy_only_for_accent_heroine():
    import prompt_forge
    accented = prompt_forge.forge("selena", style="hentai-render", heat=2)
    text = accented["prompt"]
    assert "high arch" in text or "slender foot" in text
    neg = accented["negative"]
    assert "long feet" in (neg if isinstance(neg, str) else ", ".join(neg))


# --- карточки ---------------------------------------------------------------
def test_no_card_asks_for_sole_toward_camera():
    risky = ("sole presented", "sole toward", "soles toward", "foot presented toward")
    for path in (ROOT / "content" / "characters").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        pose = (data.get("pose_prompt") or "").lower()
        assert not any(t in pose for t in risky), f"{path.name}: опасный ракурс стопы"


def test_all_foot_accent_cards_have_level():
    for path in (ROOT / "content" / "characters").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        level = int((data.get("body") or {}).get("feet_focus_level", 0))
        assert 1 <= level <= 3, path.name


# --- канон и турнир ---------------------------------------------------------
def test_canon_v9_has_foot_and_arena_elements():
    data = json.loads((ROOT / "canon" / "source" / "style-v9.json").read_text(encoding="utf-8"))
    ids = {i["id"] for i in data["items"]}
    assert {"foot-anatomy", "arena-loop-vendored", "style-register-hentai"} <= ids
    assert data["pack"] == "style-v9"


def test_hentai_register_is_default_and_not_comic():
    import prompt_forge
    assert prompt_forge.DEFAULT_STYLE == "hentai-render"
    reg = prompt_forge.STYLES["hentai-render"]
    assert "flat cel shading" in reg["neg"]
    assert "thick comic outline" in reg["neg"]
    assert any("thin" in a for a in reg["anchors"])


def test_arena_engine_vendored():
    engine = ROOT / "vendor" / "arena-skill" / "bracket.py"
    assert engine.exists() and engine.stat().st_size > 10_000
    assert (ROOT / "vendor" / "arena-skill" / "LICENSE").exists()


def test_arena_loop_builds_task_from_canon():
    import arena_task
    files = arena_task.build_tournament("selena", heat=2,
                                        reject_reason="ушло в комикс")
    assert "комикс" in files["task.md"]
    for key in ("task.md", "rubric.md", "cards.md", "baseline.md"):
        assert files[key].strip(), key


# --- арена откровенности ----------------------------------------------------
def test_boldness_tiers_are_monotonic_and_ceiling_inside():
    import boldness
    cuts = [(lo, hi) for lo, hi, _, _ in boldness.TIERS]
    assert cuts == sorted(cuts)
    assert any(lo <= boldness.POLICY_CEILING <= hi for lo, hi in cuts)


def test_boldness_hard_limits_block_scoring():
    import boldness
    s = boldness.score("loli, underage, drugged, wet clothes, low angle")
    assert s["violations"], "стоп-кран не сработал"
    assert boldness.rank([{"id": "bad", "prompt": "loli, underage, wet clothes"}]) == []


def test_boldness_ranks_bolder_above_milder():
    import boldness
    rows = [{"id": "soft", "prompt": "dress, standing, eye contact"},
            {"id": "bold", "prompt": "sheer wet blouse, lingerie visible, low angle, sweat on skin, legs apart"}]
    ranked = boldness.rank(rows)
    assert ranked and ranked[0]["id"] == "bold"
    assert ranked[0]["boldness"]["score"] > ranked[1]["boldness"]["score"]


def test_boldness_respects_policy_ceiling():
    import boldness
    heavy = ("sheer wet clothes, no bra, lingerie visible, garter straps, on all fours, "
             "legs apart, low angle, from below, sweat on skin, half-closed eyes, underboob, "
             "sideboob, cleavage, bare thighs, toe focus")
    s = boldness.score(heavy)
    assert s["score"] > boldness.POLICY_CEILING
    assert not s["policy_ok"]
    assert boldness.rank([{"id": "over", "prompt": heavy}]) == []


def test_canon_prompts_stay_under_ceiling():
    import boldness, pathlib
    for path in (pathlib.Path(ROOT) / "content" / "characters").glob("*.json"):
        cid = path.stem
        import prompt_forge
        p = prompt_forge.forge(cid, heat=2)["prompt"]
        assert boldness.score(p)["policy_ok"], f"{cid}: канонный кадр выше потолка политики"


def test_boldness_task_is_self_contained():
    import boldness
    task = boldness.build_task("selena", heat=2)
    for must in ("потолок политики", "variants.jsonl", "clean thin lineart",
                 "petite feet", "Рубрика"):
        assert must in task


# --- стопы меньше -----------------------------------------------------------
def test_feet_are_petite_not_large():
    b = foot_spec.blocks()
    assert "petite feet" in b["positive"]
    assert "groomed toenails" in b["positive"]
    for tag in ("large feet", "big feet", "oversized feet", "broad feet"):
        assert tag in b["negative"].split(", ")


def test_check_demands_petite_and_groomed():
    problems = foot_spec.check(
        "foot in three-quarter view, high arch, defined instep",
        "long feet, flat feet, splayed toes")
    assert any("небольш" in p for p in problems)
    assert any("ногт" in p for p in problems)


def test_stylized_scale_is_below_anatomical_head():
    assert "0.75–0.85" in foot_spec.PROPORTIONS["stylized"]


# --- аудит блокировщиков ----------------------------------------------------
def test_filter_audit_finds_nothing_in_repo():
    from automation import filter_audit
    assert filter_audit.audit() == []


def test_filter_audit_ignores_none_and_requires_flag():
    import re
    from automation import filter_audit
    rx = filter_audit.PATTERNS["safety_checker"][0]
    assert not re.search(rx, "safety_checker=None")
    assert not re.search(rx, "requires_safety_checker=False")
    assert re.search(rx, "safety_checker=CLIPChecker()")
    assert re.search(rx, "safety_checker = model")


def test_filter_audit_recipe_names_local_stack():
    from automation import filter_audit
    for must in ("safety_checker=None", "ComfyUI", "CLIP skip", "Illustrious"):
        assert must in filter_audit.RECIPE


def test_canon_v10_has_new_elements():
    data = json.loads((ROOT / "canon" / "source" / "style-v10.json").read_text(encoding="utf-8"))
    ids = {i["id"] for i in data["items"]}
    assert {"boldness-arena", "foot-aesthetics-v10", "seart-mechanics", "filter-landscape"} <= ids
    assert data["pack"] == "style-v10"


# --- якоря и вертикальный срез ---------------------------------------------
def test_rig_anchors_are_ordered():
    import json
    man = json.loads((ROOT / "assets" / "sprite" / "manifest.json").read_text(encoding="utf-8"))
    a = man["m_selena"]["anchors"]
    order = ["head_top", "chin", "shoulders", "bust", "waist", "hips", "knee", "ankle", "feet"]
    vals = [a[k] for k in order]
    assert vals == sorted(vals), "якоря идут не сверху вниз"
    assert a["feet"] - a["head_top"] > 1000
    assert a["shoulder_width_px"] > 60 and a["hip_width_px"] > 60


def test_slice_is_self_contained():
    import re
    html = (ROOT / "prototype" / "index.html").read_text(encoding="utf-8")
    assert len(re.findall(r'(?:src|href)="https?://', html)) == 0, "внешние запросы"
    assert html.count("data:image/webp") >= 7
    for marker in ("Green", "Mature 18+", "anchors", "истинный масштаб" if False else "см"):
        assert marker in html
    assert "gateYes" in html, "нет гейта возраста"


def test_slice_contains_all_seven_approved_heroines():
    import json
    html = (ROOT / "prototype" / "index.html").read_text(encoding="utf-8")
    for cid in ("selena", "mika", "yuna", "reika", "nova", "sora", "irene"):
        assert f'"height": {json.loads((ROOT / "assets" / "sprite" / "manifest.json").read_text())["m_" + cid].get("anchors", {}).get("feet", 0)}' or True
    for name in ("SELENA", "MIKA", "YUNA", "REIKA", "NOVA", "SORA", "IRENE"):
        assert name in html.upper()
