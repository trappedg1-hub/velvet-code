"""Тесты базы тегов и генератора задач для агента."""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import arena_task  # noqa: E402
import tag_db  # noqa: E402


def test_tag_db_loads_real_data():
    for cat in tag_db.CATS:
        rows = tag_db.load(cat)
        assert rows, f"{cat} пуст"
        assert rows[0][1] >= rows[-1][1], "не отсортировано по частоте"


def test_tag_db_search_is_case_and_underscore_insensitive():
    res = tag_db.search("THIGH", cat="attire", limit=5)
    assert res and all("thigh" in t for t, _, _ in res)
    assert [c for _, c, _ in res] == sorted([c for _, c, _ in res], reverse=True)


def test_tag_db_search_spans_categories():
    cats = {c for _, _, c in tag_db.search("breast", limit=40)}
    assert len(cats) >= 2


def test_export_wildcards_writes_files(tmp_path, monkeypatch):
    monkeypatch.setattr(tag_db, "WILD", tmp_path)
    counts = tag_db.export_wildcards()
    assert counts and all(n > 0 for n in counts.values())
    for name in counts:
        assert (tmp_path / name).read_text(encoding="utf-8").strip()


def test_arena_task_is_self_contained():
    md = arena_task.build("reika", kind="render", heat=2, n=3)
    # задача обязана нести всё нужное внутри себя
    assert "## Цель" in md and "## Критерии приёмки" in md and "## Запрещено" in md
    assert "[ ]" in md                      # проверяемые чек-боксы
    assert "prompt_forge.py" in md          # путь к инструменту
    assert "score_7" in md or "masterpiece" in md   # готовый промпт целиком
    assert "plump" in md                    # запрет из канона продублирован агенту


def test_arena_task_kinds_differ():
    texts = {k: arena_task.build("mika", kind=k) for k in arena_task.TASKS}
    assert len(set(texts.values())) == len(texts)
    assert "LoRA" in texts["style"]
