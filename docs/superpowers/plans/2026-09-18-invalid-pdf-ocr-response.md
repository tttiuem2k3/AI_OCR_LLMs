# Invalid PDF OCR Response Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return the normal TXT OCR response for invalid PDF data while preserving existing behavior for all other OCR errors.

**Architecture:** A small OCR helper recognizes the specific PDFium data-format failure and supplies one Vietnamese error-text page. The `/ocr` endpoint uses that page in the existing TXT save/response path and batch formatting path.

**Tech Stack:** Python 3.11, Flask, PaddleOCR/PDFium, unittest.

## Global Constraints

- Preserve `text/plain; charset=utf-8` and existing attachment headers.
- Recover only `PdfiumError` messages containing `Data format error`.
- Use the exact message `File bị lỗi, không đọc được nội dung OCR.`.

---

### Task 1: Recover invalid PDF data errors

**Files:**
- Create: `App/OCR_BE/pdf_errors.py`
- Modify: `App/main_iis.py`
- Test: `tests/test_pdf_errors.py`

**Interfaces:**
- Produces: `pdf_data_format_error_pages(error: BaseException) -> list[str] | None`.

- [ ] **Step 1: Write the failing test**

```python
assert pdf_data_format_error_pages(PdfiumError("Data format error")) == [
    "File bị lỗi, không đọc được nội dung OCR."
]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_pdf_errors -v`

Expected: FAIL because `App.OCR_BE.pdf_errors` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
def pdf_data_format_error_pages(error: BaseException) -> list[str] | None:
    if error.__class__.__name__ == "PdfiumError" and "Data format error" in str(error):
        return ["File bị lỗi, không đọc được nội dung OCR."]
    return None
```

- [ ] **Step 4: Use the helper in `/ocr`**

```python
error_pages = pdf_data_format_error_pages(error) if ext in PDF_EXTS else None
if error_pages is None:
    raise
pages = error_pages
```

- [ ] **Step 5: Run tests to verify success**

Run: `python -m unittest tests.test_pdf_errors -v`

Expected: PASS.
