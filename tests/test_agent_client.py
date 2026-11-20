import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pytest
from automation.agent_client import AgentClient, AgentError, extract_json, PRESETS


def test_mock_chat_returns_json():
    c = AgentClient(provider="mock")
    out = c.chat([{"role": "user", "content": "проверка"}])
    assert out["content"]
    assert extract_json(out["content"])["provider"] == "mock"


def test_probe_mock_is_ok():
    assert AgentClient(provider="mock").probe()["ok"] is True


def test_unknown_provider_rejected():
    with pytest.raises(ValueError):
        AgentClient(provider="nope")


def test_presets_are_serial_for_bridge():
    assert PRESETS["arena-bridge"]["serial"] is True
    assert PRESETS["arena-bridge"]["base_url"].startswith("http://127.0.0.1")


def test_extract_json_from_fence_and_prose():
    assert extract_json('вот:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('мусор {"b": [1,2]} хвост') == {"b": [1, 2]}


def test_extract_json_raises_on_garbage():
    with pytest.raises(AgentError) as e:
        extract_json("совсем не json")
    assert e.value.code == "bad_json"


def test_needs_human_codes_stop_retries():
    # captcha не должна ретраиться автоматикой
    err = AgentError("captcha_required", "solve it")
    assert err.needs_human is True
    assert AgentError("page_timeout", "").retryable is True


def test_chat_json_roundtrip():
    c = AgentClient(provider="mock")
    out = c.chat_json("ты тестовый", "верни ok")
    assert out["ok"] is True
