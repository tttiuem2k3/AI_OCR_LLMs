# Conditional Unwarping Padding Implementation Plan

> **For agentic workers:** Implement locally; sub-agents are not authorized for this task.

**Goal:** Protect edge content from UVDoc cropping while preserving one full OCR pass per file.

**Architecture:** Reuse the already prepared page images. Upscale low-resolution pages as today, then perform a cheap border-band pixel check and add white padding only for small pages or pages containing dark pixels near an edge. Pass the resulting images to the existing single `PPStructureV3.predict` call.

**Tech Stack:** Python, NumPy, unittest, PaddleOCR PPStructureV3.

## Global Constraints

- Do not add another OCR pass.
- Do not add another ML model or full-page contour analysis.
- Preserve existing orientation and low-resolution behavior.
- Keep `use_doc_unwarping=True` supported.

### Task 1: Conditional safety padding

**Files:**
- Modify: `App/OCR_BE/orientation.py`
- Modify: `App/OCR_BE/ocr_engine_iis.py`
- Test: `tests/test_ocr_orientation.py`

- [ ] Add failing tests for small pages, edge-content pages, and ordinary large pages.
- [ ] Implement NumPy-only conditional white padding.
- [ ] Apply it after low-resolution normalization and before the single full OCR prediction.
- [ ] Run focused unit tests and syntax validation.
