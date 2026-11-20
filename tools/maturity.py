"""
maturity.py — Green / Mature как в SeaArt, только у нас.

У SeaArt это устроено на уровне аккаунта: возрастной гейт, переключатель
Green / Mature, модерация выходов. Смысл режима не в «цензуре», а в том, что
один и тот же продукт должен уметь показывать и промо-кадр, и взрослый кадр —
но не смешивать их в одной ленте.

У нас два режима:

  green  — витрина. Кадр читается как персонаж: костюм, поза, свет.
           Потолок: heat ≤ 1, смелость ≤ 74 (ступень B1). Без подписи 18+.
  mature — игра. Взрослый контент, только после подтверждения возраста.
           Потолок: heat ≤ 2, смелость ≤ 164 (B2+, по разрешению владельца).

Режим — это не украшение интерфейса, а гейт в пайплайне: форж спрашивает
`cap()`, отчёт спрашивает `rating_of()`, а `resolve()` говорит, что делать
с конкретным кадром.

    python3 tools/maturity.py --status
    python3 tools/maturity.py --verify-age
    python3 tools/maturity.py --mode mature
    python3 tools/maturity.py --mode green
    python3 tools/maturity.py --resolve 2 141
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / "canon" / "source" / "maturity.json"

DEFAULT = {
    "mode": "green",
    "age_verified": False,
    "verified_at": None,
    "ceiling": {"green": {"heat": 1, "boldness": 74}, "mature": {"heat": 3, "boldness": 200}},
    "history": [],
}


def load() -> dict:
    if STATE.exists():
        try:
            data = json.loads(STATE.read_text(encoding="utf-8"))
            return {**DEFAULT, **data}
        except json.JSONDecodeError:
            pass
    return dict(DEFAULT)


def save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def set_mode(mode: str) -> dict:
    if mode not in ("green", "mature"):
        raise ValueError("режим: green или mature")
    state = load()
    if mode == "mature" and not state["age_verified"]:
        raise PermissionError("mature без подтверждённого возраста: сначала --verify-age")
    state["mode"] = mode
    state["history"] = (state.get("history") or [])[-19:] + [
        {"at": dt.datetime.now().isoformat(timespec="seconds"), "event": f"mode={mode}"}]
    save(state)
    return state


def verify_age() -> dict:
    state = load()
    state["age_verified"] = True
    state["verified_at"] = dt.datetime.now().isoformat(timespec="seconds")
    state["history"] = (state.get("history") or [])[-19:] + [
        {"at": state["verified_at"], "event": "age_verified"}]
    save(state)
    return state


def cap() -> dict:
    """Потолки текущего режима."""
    state = load()
    return state["ceiling"][state["mode"]]


def resolve(heat: int, boldness: int) -> dict:
    """Пускаем кадр или режем — и что именно режем."""
    state = load()
    mode = state["mode"]
    limit = state["ceiling"][mode]
    notes = []
    eff_heat, eff_bold = heat, boldness
    allowed = True

    if heat > limit["heat"]:
        eff_heat = limit["heat"]
        notes.append(f"heat {heat} → {eff_heat} (потолок режима {mode})")
    if boldness > limit["boldness"]:
        eff_bold = limit["boldness"]
        notes.append(f"смелость {boldness} → {eff_bold} (потолок режима {mode})")
        if mode == "mature" and boldness > 164:
            notes.append("выше B2+ — только отдельный подписанный кадр, а не поток")
        else:
            allowed = False
            notes.append("в green такой кадр не публикуется")
    if mode == "green" and heat > 1:
        allowed = False
    return {"mode": mode, "allowed": allowed, "heat": eff_heat, "boldness": eff_bold,
            "age_gate": "пройден" if state["age_verified"] else "нет", "notes": notes}


def rating_of(heat: int, boldness: int) -> str:
    """Ярлык для ассета: general / mature / restricted."""
    if boldness <= 74 and heat <= 1:
        return "general"
    if boldness <= 164 and heat <= 2:
        return "mature"
    return "restricted"


def prompt_suffix() -> str:
    """Что форж добавляет к промпту в текущем режиме."""
    return "fully clothed, tasteful" if load()["mode"] == "green" else ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--mode", choices=["green", "mature"])
    ap.add_argument("--verify-age", action="store_true")
    ap.add_argument("--resolve", nargs=2, type=int, metavar=("HEAT", "BOLDNESS"))
    a = ap.parse_args()

    if a.verify_age:
        s = verify_age()
        print(f"возраст подтверждён: {s['verified_at']}")
        return
    if a.mode:
        try:
            s = set_mode(a.mode)
        except PermissionError as e:
            print(e)
            return
        print(f"режим: {s['mode']} · потолок heat {cap()['heat']} / смелость {cap()['boldness']}")
        return
    if a.resolve:
        r = resolve(*a.resolve)
        print(f"режим {r['mode']} · возраст: {r['age_gate']} · "
              f"{'ПУСК' if r['allowed'] else 'ОТКАЗ'} · heat {r['heat']} · смелость {r['boldness']}")
        for n in r["notes"]:
            print("  -", n)
        return
    s = load()
    print(f"режим: {s['mode']} · возраст подтверждён: {'да' if s['age_verified'] else 'нет'}")
    print(f"потолки: green heat {s['ceiling']['green']['heat']}/смелость {s['ceiling']['green']['boldness']} · "
          f"mature heat {s['ceiling']['mature']['heat']}/смелость {s['ceiling']['mature']['boldness']}")


if __name__ == "__main__":
    main()
