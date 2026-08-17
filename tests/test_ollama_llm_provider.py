import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase


class FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or json.dumps(payload, ensure_ascii=False)

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return self.response


class OllamaChatEngineTests(TestCase):
    def _make_engine(self, response=None):
        from App.LLMs_BE.ollama_client import OllamaChatEngine

        settings = SimpleNamespace(
            OLLAMA_CHAT_API_URL="http://169.254.1.2:11434/api/chat",
            OLLAMA_MODEL="qwen3.6:latest",
            OLLAMA_CONNECT_TIMEOUT_SECONDS=5.0,
            OLLAMA_READ_TIMEOUT_SECONDS=600.0,
        )
        config = {
            "stream": False,
            "think": False,
            "format": "json",
            "keep_alive": "30m",
            "options": {
                "temperature": 0,
                "seed": 42,
                "num_ctx": 32768,
                "num_predict": 4096,
                "top_p": 0.9,
                "repeat_penalty": 1.05,
            },
        }
        session = FakeSession(response or FakeResponse({"message": {"content": '{"sections":[]}'}}))
        return OllamaChatEngine(settings, config, session=session), session

    def test_generate_chat_posts_expected_payload_and_returns_content(self):
        engine, session = self._make_engine()
        messages = [
            {"role": "system", "content": "Chỉ trả JSON."},
            {"role": "user", "content": "Trích xuất dữ liệu."},
        ]

        result = engine.generate_chat(messages, max_new_tokens=128, temperature=0.2)

        self.assertEqual(result, '{"sections":[]}')
        self.assertEqual(len(session.calls), 1)
        call = session.calls[0]
        self.assertEqual(call["url"], "http://169.254.1.2:11434/api/chat")
        self.assertEqual(call["timeout"], (5.0, 600.0))
        self.assertEqual(
            call["json"],
            {
                "model": "qwen3.6:latest",
                "messages": messages,
                "stream": False,
                "think": False,
                "format": "json",
                "keep_alive": "30m",
                "options": {
                    "temperature": 0,
                    "seed": 42,
                    "num_ctx": 32768,
                    "num_predict": 4096,
                    "top_p": 0.9,
                    "repeat_penalty": 1.05,
                },
            },
        )

    def test_stream_chat_yields_single_non_streaming_result(self):
        engine, _ = self._make_engine(FakeResponse({"message": {"content": "answer"}}))
        self.assertEqual(
            list(engine.stream_chat([{"role": "user", "content": "hello"}], 10, 0.1)),
            ["answer"],
        )

    def test_generate_chat_overrides_think_for_single_request(self):
        engine, session = self._make_engine()

        engine.generate_chat(
            [{"role": "user", "content": "compare amounts"}],
            max_new_tokens=128,
            temperature=0.0,
            think=True,
        )

        self.assertIs(session.calls[0]["json"]["think"], True)

    def test_generate_chat_rejects_missing_message_content(self):
        engine, _ = self._make_engine(FakeResponse({"done": True}))
        with self.assertRaisesRegex(RuntimeError, "message.content"):
            engine.generate_chat([{"role": "user", "content": "hello"}], 10, 0.1)

    def test_generate_chat_reports_http_error_body(self):
        engine, _ = self._make_engine(
            FakeResponse({"error": "model not found"}, status_code=404, text="model not found")
        )
        with self.assertRaisesRegex(RuntimeError, "model not found"):
            engine.generate_chat([{"role": "user", "content": "hello"}], 10, 0.1)

    def test_load_and_unload_are_noops(self):
        engine, session = self._make_engine()
        engine.load("local-model", {"engine": "transformers"})
        engine.unload()
        self.assertEqual(session.calls, [])
        self.assertEqual(engine.active_id, "qwen3.6:latest")


class OllamaProviderFactoryTests(TestCase):
    def test_ocr_unload_setting_controls_ai_inference_switch(self):
        from App.LLMs_BE.llms_integration import should_unload_ocr_before_ai_inference

        self.assertTrue(
            should_unload_ocr_before_ai_inference(
                SimpleNamespace(LLM_UNLOAD_OCR_BEFORE_AI_INFERENCE=True)
            )
        )
        self.assertFalse(
            should_unload_ocr_before_ai_inference(
                SimpleNamespace(LLM_UNLOAD_OCR_BEFORE_AI_INFERENCE=False)
            )
        )

    def test_factory_uses_ollama_without_constructing_local_engine(self):
        from App.LLMs_BE import llms_integration

        with TemporaryDirectory() as tmp:
            yaml_path = Path(tmp) / "models.yaml"
            yaml_path.write_text(
                "ollama:\n  chat:\n    stream: false\n    options:\n      num_ctx: 32768\nmodels: []\n",
                encoding="utf-8",
            )
            settings = SimpleNamespace(
                LLM_USE_OLLAMA=True,
                OLLAMA_CHAT_API_URL="http://169.254.1.2:11434/api/chat",
                OLLAMA_MODEL="qwen3.6:latest",
                OLLAMA_CONNECT_TIMEOUT_SECONDS=5.0,
                OLLAMA_READ_TIMEOUT_SECONDS=600.0,
                LLM_HF_HOME="Models",
                LLM_HF_TOKEN=None,
                LLM_MODELS_YAML_PATH=str(yaml_path),
                LLM_LOCAL_MODELS_DIR="Models",
            )
            original_manager = llms_integration.LLMEngineManager

            def fail_local_manager():
                raise AssertionError("Local LLM engine must not be constructed")

            llms_integration.LLMEngineManager = fail_local_manager
            try:
                engine, registry = llms_integration.get_llms_engine_and_registry(settings, tmp)
            finally:
                llms_integration.LLMEngineManager = original_manager

            self.assertTrue(engine.is_ollama)
            self.assertEqual(engine.active_id, "qwen3.6:latest")
            self.assertEqual(registry.get_ollama_chat_config()["options"]["num_ctx"], 32768)
            self.assertEqual(llms_integration.load_special_model(engine, registry, settings), "qwen3.6:latest")
