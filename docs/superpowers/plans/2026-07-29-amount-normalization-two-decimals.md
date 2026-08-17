# Amount Normalization with Two Decimals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-enable reconciliation amount normalization while preserving `.00` when an input amount contains an all-zero fractional part.

**Architecture:** Keep the existing field-aware amount normalizer and change only the all-zero fractional branch. Re-enable its reconciliation call before LLM generation; integer inputs without a decimal separator remain unchanged.

**Tech Stack:** Python, unittest/pytest, existing Rules-layer prompt processing.

---

### Task 1: Two-decimal zero normalization

**Files:**
- Modify: `App/Rules_AI_BEM_MEIKO.py`
- Modify: `tests/test_rules_ai_bem_meiko_amount_prompt.py`

- [ ] Update tests to expect `50105440.00000000` to become `50105440.00`.
- [ ] Add assertions that `1234` remains `1234` and `1234.0000000` becomes `1234.00`.
- [ ] Run the focused tests and confirm failure.
- [ ] Change the all-zero fractional normalization result to `.00`.
- [ ] Re-enable `_normalize_compare_amount_fields()` before reconciliation LLM generation.
- [ ] Run the Rules and Ollama regression tests.
