"""Тесты форжа промптов: язык модели, лестница горячести, защита канона."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))

import prompt_forge as pf  # noqa: E402


def test_forge_returns_contract():
    r = pf.forge("selena", model="anima", heat=2, seed=1)
    for key in ("prompt", "negative", "params", "heat", "model", "note"):
        assert key in r
    assert "1girl" in r["prompt"] and "selena" == r["heroine"]


def test_figure_comes_from_card_not_random():
    card = pf.load_card("selena")
    r1 = pf.forge("selena", model="anima", heat=1, seed=10)
    r2 = pf.forge("selena", model="anima", heat=1, seed=99)
    for tag in card["body"]["figure_tags"]:
        assert tag in r1["prompt"] and tag in r2["prompt"]


def test_heat_levels_escalate():
    prompts = {h: pf.forge("yuna", heat=h, seed=5)["prompt"] for h in (1, 2, 3)}
    assert "underboob" not in prompts[1] and "underboob" in prompts[2]
    assert "nipples" in prompts[3] and "nipples" not in prompts[2]
    assert len(set(prompts.values())) == 3


def test_pony_rating_map():
    assert "rating_safe" in pf.forge("reika", model="pony", heat=1)["prompt"]
    assert "rating_questionable" in pf.forge("reika", model="pony", heat=2)["prompt"]
    assert "rating_explicit" in pf.forge("reika", model="pony", heat=3)["prompt"]


def test_illustrious_carries_manhwa_trigger():
    r = pf.forge("mika", model="illustrious", heat=2)
    assert "manhwa_style" in r["prompt"]
    assert r["params"]["sampler"] == "dpmpp_2m_karras"


def test_anima_weights_are_doubled():
    # у Anima вес идёт ×2: проверяем по фигурному блоку
    r = pf.forge("irene", model="anima", heat=1)
    assert ":2.5)" in r["prompt"]


def test_flux_uses_prose_not_weights():
    r = pf.forge("nova", model="flux", heat=2)
    assert "(" not in r["prompt"] and ":" not in r["prompt"].split(".")[0]
    assert "manhwa" in r["prompt"].lower()


def test_no_duplicate_tags():
    r = pf.forge("selena", model="anima", heat=2, seed=3)
    tags = [t.strip().split(":")[0].strip("()") for t in r["prompt"].split(",")]
    dupes = [t for t in set(tags) if tags.count(t) > 1]
    assert not dupes, f"повторы: {dupes}"


def test_short_hair_negative_is_conditional():
    # канон требует короткостриженую героиню — инструмент не должен её запрещать
    assert "short hair" in pf.forge("selena", heat=2)["negative"]
    assert pf._is_short_haired({"body": {"figure_tags": ["bob cut"]}}) is True
    assert pf._is_short_haired({"body": {"figure_tags": ["long legs"]}}) is False


def test_censor_negatives_only_from_l2():
    assert "mosaic censoring" not in pf.forge("sora", heat=1)["negative"]
    assert "mosaic censoring" in pf.forge("sora", heat=2)["negative"]
