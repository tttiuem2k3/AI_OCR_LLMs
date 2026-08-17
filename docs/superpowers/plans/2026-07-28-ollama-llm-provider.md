# Ollama LLM Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuyển toàn bộ luồng LLM giữa Ollama và Transformers bằng một công tắc mà không tải SPECIAL_MODEL_ID khi Ollama bật.

**Architecture:** Thêm `OllamaChatEngine` tương thích engine hiện tại và chọn provider trong factory. `main_iis.py` dùng model/config theo provider và giữ OCR độc lập.

**Tech Stack:** Python 3, requests, PyYAML, Pydantic Settings, pytest.

---

### Task 1: Client và test Ollama

**Files:**
- Create: `tests/test_ollama_llm_provider.py`
- Create: `App/LLMs_BE/ollama_client.py`

- [ ] Viết test mock HTTP xác nhận payload và `message.content`.
- [ ] Chạy test để xác nhận fail trước implementation.
- [ ] Cài đặt `generate_chat`, `stream_chat`, no-op `load/unload` và lỗi HTTP/schema.
- [ ] Chạy lại test để xác nhận pass.

### Task 2: Cấu hình và factory

**Files:**
- Modify: `App/settings_all.py`
- Modify: `App/LLMs_BE/models.yaml`
- Modify: `App/LLMs_BE/registry.py`
- Modify: `App/LLMs_BE/llms_integration.py`

- [ ] Test factory Ollama không dựng `LLMEngineManager`.
- [ ] Thêm settings kết nối và cấu hình `ollama.chat` trong YAML.
- [ ] Expose cấu hình Ollama từ registry.
- [ ] Chọn provider trong factory và bảo vệ `load_special_model`.

### Task 3: Route provider-aware

**Files:**
- Modify: `App/main_iis.py`

- [ ] Vô hiệu hóa autoload local khi Ollama bật.
- [ ] Bỏ validate/load registry local trong chat, generate và `ai_llms_models` khi dùng Ollama.
- [ ] Giữ load/unload endpoint dưới dạng no-op tương thích khi dùng Ollama.
- [ ] Giữ nguyên nhánh Transformers khi tắt Ollama.

### Task 4: Xác minh

- [ ] Chạy test Ollama và test Rules hiện có.
- [ ] Chạy `py_compile` cho các file đã sửa.
- [ ] Rà diff để xác nhận OCR chỉ đổi điều kiện autoload LLM.
