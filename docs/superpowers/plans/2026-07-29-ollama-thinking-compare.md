# Ollama Thinking for Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Ollama thinking for every reconciliation request that reaches the LLM while keeping extraction and Transformers behavior unchanged.

**Architecture:** The Rules layer marks reconciliation generation with a per-request `think=True` flag. `main_iis.py` forwards the flag only to Ollama engines, and `OllamaChatEngine` overrides the configured payload value without mutating shared configuration.

**Tech Stack:** Python, Flask integration callback, Ollama `/api/chat`, unittest/pytest.

---

### Task 1: Per-request Ollama thinking override

**Files:**
- Modify: `App/LLMs_BE/ollama_client.py`
- Modify: `App/main_iis.py`
- Modify: `App/Rules_AI_BEM_MEIKO.py`
- Test: `tests/test_ollama_llm_provider.py`
- Test: `tests/test_rules_ai_bem_meiko_amount_prompt.py`

- [x] Add a failing payload test for `think=True` overriding the default `think: false` configuration.
- [x] Add a failing reconciliation test using a non-amount criterion.
- [x] Add optional `think` arguments to Ollama payload and chat methods.
- [x] Forward `think` only when the active engine is Ollama.
- [x] Pass `think=True` for every reconciliation LLM call.
- [x] Run the Ollama provider and Rules regression tests.
