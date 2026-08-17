# Processed Prompt Client Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ghi `Outputs/llms/prompt_client_1.txt` sau khi system prompt nhánh Trích xuất đã lọc DOC, trước khi OCR được chia chunk.

**Architecture:** Rules layer gọi callback snapshot đúng một lần với system prompt đã lọc và user prompt OCR nguyên khối. Endpoint cung cấp callback ghi log theo cùng cấu trúc của `prompt_client.txt`, nhưng dùng file `prompt_client_1.txt` và metadata lọc DOC.

**Tech Stack:** Python, unittest, Flask endpoint helpers.

---

### Task 1: Verify snapshot timing

**Files:**
- Modify: `tests/test_rules_ai_bem_meiko_extract_prompt_filter.py`
- Modify: `App/Rules_AI_BEM_MEIKO.py`

- [ ] Add an integration test that captures `append_prompt_client_snapshot_fn`.
- [ ] Assert the callback runs once before `split_ocr_text_fn`.
- [ ] Assert the system content has only selected DOC bodies and no DOC tags.
- [ ] Assert the user content still contains the complete unsplit OCR input.

### Task 2: Write the second log file

**Files:**
- Modify: `App/main_iis.py`

- [ ] Generalize the existing snapshot writer to accept a target filename.
- [ ] Add a callback that writes normalized snapshots to `prompt_client_1.txt`.
- [ ] Pass the callback into `process_ai_llms_models_rules`.
- [ ] Run focused extraction prompt-filter tests and Python compilation.

