import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from automation import canon


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(canon, "REG", tmp_path / "canon.json")
    monkeypatch.setattr(canon, "SRC", tmp_path / "source")
    monkeypatch.setattr(canon, "EXPORT", tmp_path / "approved.json")
    (tmp_path / "source").mkdir()
    return tmp_path


def write_item(sb, iid="style-x", value=1):
    payload = {"items": [{"id": iid, "kind": "style", "title": "T", "data": {"v": value}}]}
    (sb / "source" / f"{iid}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_sync_creates_draft(sandbox):
    write_item(sandbox)
    assert canon.main(["sync"]) == 0
    reg = canon.load()
    assert reg["items"][0]["status"] == "draft"


def test_approve_then_check_ok(sandbox):
    write_item(sandbox)
    canon.main(["sync"])
    assert canon.main(["approve", "style-x", "--note", "ок"]) == 0
    assert canon.load()["items"][0]["status"] == "approved"
    assert canon.main(["check"]) == 0


def test_change_after_approval_resets_to_draft(sandbox):
    write_item(sandbox, value=1)
    canon.main(["sync"]); canon.main(["approve", "style-x"])
    write_item(sandbox, value=2)          # канон изменился
    canon.main(["sync"])
    item = canon.load()["items"][0]
    assert item["status"] == "draft"
    assert "переутвердить" in item["note"]


def test_tamper_detected_by_check(sandbox):
    write_item(sandbox)
    canon.main(["sync"]); canon.main(["approve", "style-x"])
    reg = canon.load()
    reg["items"][0]["data"]["v"] = 999      # правим реестр в обход sync
    canon.save(reg)
    assert canon.main(["check"]) == 1


def test_export_contains_only_approved(sandbox):
    write_item(sandbox, "a", 1); write_item(sandbox, "b", 2)
    canon.main(["sync"]); canon.main(["approve", "a"])
    canon.main(["export"])
    exported = json.loads((sandbox / "approved.json").read_text())
    assert set(exported["canon"]) == {"a"}


def test_reject_status(sandbox):
    write_item(sandbox)
    canon.main(["sync"])
    canon.main(["reject", "style-x", "--note", "не то"])
    assert canon.load()["items"][0]["status"] == "rejected"


def test_sync_refreshes_title_when_data_changed(sandbox):
    """Иначе в листе утверждения остаётся заголовок «v2» поверх v3."""
    write_item(sandbox, value=1)
    canon.main(["sync"])
    payload = {"items": [{"id": "style-x", "kind": "style", "title": "T v3", "data": {"v": 2}}]}
    (sandbox / "source" / "style-x.json").write_text(json.dumps(payload), encoding="utf-8")
    canon.main(["sync"])
    assert canon.load()["items"][0]["title"] == "T v3"


def test_sync_prunes_orphaned_draft_but_keeps_approved(sandbox):
    write_item(sandbox, iid="gone", value=1)
    canon.main(["sync"])
    (sandbox / "source" / "gone.json").unlink()
    canon.main(["sync"])                       # draft без источника -> удаляется
    assert [i["id"] for i in canon.load()["items"]] == []

    write_item(sandbox, iid="kept", value=1)
    canon.main(["sync"]); canon.main(["approve", "kept"])
    (sandbox / "source" / "kept.json").unlink()
    canon.main(["sync"])                       # утверждённый остаётся с пометкой
    reg = canon.load()
    assert [i["id"] for i in reg["items"]] == ["kept"]
    assert "источник удалён" in reg["items"][0]["note"]
