# OCR Table Markdown Formatter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render detected OCR table regions as Markdown tables in TXT output while preserving existing pretty text behavior elsewhere.

**Architecture:** Extend `App/OCR_BE/text_format.py` with small helpers that identify table regions, split page tokens into table/non-table blocks, infer rows and columns from geometry, and render table blocks as Markdown. Keep the existing pretty layout renderer as fallback and for non-table text.

**Tech Stack:** Python, unittest/pytest-compatible tests, existing PPStructureV3 result dictionaries.

## Global Constraints

- Do not change OCR model settings or API response shape.
- Keep output unchanged when no table regions exist.
- Prefer Markdown tables over ASCII borders.
- Fall back to existing text rendering if a table candidate is weak.
- Keep changes focused in `App/OCR_BE/text_format.py` and tests.

---

### Task 1: Add Markdown Table Formatting Tests

**Files:**
- Modify: `tests/test_ocr_cleaning_experiment.py`
- Modify: `App/OCR_BE/text_format.py`

**Interfaces:**
- Consumes: `to_pretty_txt_pages(page_results: List[Any]) -> List[str]`
- Produces: table-aware behavior through the same public function.

- [ ] **Step 1: Write failing tests**

Add tests that build fake page dictionaries with `overall_ocr_res.rec_texts`, `overall_ocr_res.rec_polys`, and `layout_det_res.boxes` containing a `table` region. Assert that `to_pretty_txt_pages()` emits a Markdown table, preserves outside text order, and leaves pages without table regions unchanged.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_ocr_cleaning_experiment.py -q`
Expected: table test fails because output is still spacing-based text, not Markdown.

- [ ] **Step 3: Implement minimal formatter helpers**

In `App/OCR_BE/text_format.py`, add helpers to extract page tokens, collect table tokens, cluster rows, infer columns, render Markdown, and mix table/non-table blocks in reading order.

- [ ] **Step 4: Run targeted tests**

Run: `pytest tests/test_ocr_cleaning_experiment.py -q`
Expected: PASS.

- [ ] **Step 5: Run orientation tests**

Run: `pytest tests/test_ocr_orientation.py -q`
Expected: PASS, confirming unrelated orientation helpers remain unchanged.
