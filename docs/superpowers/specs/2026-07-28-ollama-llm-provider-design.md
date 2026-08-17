# Ollama LLM Provider Design

## Mục tiêu

Thêm công tắc toàn cục để mọi luồng sinh nội dung LLM dùng Ollama qua `POST /api/chat`, đồng thời giữ nguyên Transformers/SPECIAL_MODEL_ID khi tắt Ollama.

## Kiến trúc

- `SettingsAll` quản lý công tắc provider, URL, tên model và timeout Ollama.
- `models.yaml` quản lý tham số chat/runtime của Ollama.
- `OllamaChatEngine` triển khai cùng giao diện `load`, `unload`, `generate_chat`, `stream_chat` mà `main_iis.py` đang dùng.
- Factory trả Ollama engine khi bật cấu hình và không khởi tạo Transformers engine.
- `main_iis.py` bỏ qua validate/autoload/load `SPECIAL_MODEL_ID` khi Ollama bật.

## Tương thích và lỗi

- `generate_chat(...)` trả trực tiếp `response.message.content` dạng `str`.
- `stream_chat(...)` gọi API non-streaming rồi yield một chunk để giữ SSE hiện tại.
- `load/unload` Ollama là no-op, không tác động OCR.
- Khi Ollama bật, `LLM_AUTOLOAD_SPECIAL` không trì hoãn khởi tạo OCR.
- Client báo lỗi rõ cho timeout, kết nối, HTTP, JSON và response thiếu `message.content`.

## Kiểm thử

- Payload và kết quả Ollama.
- Lỗi HTTP/schema.
- Factory không dựng local engine khi Ollama bật.
- Không load model local/SPECIAL_MODEL_ID khi Ollama bật.

