# Low-Resolution OCR Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upscale only low-resolution portrait document pages before PPStructureV3 text detection without changing the existing OCR configuration for normal inputs.

**Architecture:** Add a small image normalization helper to the existing orientation module because that stage already exposes PDF and image pages as NumPy arrays. Invoke the helper after orientation verification and before passing the prepared pages to PPStructureV3.

**Tech Stack:** Python, NumPy, OpenCV, unittest.

## Global Constraints

- Keep the existing PPStructureV3 detection configuration unchanged.
- Do not add a custom PDF renderer.
- Skip landscape crops and sufficiently large pages.
- Cap enlarged pages at 1600 pixels on the longest side.

---

### Task 1: Add conditional page normalization

**Files:**
- Modify: `App/OCR_BE/orientation.py`
- Modify: `App/OCR_BE/ocr_engine_iis.py`
- Test: `tests/test_ocr_orientation.py`

**Interfaces:**
- Produces: `normalize_low_resolution_pages(images, ...) -> list[np.ndarray]`
- Consumes: oriented page images returned by `prepare_oriented_inputs`

- [x] Write failing tests for low-resolution portrait, landscape crop, and sufficiently large portrait inputs.
- [x] Run the focused test and confirm the helper is missing.
- [x] Implement the minimal normalization helper with cubic interpolation and bounded scaling.
- [x] Call the helper after orientation verification and before PPStructureV3 prediction.
- [x] Run focused orientation tests and inspect the final diff.
