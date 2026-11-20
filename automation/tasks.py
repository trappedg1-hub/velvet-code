"""
tasks.py — машинночитаемая очередь задач (минимальное участие человека).

Агент берёт следующую задачу, выполняет, отмечает done. Человек нужен только
на задачах с owner=human (утверждения, деньги, юрлицо) — их агент не трогает.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATH = ROOT / "ROADMAP.json"


def load() -> dict:
    return json.loads(PATH.read_text(encoding="utf-8"))


def save(d: dict) -> None:
    d["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def blocked_by_approval(tasks, t) -> bool:
    """Задача заблокирована, пока хоть одна зависимость не done."""
    by_id = {x["id"]: x for x in tasks}
    return any(by_id.get(dep, {"status": "todo"})["status"] != "done"
               for dep in t.get("depends_on", []))


def cmd_next(args) -> int:
    d = load()
    tasks = d["tasks"]
    for t in tasks:
        if t["status"] != "todo":
            continue
        if t.get("owner") == "human" and not args.include_human:
            continue
        if blocked_by_approval(tasks, t):
            continue
        print(json.dumps(t, ensure_ascii=False, indent=2))
        return 0
    print("нет доступных задач (все done или ждут человека)")
    return 0


def cmd_list(args) -> int:
    d = load()
    icon = {"todo": "·", "doing": "▶", "done": "✅", "blocked": "⛔"}
    for t in d["tasks"]:
        own = "🧑" if t.get("owner") == "human" else "🤖"
        print(f"{icon.get(t['status'],'?')} {own} {t['id']:26} {t['status']:8} {t['title']}")
    return 0


def cmd_done(args) -> int:
    d = load()
    t = next((x for x in d["tasks"] if x["id"] == args.id), None)
    if t is None:
        print(f"нет задачи {args.id}")
        return 1
    t["status"] = "done"
    t["closed"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if args.note:
        t["result"] = args.note
    save(d)
    print(f"{args.id} → done")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tasks")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("next"); p.add_argument("--include-human", action="store_true")
    p.set_defaults(fn=cmd_next)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    p = sub.add_parser("done"); p.add_argument("id"); p.add_argument("--note", default="")
    p.set_defaults(fn=cmd_done)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
