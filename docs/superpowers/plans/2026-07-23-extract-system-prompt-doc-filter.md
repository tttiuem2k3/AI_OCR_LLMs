# Extract System Prompt DOC Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lọc system prompt theo prefix filename trước khi chia chunk và gọi LLM trong nhánh Trích xuất.

**Architecture:** Thêm bảng mapping prefix và các helper thuần Python trong `App/Rules_AI_BEM_MEIKO.py`. Nhánh Trích xuất chuẩn bị một `selected_system_prompt` trước `split_ocr_text_fn`, sau đó dùng prompt này cho mọi chunk và log liên quan.

**Tech Stack:** Python 3, standard library `re`, `pathlib`, `unittest`.

---

### Task 1: Filename mapping and DOC filtering

**Files:**
- Create: `tests/test_rules_ai_bem_meiko_extract_prompt_filter.py`
- Modify: `App/Rules_AI_BEM_MEIKO.py`

- [ ] Viết test thất bại cho mapping prefix đơn/kết hợp và case-insensitive.
- [ ] Chạy test, xác nhận lỗi import helper chưa tồn tại.
- [ ] Thêm `EXTRACT_FILENAME_DOC_TYPE_RULES` và `_resolve_extract_doc_types_by_filename`.
- [ ] Viết test thất bại cho block inline/multiline, duplicate type, common text và lỗi cấu trúc.
- [ ] Thêm `_filter_extract_system_prompt_by_doc_types` cùng metadata.
- [ ] Chạy test helper đến khi xanh.

### Task 2: Extract-flow integration

**Files:**
- Modify: `tests/test_rules_ai_bem_meiko_extract_prompt_filter.py`
- Modify: `App/Rules_AI_BEM_MEIKO.py`

- [ ] Viết integration test với hai chunk, capture system prompt gửi LLM.
- [ ] Xác nhận test đỏ vì code hiện gửi `latest_system` nguyên bản.
- [ ] Chuẩn bị filtered prompt sau `_extract_ocr_filename_and_text` và trước split.
- [ ] Dùng filtered prompt cho LLM, prompt logs và empty-section log.
- [ ] Thêm metadata lọc vào prompt-process log.
- [ ] Chạy integration test và toàn bộ feature tests.

### Task 3: Verification

**Files:**
- Verify: `App/Rules_AI_BEM_MEIKO.py`
- Verify: `tests/test_rules_ai_bem_meiko_extract_prompt_filter.py`

- [ ] Chạy `python -m py_compile App/Rules_AI_BEM_MEIKO.py tests/test_rules_ai_bem_meiko_extract_prompt_filter.py`.
- [ ] Chạy `python -m unittest tests.test_rules_ai_bem_meiko_extract_prompt_filter tests.test_rules_ai_bem_meiko_payment_deadline -v`.
- [ ] Chạy payload mẫu `IV_105.pdf` và xác nhận mọi chunk chỉ nhận DOC:INVOICE.
- [ ] Rà soát diff tập trung, không thay đổi nhánh Đối chiếu.
