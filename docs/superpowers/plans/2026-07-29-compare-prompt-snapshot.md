# Compare Prompt Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Log the exact system and user messages for the reconciliation branch to `prompt_client_1.txt` immediately before LLM generation.

**Architecture:** Reuse the existing `append_prompt_client_snapshot_fn` callback already wired from `main_iis.py`. Invoke it once after reconciliation document filtering and message construction, immediately before `generate_with_trim_fn`, with reconciliation metadata for traceability.

**Tech Stack:** Python, unittest/pytest, existing prompt snapshot logging callback.

---

### Task 1: Reconciliation prompt snapshot

**Files:**
- Modify: `App/Rules_AI_BEM_MEIKO.py:3239`
- Modify: `tests/test_rules_ai_bem_meiko_amount_prompt.py:17`

- [ ] **Step 1: Write the failing test**

Extend the amount reconciliation integration test with a snapshot callback. Assert the callback runs once before generation, receives the same messages passed to `generate_with_trim_fn`, and includes `prompt_mode=DOICHIEU` plus the resolved reconciliation metadata.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rules_ai_bem_meiko_amount_prompt.py -q`

Expected: FAIL because the reconciliation branch does not call `append_prompt_client_snapshot_fn`.

- [ ] **Step 3: Write minimal implementation**

After creating `case2_messages`, call `append_prompt_client_snapshot_fn(case2_messages, extra)` in a guarded `try/except`, then call `generate_with_trim_fn` unchanged.

- [ ] **Step 4: Run relevant tests**

Run: `python -m pytest tests/test_rules_ai_bem_meiko_amount_prompt.py tests/test_rules_ai_bem_meiko_delivery_term.py tests/test_rules_ai_bem_meiko_payment_deadline.py tests/test_rules_ai_bem_meiko_extract_prompt_filter.py -q`

Expected: all tests pass.
