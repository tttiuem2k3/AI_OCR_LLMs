# Client API Guide

Tài liệu này mô tả các API hiện có trên server (OCR + LLMs) và cách gọi từ client.

> Base URL mặc định: `http://127.0.0.1:4444`
>
> Server chạy bằng Flask (WSGI) và có thể được serve qua `uvicorn` (ASGI wrapper).

---

## 0) Quick health checks

### `GET /ping`
Kiểm tra server OCR đã sẵn sàng hay chưa.

**Response (text/plain)**
- `OK (ready)` hoặc `OK (not-ready)`

**Ví dụ (curl)**
```bash
curl -s http://127.0.0.1:4444/ping
```

### `GET /llms/api/health`
Kiểm tra subsystem LLMs.

**Response (JSON)**
```json
{
  "status": "ok" | "not-ready",
  "active_model_id": "..." | null,
  "active_model_name": "..." | null,
  "hf_home": "Models",
  "ts": 1730000000.0
}
```

**Ví dụ (curl)**
```bash
curl -s http://127.0.0.1:4444/llms/api/health
```

---

## 1) OCR API

### `POST /ocr`
Thực hiện OCR cho **1 file** hoặc **nhiều file**.

- Hỗ trợ: PDF, ảnh (`.png .jpg .jpeg .tif .tiff .bmp .webp`), Office (`.docx .xlsx .xls .pptx`)
- Upload dạng `multipart/form-data`

**Request**
- Single file: field `file`
- Multi file: field `files` (có thể gửi nhiều file cùng key)

**Response**
- Trả về `text/plain; charset=utf-8` dạng file `.txt` (stream) với header `Content-Disposition: attachment; ...`

**Ví dụ (curl - 1 file)**
```bash
curl -X POST http://127.0.0.1:4444/ocr \
  -F "file=@Data_test/Anh-Nhat.jpg" \
  -o result.txt
```

**Ví dụ (curl - nhiều file)**
```bash
curl -X POST http://127.0.0.1:4444/ocr \
  -F "files=@Data_test/Anh-Nhat.jpg" \
  -F "files=@Data_test/Nhat.jpg" \
  -o batch.txt
```

**Lỗi thường gặp**
- `400`: không có file hoặc file không đúng định dạng.
- `415`: Office file không parse được.
- `500`: engine OCR chưa init hoặc lỗi runtime.

---

## 2) Output/Annotation API

### `GET /annot-list?stem=<name>`
Lấy danh sách URL ảnh annotate (nếu `SAVE_ANNOTATIONS=true`).

**Query params**
- `stem`: tên stem (ví dụ: tên file sau sanitize)

**Response (JSON)**
```json
[
  "http://127.0.0.1:4444/Outputs/annot_images/<stem>/annot_p01_overall_ocr_res.png",
  "..."
]
```

**Ví dụ**
```bash
curl -s "http://127.0.0.1:4444/annot-list?stem=Anh-Nhat"
```

### `GET /Outputs/<path:filename>`
Serve các file output (txt/annot_images/...).

**Ví dụ**
```bash
curl -O "http://127.0.0.1:4444/Outputs/txt/Anh-Nhat.txt"
curl -O "http://127.0.0.1:4444/Outputs/annot_images/Anh-Nhat/annot_p01_overall_ocr_res.png"
```

---

## 3) LLMs API (prefix `/llms`)

### 3.1) Authentication (Token)
Các endpoint LLMs yêu cầu token.

Server dùng:
- `LLM_API_TOKEN`
- key query param: `LLM_API_TOKEN_QUERY_KEY` (mặc định `Token`)

**Cách gửi token**
1) Query param:
- `?Token=<your_token>`

2) Header:
- `Authorization: Bearer <your_token>`

3) Header:
- `X-API-Token: <your_token>`

> Lưu ý: một số UI/client có thể URL-encode token với dấu ngoặc kép (`%22token%22`). Server đã normalize trường hợp này.

---

### 3.2) Connect & list models

#### `GET /llms/api/connect`  (alias: `GET /llms/connect`)
Trả về trạng thái + danh sách model trong registry.

**Ví dụ (query param token)**
```bash
curl -s "http://127.0.0.1:4444/llms/api/connect?Token=YOUR_TOKEN"
```

#### `GET /llms/api/models`
List models.

```bash
curl -s "http://127.0.0.1:4444/llms/api/models?Token=YOUR_TOKEN"
```

#### `POST /llms/api/models/reload`
Reload registry từ `App/LLMs_BE/models.yaml`.

```bash
curl -X POST "http://127.0.0.1:4444/llms/api/models/reload?Token=YOUR_TOKEN"
```

---

### 3.3) Load / Unload model

#### `POST /llms/api/models/load`
Load một model theo `model_id`.

**Body (JSON)**
```json
{ "model_id": "qwen2_5_0_5b_instruct" }
```

**Ví dụ**
```bash
curl -X POST "http://127.0.0.1:4444/llms/api/models/load?Token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_id":"qwen2_5_0_5b_instruct"}'
```

#### `POST /llms/api/models/unload`
Unload model hiện tại.

```bash
curl -X POST "http://127.0.0.1:4444/llms/api/models/unload?Token=YOUR_TOKEN"
```

---

### 3.4) Generate (non-stream)

#### `POST /llms/api/generate`
Sinh text theo prompt.

**Body (JSON)**
```json
{
  "model_id": "qwen2_5_0_5b_instruct",
  "sys_prompt": "... optional ...",
  "user_prompt": "... required ...",
  "max_new_tokens": 256,
  "temperature": 0.7
}
```

**Ví dụ**
```bash
curl -X POST "http://127.0.0.1:4444/llms/api/generate?Token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_id":"qwen2_5_0_5b_instruct","user_prompt":"Hello"}'
```

---

### 3.5) Chat streaming (SSE)

#### `POST /llms/api/chat/stream`
Chat streaming theo chuẩn Server-Sent Events (SSE).

**Body (JSON)**
```json
{
  "model_id": "qwen2_5_0_5b_instruct",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "max_new_tokens": 256,
  "temperature": 0.7
}
```

**Response**
- `Content-Type: text/event-stream`
- Event payload mỗi dòng: `data: { ...json... }`
  - `{type: "meta"}` / `{type: "delta"}` / `{type: "done"}` / `{type: "error"}`

**Ví dụ (curl)**
```bash
curl -N -X POST "http://127.0.0.1:4444/llms/api/chat/stream?Token=YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model_id":"qwen2_5_0_5b_instruct","messages":[{"role":"user","content":"Hello"}]}'
```

---

### 3.6) Special model endpoint

#### `POST /llms/api/ai_llms_models`
Gọi model đặc biệt `SPECIAL_MODEL_ID` (config trong `App/settings_all.py`).

**Body (JSON)**
```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "max_new_tokens": 256,
  "temperature": 0.7
}
```

---

### 3.7) Token status

#### `GET /llms/api/token/status`
Kiểm tra token đang bật hay không.

```bash
curl -s http://127.0.0.1:4444/llms/api/token/status
```

---

## 4) Compatibility routes (root-level)

Để tương thích UI cũ, server có expose thêm các route ở root:

- `GET /connect` (→ `/llms/api/connect`)
- `GET /api/connect`
- `GET /api/health`
- `GET /api/models`
- `POST /api/models/reload`
- `POST /api/models/load`
- `POST /api/models/unload`
- `POST /api/chat/stream`
- `POST /api/generate`
- `GET /api/token/status`
- `POST /api/ai_llms_models`

Các route này có cùng authentication logic như phần `/llms/api/*`.

---

## 5) UI routes (tham khảo)

- `GET /` → Landing page (UI/index_all.html hoặc UI/index_root.html)
- `GET /ocr/` → OCR UI
- `GET /llms/` → LLMs UI

Static:
- `GET /static/<file>` → `UI/static/<file>`
- `GET /llms/static/<file>` → `UI/static/<file>`
