"""
agent_client.py — единый клиент к «мозгу» фабрики.

Поддерживает три режима:
  arena-bridge : ArenaAgentBridge (локальный OpenAI-совместимый сервер поверх
                 залогиненной вкладки arena.ai/agent). Основной dev-ускоритель.
  openai       : любой OpenAI-совместимый провайдер (для рантайма игры).
  mock         : офлайн-заглушка, без сети. Для тестов и CI.

Зачем отдельный слой: у ArenaAgentBridge своя семантика (single-flight очередь,
таймаут 300 с, типизированные ошибки captcha/login/dom_changed). Клиент
нормализует это в один интерфейс и превращает ошибки страницы в типизированные
исключения, чтобы вышележащий код мог уйти в «нужен человек».
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

# ---------------------------------------------------------------- провайдеры

PRESETS = {
    "arena-bridge": {
        "base_url": "http://127.0.0.1:8000/v1",
        "model": "arena-agent",
        "serial": True,          # single-flight: не пускать параллельные вызовы
        "timeout": 300,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "serial": False,
        "timeout": 180,
    },
    "mock": {"base_url": "", "model": "mock", "serial": True, "timeout": 5},
}

# Ошибки, которые мост отдаёт как {"error": {"code": ...}} и которые означают
# «человек должен вмешаться» — автоматика обязана остановиться, а не ретраить.
NEEDS_HUMAN = {"captcha_required", "login_required", "dom_changed", "browser_offline"}
TRANSIENT = {"page_timeout", "queue_full", "rate_limited"}


class AgentError(RuntimeError):
    def __init__(self, code: str, message: str = "", retryable: bool | None = None):
        self.code = code
        # transient-ошибки ретраятся по умолчанию, «нужен человек» — никогда
        self.retryable = (code in TRANSIENT) if retryable is None else retryable
        self.needs_human = code in NEEDS_HUMAN
        super().__init__(f"[{code}] {message}".strip())


@dataclass
class AgentClient:
    provider: str = "mock"
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout: int | None = None
    max_retries: int = 3
    calls: list = field(default_factory=list)

    def __post_init__(self):
        if self.provider not in PRESETS:
            raise ValueError(f"unknown provider {self.provider!r}; use {list(PRESETS)}")
        p = PRESETS[self.provider]
        self.base_url = self.base_url or p["base_url"]
        self.model = self.model or p["model"]
        self.timeout = self.timeout or p["timeout"]

    # ------------------------------------------------------------ транспорт
    def _http(self, path: str, payload: dict | None = None, method="POST") -> dict:
        url = self.base_url.rstrip("/") + path
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        # мост по умолчанию работает без ключа; AAB_REQUIRE_API_KEY=1 включает
        key = self.api_key or os.environ.get("AAB_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            code = "http_error"
            try:
                err = json.loads(body).get("error") or {}
                code = err.get("code") or err.get("type") or code
                msg = err.get("message", "")
            except Exception:
                msg = body[:300]
            raise AgentError(code, msg) from None
        except urllib.error.URLError as e:
            raise AgentError("browser_offline", f"{self.base_url}: {e.reason}") from None

    # ------------------------------------------------------------ mock
    def _mock(self, messages: list) -> dict:
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return {
            "id": "mock-1",
            "model": "mock",
            "choices": [{
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": json.dumps(
                    {"ok": True, "provider": "mock", "echo": str(last)[:120]},
                    ensure_ascii=False)},
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }

    # ------------------------------------------------------------ API
    def chat(self, messages: list, tools: list | None = None,
             temperature: float = 0.8) -> dict:
        """Возвращает нормализованный ответ: {content, tool_calls, raw}."""
        if self.provider == "mock":
            raw = self._mock(messages)
            self.calls.append({"mock": True})
        else:
            payload = {"model": self.model, "messages": messages,
                       "temperature": temperature, "stream": False}
            if tools:
                payload["tools"] = tools
            raw = self._with_retries(payload)
            self.calls.append({"tokens": raw.get("usage", {})})

        msg = (raw.get("choices") or [{}])[0].get("message", {})
        return {
            "content": msg.get("content") or "",
            "tool_calls": msg.get("tool_calls") or [],
            "raw": raw,
        }

    def _with_retries(self, payload: dict) -> dict:
        delay = 2.0
        last = None
        for attempt in range(self.max_retries):
            try:
                return self._http("/chat/completions", payload)
            except AgentError as e:
                last = e
                if e.needs_human or not e.retryable:
                    raise
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(delay)
                delay *= 2
        raise last  # pragma: no cover

    # ------------------------------------------------------------ helpers
    def chat_json(self, system: str, user: str, schema_hint: str = "") -> dict:
        """Просит строгий JSON и вытаскивает его даже из ```-блока."""
        messages = [
            {"role": "system", "content": system + (
                "\n\nОтвечай ТОЛЬКО валидным JSON без пояснений." if schema_hint else "")},
            {"role": "user", "content": user},
        ]
        out = self.chat(messages, temperature=0.7)["content"]
        return extract_json(out)

    def probe(self) -> dict:
        """Диагностика моста: живой ли, залогинен ли, есть ли капча."""
        info = {"provider": self.provider, "base_url": self.base_url,
                "models": None, "status": None, "ok": False, "advice": ""}
        if self.provider == "mock":
            info.update(ok=True, advice="mock: сеть не используется")
            return info
        try:
            info["models"] = self._http("/models", method="GET")
        except AgentError as e:
            info["advice"] = {
                "browser_offline": "Мост не запущен или расширение не подключено. "
                                   "Запусти сервер и открой arena.ai/agent в браузере.",
                "login_required": "Вкладка не залогинена в arena.ai — войди вручную.",
                "captcha_required": "Капча. Нужен человек: открой вкладку и реши её.",
                "http_error": "Проверь AAB_API_KEY / AAB_REQUIRE_API_KEY.",
            }.get(e.code, str(e))
            info["error"] = e.code
            return info
        # /bridge/status отдаёт состояние вкладки (без утечки текста промптов)
        for path in ("/bridge/status", "/../healthz"):
            try:
                info["status"] = self._http(path, method="GET")
                break
            except AgentError:
                continue
        info["ok"] = True
        return info


FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> dict:
    """Достаёт первый JSON-объект из ответа модели (терпит ```-обёртки и преамбулы)."""
    if not text:
        raise AgentError("empty_answer", "модель вернула пустой ответ")
    candidates = [m.group(1) for m in FENCE.finditer(text)] + [text]
    for c in candidates:
        c = c.strip()
        for opener, closer in (("{", "}"), ("[", "]")):
            i, j = c.find(opener), c.rfind(closer)
            if i != -1 and j > i:
                try:
                    return json.loads(c[i:j + 1])
                except json.JSONDecodeError:
                    continue
    raise AgentError("bad_json", text[:200])


def from_env() -> AgentClient:
    """AC_PROVIDER=arena-bridge|openai|mock, AC_BASE_URL, AC_MODEL, AC_API_KEY."""
    return AgentClient(
        provider=os.environ.get("AC_PROVIDER", "mock"),
        base_url=os.environ.get("AC_BASE_URL") or None,
        model=os.environ.get("AC_MODEL") or None,
        api_key=os.environ.get("AC_API_KEY") or None,
    )


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Диагностика подключения к мозгу")
    ap.add_argument("--provider", default=os.environ.get("AC_PROVIDER", "arena-bridge"))
    ap.add_argument("--base-url", default=None)
    a = ap.parse_args()
    c = AgentClient(provider=a.provider, base_url=a.base_url)
    print(json.dumps(c.probe(), indent=2, ensure_ascii=False))
