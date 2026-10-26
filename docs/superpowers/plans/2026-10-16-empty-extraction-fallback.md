# Empty Extraction Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task.

**Goal:** Return schema-valid fallback sections instead of `{"sections": []}` when LLM extraction produces no usable sections.

**Architecture:** Keep one shared extraction schema mapping for merge and fallback generation. Resolve expected document types from the filename prefix, build one fallback section per resolved type, and use `OTHER` for unknown prefixes while preserving the existing empty-result error log.

**Tech Stack:** Python, `unittest`, Flask response contract.

## Global Constraints

- Do not modify the prompt SQL; the user already updated it.
- Preserve HTTP `200` and the existing `{"text": "..."}` endpoint wrapper.
- Discard partial LLM data when all sections are filtered.
- Combined filename prefixes must return both fallback sections.

---

### Task 1: Share extraction schemas

**Files:**
- Modify: `App/Rules_BE/rules_ai_bem_meiko.py`
- Test: `tests/test_rules_ai_bem_meiko_section_schema.py`

- [x] Make `STATEMENT` use `ListNo` as its key and include `ListNo` in fields.
- [x] Include `Currency` in `BILL` fields.
- [x] Move the schema mapping to a shared module-level constant.

### Task 2: Build fallback sections

**Files:**
- Modify: `App/Rules_BE/rules_ai_bem_meiko.py`
- Test: `tests/test_rules_ai_bem_meiko_extract_fallback.py`

- [x] Add failing tests for `INSPECTION`, combined `INVOICE`/`PACKINGLIST`, and unknown-prefix `OTHER` fallbacks.
- [x] Implement fallback master/detail construction from the shared schema.
- [x] Verify key, review-message, null, numeric-zero, and ordering behavior.

### Task 3: Integrate empty-result fallback

**Files:**
- Modify: `App/Rules_BE/rules_ai_bem_meiko.py`
- Test: `tests/test_rules_ai_bem_meiko_extract_prompt_filter.py`

- [x] Replace only the final empty extraction response with fallback sections.
- [x] Keep `ALL_SECTIONS_FILTERED_AFTER_MERGE` / `NO_PARSEABLE_SECTIONS` logging based on the original empty result.
- [x] Run focused extraction tests, schema tests, and Python compilation.
