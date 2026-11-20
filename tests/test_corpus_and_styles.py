"""Корпус, атлас, регистры стиля и турнирный пакет."""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import arena_task  # noqa: E402
import prompt_forge as pf  # noqa: E402
import prompt_miner as pm  # noqa: E402
import tag_db  # noqa: E402


# --- корпус ---------------------------------------------------------------
def test_corpus_loaded_and_parsable():
    rows = pm.load()
    assert len(rows) > 1000, "корпус должен быть, а не пустой файл"
    assert all("prompt" in r and "negative" in r for r in rows[:50])


def test_tokens_strip_weights_and_brackets():
    toks = pm.tokens("(masterpiece:1.2), best quality")
    assert "masterpiece" in toks and "best quality" in toks
    assert all("1.2" not in t for t in toks)


def test_fingerprint_is_real():
    fp = pm.mine(pm.load())
    assert fp["total"] > 1000
    # в реальном корпусе негатив low quality стоит почти везде
    assert fp["top_negative"].get("low quality", 0) > 50
    assert fp["top_positive"].get("masterpiece", 0) > 20


def test_cooccur_never_exceeds_100_percent():
    rows = pm.load()
    res = pm.cooccur(rows, "anime", 10)
    if res:
        total = res[0][2]
        assert all(k <= total for _, k, _ in res), "тег посчитан дважды в одном промпте"


# --- атлас ----------------------------------------------------------------
def test_atlas_terms_have_real_frequencies():
    data = tag_db.atlas()
    assert set(data) >= {"act_solo", "act_pair", "fetish_feet", "face_heat"}
    for group, rows in data.items():
        for tag, count in rows:
            assert count > 0, f"{group}/{tag}: частота должна быть реальной"
    feet = dict(data["fetish_feet"])
    assert feet["barefoot"] > 100_000
    assert feet["presenting foot"] < 10_000     # ниша, держим позой, а не тегом


# --- регистры стиля -------------------------------------------------------
def test_styles_differ_and_veto_works():
    prompts = {s: pf.forge("selena", heat=2, style=s)["prompt"] for s in pf.STYLES}
    assert len(set(prompts.values())) == len(pf.STYLES)
    assert "screentone accents" in prompts["ink-panel"]
    # конфликтующий тег не должен дожить до промпта
    assert "glossy skin" not in prompts["ink-panel"]
    assert "glossy skin" in prompts["webtoon-drama"]


def test_style_negatives_applied():
    ink = pf.forge("mika", heat=2, style="ink-panel")["negative"]
    for bad in ("airbrushed", "3d render", "plastic skin"):
        assert bad in ink


def test_from_fingerprint_adds_corpus_quality_block():
    plain = pf.forge("yuna", heat=2, style="manhwa-color")["prompt"]
    with_fp = pf.forge("yuna", heat=2, style="manhwa-color", from_fp=True)["prompt"]
    assert with_fp != plain
    assert "masterpiece" in with_fp and "best quality" in with_fp


# --- турнир ---------------------------------------------------------------
def test_tournament_package_is_complete(tmp_path):
    files = arena_task.build_tournament("selena", heat=2, reject_reason="тест: глянец")
    assert set(files) == {"task.md", "rubric.md", "cards.md", "README.md", "baseline.md"}
    task = files["task.md"]
    assert "тест: глянец" in task          # причина отказа обязана попасть в задачу
    assert "ink-panel" in task and "manhwa-color" in task
    assert "fatal" in files["rubric.md"]
    assert len(files["cards.md"].splitlines()) >= 8
    for name, text in files.items():
        assert len(text) > 100, f"{name} слишком короткий"
