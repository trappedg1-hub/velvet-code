"""
tests/test_fabric_maturity_artifacts.py — четыре контракта этого захода.

1. Ткань — это физика: материал, свет, поведение. Иначе выходит пластик.
2. Негатив может саботировать сам себя: nuke/nsfw в негативе глушит кожу.
3. Green/Mature — гейт пайплайна, а не надпись на кнопке.
4. Артефакты лечатся измеримо. Отдельная регрессия: крупные просветы
   (между рукой и телом) нельзя заливать — это даёт «чёрную плиту».
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import fabric  # noqa: E402
import neg_audit  # noqa: E402
import maturity  # noqa: E402


# --- ткань ------------------------------------------------------------------
def test_fabric_block_has_material_light_and_behaviour():
    block = fabric.build("sheer black pantyhose, bodycon dress")
    low = block.lower()
    assert "nylon" in low or "jersey" in low
    assert "sheen" in low or "highlight" in low
    assert "clinging" in low or "tension folds" in low


def test_opaque_tights_do_not_go_sheer():
    beh = fabric.behaviors_for("white knotted tee, opaque tights, leather mini skirt")
    assert "sheer" not in beh
    beh2 = fabric.behaviors_for("black pantyhose, bodycon dress")
    assert "sheer" in beh2 and "cling" in beh2


def test_fabric_check_catches_plastic_prompt():
    problems = fabric.check("black dress, lowres, standing")
    assert len(problems) >= 3
    good = fabric.build("silk blouse, bodycon fit", ["cling"]) + ", plastic fabric"
    assert fabric.check(good) == []


def test_forge_prompt_contains_fabric_physics():
    import prompt_forge
    p = prompt_forge.forge("mika", heat=2)
    assert "silk" in p["prompt"]
    assert "plastic fabric" in p["negative"]


# --- негатив ----------------------------------------------------------------
def test_negative_sabotage_is_measured_and_removed():
    res = neg_audit.check("lowres, nsfw, nude, bad anatomy")
    assert res["index"] >= 20
    cleaned, removed = neg_audit.clean("lowres, nsfw, nude, bad anatomy, censored, mosaic censoring")
    assert set(t.strip() for t in removed) == {"nsfw", "nude"}
    assert "censored" in cleaned and "mosaic censoring" in cleaned


def test_anti_censor_is_never_stripped():
    _, removed = neg_audit.clean("censored, bar censor, hair over breasts, steam")
    assert removed == []


def test_our_own_negatives_are_clean():
    import prompt_forge
    for cid in ("selena", "mika", "reika", "nova", "sora", "yuna", "irene"):
        neg = prompt_forge.forge(cid, heat=2)["negative"]
        assert neg_audit.check(neg)["index"] == 0, cid


# --- Green / Mature ---------------------------------------------------------
def test_modes_have_different_ceilings():
    assert maturity.DEFAULT["ceiling"]["green"]["heat"] < maturity.DEFAULT["ceiling"]["mature"]["heat"]
    assert maturity.DEFAULT["ceiling"]["green"]["boldness"] < maturity.DEFAULT["ceiling"]["mature"]["boldness"]


def test_mature_requires_age_and_gates_boldness():
    state = maturity.load()
    assert state["age_verified"] is True, "для adult-проекта возраст должен быть подтверждён"
    r = maturity.resolve(2, 120)
    assert r["mode"] == "mature" and r["allowed"]
    over = maturity.resolve(2, 240)
    assert over["boldness"] == maturity.load()["ceiling"]["mature"]["boldness"]
    assert any("подписанный" in n for n in over["notes"])


def test_rating_labels():
    assert maturity.rating_of(1, 40) == "general"
    assert maturity.rating_of(2, 120) == "mature"
    assert maturity.rating_of(3, 200) == "restricted"


def test_green_mode_caps_forge(monkeypatch):
    import prompt_forge
    monkeypatch.setitem(maturity.load(), "mode", "green")
    monkeypatch.setattr(maturity, "load", lambda: {**maturity.DEFAULT, "mode": "green", "age_verified": True})
    p = prompt_forge.forge("selena", heat=2)
    assert p["heat"] == 1
    assert "fully clothed" in p["prompt"]


# --- артефакты --------------------------------------------------------------
def _synthetic(fringe: bool = True) -> tuple[np.ndarray, np.ndarray]:
    h, w = 200, 120
    bgr = np.zeros((h, w, 3), np.uint8)
    bgr[:, :] = (0, 255, 0)                      # зелёный фон
    alpha = np.zeros((h, w), np.uint8)
    # тело: прямоугольник с «шеей» и просветом между рукой и телом
    bgr[40:180, 30:90] = (180, 120, 90)
    alpha[40:180, 30:90] = 255
    if fringe:                                    # зелёная кайма по контуру
        bgr[38:42, 30:90] = (20, 240, 20)
        alpha[38:42, 30:90] = 255
    return bgr, alpha


def test_artifact_repair_kills_green_fringe():
    import artifact_repair as ar
    bgr, alpha = _synthetic()
    before = ar.measure(bgr, alpha)
    fixed, a2 = ar.repair(bgr, alpha)[:2]
    after = ar.measure(fixed, a2)
    assert before["fringe"] > 0
    assert after["fringe"] == 0.0
    assert after["spill"] <= 0.01


def test_big_gaps_are_not_filled_but_small_holes_are():
    """Регрессия: заливка «по внешнему контуру» превращала просвет в чёрную плиту."""
    import artifact_repair as ar
    h, w = 200, 160
    bgr = np.full((h, w, 3), (0, 255, 0), np.uint8)
    alpha = np.zeros((h, w), np.uint8)
    bgr[30:170, 20:60] = (170, 130, 100)          # торс
    alpha[30:170, 20:60] = 255
    bgr[30:170, 100:140] = (170, 130, 100)        # рука
    alpha[30:170, 100:140] = 255
    # просвет между торсом и рукой шириной 40 px остаётся прозрачным
    bgr[90:96, 30:50] = (0, 255, 0)               # маленькая «дырка» внутри торса
    alpha[90:96, 30:50] = 0

    _, a2, log = ar.repair(bgr, alpha)
    # центр просвета должен остаться прозрачным (по краям допустим сглаженный
    # переход в 1–2 px — это матирование, а не заливка)
    mid = a2[:, 72:88]
    assert mid.max() < 130, "крупный просвет залит — вернулась чёрная плита"
    assert log["holes_filled_n"] >= 1, "маленькая дырка должна закрываться"


# --- каст -------------------------------------------------------------------
def test_mature_cast_sprites_exist_and_indexed():
    manifest = json.loads((ROOT / "assets" / "sprite" / "manifest.json").read_text(encoding="utf-8"))
    for cid in ("selena", "mika", "yuna", "reika", "nova", "sora", "irene"):
        key = f"m_{cid}"
        assert key in manifest, key
        assert (ROOT / "assets" / "sprite" / f"{key}.webp").exists()


def test_no_sprite_carries_sole_camera_tag_in_cards():
    for path in (ROOT / "content" / "characters").glob("*.json"):
        card = json.loads(path.read_text(encoding="utf-8"))
        outfit = " ".join((card.get("wardrobe_default") or {}).get("prompt_tags", []))
        assert "sole toward" not in outfit.lower()
