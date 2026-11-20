"""
canon.py — реестр утверждений (единственный способ что-то «запомнить»).

Правило фабрики: любой арт, персонаж, механика и стиль существуют как элемент
канона со статусом draft → approved/rejected. Всё, что генерируется дальше,
обязано ссылаться на approved-элемент.

Защита от «тихой подмены»: у каждого элемента хранится sha256 его data.
Если данные изменились после утверждения, sync сбрасывает статус в draft и
помечает элемент как drifted. `check` валит CI, если утверждённое разошлось.

Команды:
  sync                      подтянуть canon/source/*.json в реестр
  list [--status draft]     таблица
  approve <id> [--note ...]  утвердить
  reject  <id> [--note ...]  отклонить
  check                     drift-детектор (exit 1 при расхождении)
  export                    canon/approved.json — только утверждённое
  render                     review/canon-v1.html — лист на утверждение
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
REG = ROOT / "canon" / "canon.json"
SRC = ROOT / "canon" / "source"
EXPORT = ROOT / "canon" / "approved.json"

DRAFT, APPROVED, REJECTED = "draft", "approved", "rejected"


def _rel(p: pathlib.Path) -> str:
    try:
        return str(pathlib.Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash(data) -> str:
    blob = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:32]


def load() -> dict:
    if REG.exists():
        return json.loads(REG.read_text(encoding="utf-8"))
    return {"schema": 2, "updated": _now(), "items": []}


def save(reg: dict) -> None:
    reg["updated"] = _now()
    REG.parent.mkdir(parents=True, exist_ok=True)
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def get(reg: dict, item_id: str) -> dict | None:
    return next((i for i in reg["items"] if i["id"] == item_id), None)


# ------------------------------------------------------------------ команды

def cmd_sync(args) -> int:
    reg = load()
    if not SRC.exists():
        print(f"нет каталога {SRC}")
        return 1
    seen, added, drifted = set(), 0, 0
    for path in sorted(SRC.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("items", []):
            iid = item["id"]
            seen.add(iid)
            h = _hash(item["data"])
            cur = get(reg, iid)
            if cur is None:
                reg["items"].append({
                    "id": iid, "kind": item.get("kind", "misc"),
                    "title": item.get("title", iid), "status": DRAFT,
                    "hash": h, "approved_hash": None, "data": item["data"],
                    "note": "", "updated": _now(),
                })
                added += 1
            elif cur["hash"] != h:
                was_approved = cur["status"] == APPROVED
                cur["data"], cur["hash"], cur["updated"] = item["data"], h, _now()
                # заголовок/тип тоже подтягиваем: иначе в листе остаётся «v2» поверх v3
                cur["title"] = item.get("title", cur["title"])
                cur["kind"] = item.get("kind", cur["kind"])
                if was_approved:
                    cur["status"] = DRAFT
                    cur["note"] = "изменено после утверждения — нужно переутвердить"
                    drifted += 1
            else:
                # данные те же, но заголовок мог поменяться в источнике
                cur["title"] = item.get("title", cur["title"])
                cur["kind"] = item.get("kind", cur["kind"])
    retired = 0
    kept = []
    for i in reg["items"]:
        if i["id"] in seen:
            kept.append(i)
        elif i["status"] == DRAFT:
            # черновик, чей источник удалён (например cast-v2 после переезда на cast-v3),
            # не должен висеть в реестре — выкидываем
            retired += 1
        else:
            i["note"] = (i.get("note") or "") + " [источник удалён]"
            kept.append(i)
    reg["items"] = kept
    save(reg)
    print(f"sync: добавлено {added}, сброшено в draft из-за изменений {drifted}, "
          f"убрано осиротевших черновиков {retired}")
    return 0


def cmd_list(args) -> int:
    reg = load()
    items = reg["items"]
    if args.status:
        items = [i for i in items if i["status"] == args.status]
    if not items:
        print("пусто")
        return 0
    mark = {APPROVED: "✅", DRAFT: "⏳", REJECTED: "❌"}
    print(f"{'':2} {'id':22} {'kind':10} {'статус':9} title")
    for i in items:
        print(f"{mark.get(i['status'],'?')} {i['id']:22} {i['kind']:10} {i['status']:9} {i['title']}")
        if i.get("note"):
            print(f"   ↳ {i['note']}")
    return 0


def _set_status(item_id: str, status: str, note: str) -> int:
    reg = load()
    item = get(reg, item_id)
    if item is None:
        print(f"нет такого элемента: {item_id}")
        return 1
    item["status"] = status
    item["note"] = note or ""
    item["updated"] = _now()
    if status == APPROVED:
        item["approved_hash"] = item["hash"]
        item["approved_at"] = _now()
    save(reg)
    print(f"{item_id} → {status}")
    return 0


def cmd_approve(args) -> int:
    return _set_status(args.id, APPROVED, args.note)


def cmd_reject(args) -> int:
    return _set_status(args.id, REJECTED, args.note)


def cmd_check(args) -> int:
    """CI-гейт: утверждённое не должно разойтись с данными."""
    reg = load()
    bad = []
    for i in reg["items"]:
        if i["status"] == APPROVED:
            if i.get("approved_hash") != i["hash"]:
                bad.append((i["id"], "данные изменились после утверждения"))
            elif _hash(i["data"]) != i["hash"]:
                bad.append((i["id"], "подмена данных в обход sync"))
    if bad:
        print("DRIFT:")
        for iid, why in bad:
            print(f"  ❌ {iid}: {why}")
        return 1
    n = sum(1 for i in reg["items"] if i["status"] == APPROVED)
    print(f"canon ok: {n} утверждённых элементов, расхождений нет")
    return 0


def cmd_export(args) -> int:
    reg = load()
    approved = {i["id"]: i["data"] for i in reg["items"] if i["status"] == APPROVED}
    EXPORT.write_text(json.dumps(
        {"exported": _now(), "canon": approved}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"экспортировано {len(approved)} элементов → {_rel(EXPORT)}")
    return 0


def cmd_render(args) -> int:
    from automation.review import render
    out = render()
    print(f"лист на утверждение → {_rel(out)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="canon", description="реестр утверждений")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("sync").set_defaults(fn=cmd_sync)
    p = sub.add_parser("list"); p.add_argument("--status"); p.set_defaults(fn=cmd_list)
    for name, fn in (("approve", cmd_approve), ("reject", cmd_reject)):
        p = sub.add_parser(name)
        p.add_argument("id"); p.add_argument("--note", default="")
        p.set_defaults(fn=fn)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("export").set_defaults(fn=cmd_export)
    sub.add_parser("render").set_defaults(fn=cmd_render)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
