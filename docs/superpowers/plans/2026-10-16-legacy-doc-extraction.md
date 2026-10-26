# Legacy `.doc` Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hỗ trợ trích xuất text từ `.doc` mà không thay đổi cách xử lý `.docx`.

**Architecture:** `office_text.py` định tuyến `.doc` sang một extractor mới dùng `aspose-words-foss`, trong khi `.docx` tiếp tục đi qua `python-docx`. Endpoint OCR không cần sửa vì danh sách extension được nhập từ `OFFICE_TEXT_EXTENSIONS`.

**Tech Stack:** Python 3.12, `unittest`, `python-docx==1.2.0`, `aspose-words-foss==26.7.0`.

## Global Constraints

- Không thay đổi hành vi `.docx`.
- Không yêu cầu Microsoft Word, LibreOffice hoặc Java.
- File `.doc` hỏng phải trả lỗi parse có thể ánh xạ thành HTTP 415.
- Không sửa các thay đổi không liên quan đang có trong workspace.

---

### Task 1: Define `.doc` behavior with tests

**Files:**
- Create: `tests/test_office_text_doc.py`

**Interfaces:**
- Consumes: `OFFICE_TEXT_EXTENSIONS`, `extract_office_text(path)`, `extract_doc_text(path)`.
- Produces: Regression coverage for `.doc` support and unchanged `.docx` dispatch.

- [x] Write failing tests for extension support, dispatch, pagination, parser errors, and `.docx` isolation.
- [x] Run `AI_BEM/Scripts/python.exe -m unittest tests.test_office_text_doc -v` and verify expected failures.

### Task 2: Implement `.doc` extraction

**Files:**
- Modify: `App/OCR_BE/office_text.py`
- Modify: `Setup/requirements.txt`
- Modify: `docs/requirements_server_windows_gpu.txt`

**Interfaces:**
- Produces: `extract_doc_text(src: str | Path) -> List[str]`.

- [x] Add `.doc` to `OFFICE_TEXT_EXTENSIONS`.
- [x] Implement lazy import and text extraction with `aspose.words_foss.Document`.
- [x] Route only `.doc` to `extract_doc_text()`; retain `.docx` routing unchanged.
- [x] Pin `aspose-words-foss==26.7.0` in both deployment requirement files.
- [x] Install the dependency in the project virtual environment.
- [x] Run the focused test and make it pass.

### Task 3: Verify regression safety

**Files:**
- Test: `tests/test_office_text_doc.py`
- Test: `tests/test_office_text_csv.py`

- [x] Run both Office test modules.
- [x] Compile `App/OCR_BE/office_text.py`.
- [x] Review the final diff and confirm no unrelated files changed.
