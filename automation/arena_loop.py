"""
arena_loop.py — турнир агентов как постоянная часть фабрики.

Зачем это здесь. Владелец четыре раза подряд отклонял результат формулировкой
«не то»: «слишком модельные», «все гипертрофированы», «стиль не нравится»,
«ушло в комикс». Угадывать правку в переписке дорого. Турнир решает это иначе:
N агентов получают одну и ту же задачу с разными стратегиями, атакуют решения
друг друга, защищаются и переписывают, слепой судья судит по рубрике — остаётся
одно решение, и рядом с ним видно, какие атаки оно пережило.

Движок не наш: в `vendor/arena-skill/` лежит MIT-проект
Jakeschincariol/arena-skill (bracket.py, strategies.json, rubric.md), склонированный
целиком. Здесь только обвязка: задача и baseline собираются из нашего канона и
карточки героини, поэтому турнир нельзя запустить «на пустом месте».

    python3 -m automation.arena_loop plan --agents 16
    python3 -m automation.arena_loop init --heroine selena --heat 2 --agents 16 \\
        --reject-reason "ушло в комикс: толстый контур и плоский cel"
    python3 -m automation.arena_loop next
    python3 -m automation.arena_loop status
    python3 -m automation.arena_loop winner
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRACKET = ROOT / "vendor" / "arena-skill" / "bracket.py"
SKILL = ROOT / "vendor" / "arena-skill" / "SKILL.md"
ARENA = ROOT / ".arena"

sys.path.insert(0, str(ROOT / "tools"))


def _bracket(*args: str) -> int:
    if not BRACKET.exists():
        print("нет движка: vendor/arena-skill/bracket.py отсутствует.\n"
              "  git clone --depth 1 https://github.com/Jakeschincariol/arena-skill.git\n"
              "  cp -r arena-skill/skills/arena vendor/arena-skill", file=sys.stderr)
        return 2
    cmd = [sys.executable, str(BRACKET), *args]
    proc = subprocess.run(cmd, cwd=ROOT, text=True)
    return proc.returncode


def _write_inputs(heroine: str, heat: int, reason: str | None, model: str,
                  kind: str = "style") -> tuple[pathlib.Path, pathlib.Path]:
    """Собрать task.md и baseline.md из канона, карточки и форжа."""
    if kind == "boldness":
        import boldness
        from prompt_forge import forge

        base = forge(heroine, heat=heat, model=model)
        ARENA.mkdir(parents=True, exist_ok=True)
        task = ARENA / "task.md"
        base_f = ARENA / "baseline.md"
        task.write_text(boldness.build_task(heroine, heat=heat), encoding="utf-8")
        base_f.write_text(f"# baseline: {heroine}, L{heat}\n\nPROMPT:\n{base['prompt']}\n\n"
                          f"NEGATIVE:\n{base['negative']}\n", encoding="utf-8")
        return task, base_f

    from arena_task import build_tournament

    files = build_tournament(heroine, heat=heat, reject_reason=reason, model=model)
    ARENA.mkdir(parents=True, exist_ok=True)
    task = ARENA / "task.md"
    base = ARENA / "baseline.md"
    task.write_text(
        files["task.md"]
        + "\n\n---\n\n# Рубрика (её видит судья, не участники)\n\n"
        + files["rubric.md"]
        + "\n\n# Карточки стратегий\n\n"
        + files["cards.md"],
        encoding="utf-8",
    )
    base.write_text(files["baseline.md"], encoding="utf-8")
    return task, base


def cmd_plan(args) -> int:
    print("движок:", BRACKET.relative_to(ROOT) if BRACKET.exists() else "НЕ НАЙДЕН")
    print("инструкция движка:", SKILL.relative_to(ROOT) if SKILL.exists() else "нет")
    return _bracket("plan", "--agents", str(args.agents))


def cmd_init(args) -> int:
    task, base = _write_inputs(args.heroine, args.heat, args.reject_reason, args.model, args.kind)
    print(f"задача:   {task.relative_to(ROOT)}")
    print(f"baseline: {base.relative_to(ROOT)}")
    cmd = ["init", "--agents", str(args.agents), "--task-file", str(task),
           "--baseline-file", str(base)]
    if args.seed is not None:
        cmd += ["--seed", str(args.seed)]
    rc = _bracket(*cmd)
    if rc == 0:
        print("\nдальше: python3 -m automation.arena_loop next")
    return rc


def main() -> None:
    ap = argparse.ArgumentParser(description="турнир агентов по нашему канону")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="сколько раундов и вызовов будет")
    p.add_argument("--agents", type=int, default=16)
    p.set_defaults(fn=cmd_plan)

    p = sub.add_parser("init", help="собрать задачу и начать турнир")
    p.add_argument("--heroine", required=True)
    p.add_argument("--heat", type=int, default=2)
    p.add_argument("--agents", type=int, default=16)
    p.add_argument("--seed", type=int)
    p.add_argument("--model", default="illustrious")
    p.add_argument("--kind", choices=["style", "boldness"], default="style")
    p.add_argument("--reject-reason")
    p.set_defaults(fn=cmd_init)

    for name in ("next", "status", "winner", "pairings", "collect", "advance"):
        p = sub.add_parser(name, help=f"прокси к bracket.py {name}")
        p.set_defaults(fn=lambda a, n=name: _bracket(n))

    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
