# Compare Execution Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cho phép API-AI/Hangfire chỉ định từng tiêu chí đối chiếu chạy bằng Rule Engine hoặc LLM, trong khi giữ nguyên System Prompt, User Prompt và schema kết quả hiện tại.

**Architecture:** Request `/llms/api/ai_llms_models` nhận thêm metadata tùy chọn `CompareExecutionMode` với ba giá trị `AUTO`, `RULE_ENGINE`, `LLM`. AI Python chuẩn hóa mode ở một service nhỏ rồi điều hướng nhánh đối chiếu. API-AI đọc cấu hình active của `BEMT2009` để tạo job vào queue Rule hoặc LLM; `REVIEW` từ Rule Engine được enqueue sang LLM thay vì lưu kết quả cuối.

**Tech Stack:** Python, Flask, unittest/pytest, SQL Server, .NET/Hangfire integration documentation.

## Global Constraints

- Giữ nguyên endpoint `/llms/api/ai_llms_models` và alias `/api/ai_llms_models`.
- Giữ nguyên `messages`, System Prompt, User Prompt và schema `criteria` hiện tại.
- Không dùng tên request `CompareMode` vì `BEMT2009.CompareMode` đã mang nghĩa thuật toán Rule Engine.
- Request không có `CompareExecutionMode` phải chạy như hiện tại (`AUTO`).
- `RULE_ENGINE` không được gọi LLM; `LLM` không được chạy Rule Engine mới từ `BEMT2009`.
- Không sửa source API-AI trong kế hoạch này; chỉ tạo tài liệu bàn giao chính xác cho người phụ trách.

---

### Task 1: Compare Execution Mode Service

**Files:**
- Create: `App/Rules_BE/compare_execution_mode.py`
- Test: `tests/test_compare_execution_mode.py`

**Interfaces:**
- Produces: `normalize_compare_execution_mode(value: object) -> str`
- Produces: `should_run_rule_engine(mode: str) -> bool`
- Produces: `should_run_llm(mode: str) -> bool`

- [ ] Write failing tests for default, aliases and invalid mode.
- [ ] Run focused tests and confirm failure because the service does not exist.
- [ ] Implement the minimal normalization/routing service.
- [ ] Run focused tests and confirm pass.

### Task 2: Integrate Routing Into Comparison Processing

**Files:**
- Modify: `App/Rules_BE/rules_ai_bem_meiko.py`
- Modify: `App/main_iis.py`
- Test: `tests/test_nvl_rule_engine.py`

**Interfaces:**
- Consumes: `CompareExecutionMode` from the top-level HTTP request.
- Produces: existing `(payload, status_code)` response contract.

- [ ] Write failing tests proving `LLM` skips the Rule Engine and `RULE_ENGINE` never calls LLM.
- [ ] Pass normalized mode from Flask endpoint into the comparison processor.
- [ ] Route `AUTO`, `RULE_ENGINE` and `LLM` without changing extraction behavior.
- [ ] Return `REVIEW` from `RULE_ENGINE` when no active/valid Rule configuration exists.
- [ ] Run focused routing and Rule Engine tests.

### Task 3: API-AI/Hangfire Handoff

**Files:**
- Create: `docs/API_AI_Hangfire_Routing_RuleEngine_LLM.md`

**Interfaces:**
- Documents: DB query used to classify criteria before enqueue.
- Documents: request examples for `RULE_ENGINE` and `LLM`.
- Documents: queue, retry, fallback and final-result persistence rules.

- [ ] Document the current API-AI call chain and exact modification points.
- [ ] Document routing from active `BEMT2009` Mapping/Rule rows.
- [ ] Document that `REVIEW` is an intermediate response and must not be stored as final `BEMT2004` data.
- [ ] Document backward compatibility and rollout order.

### Task 4: Verification

**Files:**
- Verify: all modified Python files and focused tests.

- [ ] Run syntax compilation.
- [ ] Run compare-mode tests.
- [ ] Run NVL Rule Engine regression tests.
- [ ] Review git diff and confirm no unrelated files changed.
