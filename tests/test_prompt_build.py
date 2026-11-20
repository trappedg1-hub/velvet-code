"""Промпт-стек: раскрыватель wildcard-шаблонов должен быть предсказуемым."""
import random
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tools.prompt_build import build, expand, _lines


def test_variants_resolve_to_one_of_the_options():
    rng = random.Random(1)
    for _ in range(20):
        assert expand("{red|black|white} dress", rng) in {"red dress", "black dress", "white dress"}


def test_wildcard_resolves_to_a_file_line():
    rng = random.Random(2)
    out = expand("__body_curvy__", rng)
    assert out in _lines("body_curvy")


def test_multi_pick_returns_distinct_lines():
    rng = random.Random(3)
    out = expand("{2$$__body_curvy__}", rng)
    parts = [p.strip() for p in out.split(",")]
    assert len(parts) >= 2


def test_nested_wildcards_expand():
    rng = random.Random(4)
    out = expand("{__pose_ecchi__|__camera__}", rng)
    assert "{" not in out and "__" not in out


def test_batch_is_deduplicated_and_seeded():
    tpl = "{a|b|c|d|e} __camera__"
    first = build(tpl, n=3, seed=11)
    second = build(tpl, n=3, seed=11)
    assert first == second
    assert len(set(first)) == len(first)


def test_missing_wildcard_raises():
    try:
        expand("__nope_not_here__", random.Random(0))
    except FileNotFoundError:
        return
    raise AssertionError("ожидался FileNotFoundError")


def test_validate_catches_conflicting_figures():
    from tools.prompt_build import validate, _lines
    two = _lines("figure_types")[:2]
    problems = validate("manhwa, " + ", ".join(two))
    assert any("взаимоисключающих" in p for p in problems)


def test_validate_clean_on_single_figure():
    from tools.prompt_build import validate, _lines
    problems = validate("manhwa style, " + _lines("figure_types")[3] + ", full body")
    assert not any("взаимоисключающих" in p for p in problems)


def test_heroine_prompt_is_single_figure_and_respects_feet_level():
    """Нова — gyaru; фигура берётся одна, акцент на стопах по уровню героини."""
    from tools.prompt_build import build_heroine
    p = build_heroine("nova", n=1, seed=1)[0]
    assert "gyaru" in p
    assert "foot_focus" not in p and "soles" not in p
    p3 = build_heroine("irene", n=1, seed=1)[0]
    assert "athletic" in p3 or "toned" in p3
