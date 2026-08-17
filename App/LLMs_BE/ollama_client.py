from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Optional

import requests


class OllamaChatEngine:
    is_ollama = True

    def __init__(self, settings_all, chat_config: Optional[Dict[str, Any]] = None, session=None):
        self._api_url = str(getattr(settings_all, "OLLAMA_CHAT_API_URL", "") or "").strip()
        self._model = str(getattr(settings_all, "OLLAMA_MODEL", "") or "").strip()
        self._connect_timeout = float(getattr(settings_all, "OLLAMA_CONNECT_TIMEOUT_SECONDS", 5.0))
        self._read_timeout = float(getattr(settings_all, "OLLAMA_READ_TIMEOUT_SECONDS", 600.0))
        self._chat_config = deepcopy(chat_config or {})
        self._session = session or requests.Session()

        if not self._api_url:
            raise RuntimeError("OLLAMA_CHAT_API_URL is not configured")
        if not self._model:
            raise RuntimeError("OLLAMA_MODEL is not configured")

    @property
    def active_id(self) -> str:
        return self._model

    @property
    def cfg(self) -> Dict[str, Any]:
        options = self._chat_config.get("options") or {}
        max_model_len = int(options.get("num_ctx") or 0) or 8192
        return {
            "id": self._model,
            "name": self._model,
            "engine": "ollama",
            "max_model_len": max_model_len,
            "ollama_chat": deepcopy(self._chat_config),
        }

    def load(self, model_id: str, cfg, local_path: Optional[str] = None):
        return self._model

    def unload(self):
        return None

    def _build_payload(
        self,
        messages: List[Dict[str, str]],
        max_new_tokens: int,
        temperature: float,
        think: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages is required")

        payload: Dict[str, Any] = {
            "model": self._model,
            "messages": deepcopy(messages),
        }
        for key in ("stream", "think", "format", "keep_alive"):
            if key in self._chat_config:
                payload[key] = deepcopy(self._chat_config[key])
        if think is not None:
            payload["think"] = bool(think)

        options = deepcopy(self._chat_config.get("options") or {})
        options.setdefault("num_predict", int(max_new_tokens))
        options.setdefault("temperature", float(temperature))
        payload["options"] = options
        return payload

    def generate_chat(
        self,
        messages,
        max_new_tokens: int,
        temperature: float,
        think: Optional[bool] = None,
    ) -> str:
        payload = self._build_payload(messages, max_new_tokens, temperature, think=think)
        try:
            response = self._session.post(
                self._api_url,
                json=payload,
                timeout=(self._connect_timeout, self._read_timeout),
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise RuntimeError(f"Ollama request timed out: {exc}") from exc
        except requests.RequestException as exc:
            detail = ""
            response = getattr(exc, "response", None)
            if response is not None:
                detail = str(getattr(response, "text", "") or "").strip()[:1000]
            suffix = f" - {detail}" if detail else ""
            raise RuntimeError(f"Ollama request failed: {exc}{suffix}") from exc

        try:
            data = response.json()
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Ollama returned invalid JSON") from exc

        message = data.get("message") if isinstance(data, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise RuntimeError("Ollama response is missing message.content")
        return content

    def stream_chat(
        self,
        messages,
        max_new_tokens: int,
        temperature: float,
        think: Optional[bool] = None,
    ) -> Iterable[str]:
        text = self.generate_chat(
            messages,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            think=think,
        )
        if text:
            yield text

    def count_prompt_tokens(self, messages) -> Optional[int]:
        return None

    def prompt_stats(self, messages) -> Optional[dict]:
        return None

    def runtime_info(self) -> dict:
        return {
            "provider": "ollama",
            "model": self._model,
            "api_url": self._api_url,
        }
