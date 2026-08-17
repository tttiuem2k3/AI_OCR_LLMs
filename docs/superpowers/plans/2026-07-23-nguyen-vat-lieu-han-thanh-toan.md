# Nguyen Vat Lieu Payment Deadline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tính DueDate bằng Python cho nhánh Đối chiếu + Nguyên vật liệu + Hạn thanh toán mà không gọi LLM.

**Architecture:** Thêm một parser thuần Python trong `App/Rules_AI_BEM_MEIKO.py` để đọc các block chứng từ cố định, chọn PaymentTerm đa số và tạo object `DueDate/FileName/Description`. Tích hợp nhánh trả sớm trong `process_ai_llms_models_rules`, sau đó tái sử dụng `_build_payment_deadline_result` để đối chiếu Deadline và chuẩn hóa ngày nghỉ.

**Tech Stack:** Python 3, standard library `re`, `datetime`, `collections.Counter`, `unittest`.

---

### Task 1: Parse and calculate payment deadlines

**Files:**
- Create: `tests/test_rules_ai_bem_meiko_payment_deadline.py`
- Modify: `App/Rules_AI_BEM_MEIKO.py`

- [ ] **Step 1: Write failing helper tests**

Add tests importing `_build_nguyenvatlieu_payment_deadline_source` and assert:

```python
def test_ams90_preserves_anchor_order_and_removes_duplicates(self):
    result = _build_nguyenvatlieu_payment_deadline_source(self.ams_prompt)
    self.assertEqual(
        result,
        {
            "DueDate": "08/06/2026, 10/06/2026, 16/06/2026, 02/06/2026, 28/05/2026, 03/06/2026",
            "FileName": "",
            "Description": "",
        },
    )
```

Add focused cases for AMS variants, AFTER B/L, invalid terms, tied majority with ten filenames, missing anchors and two-digit years.

- [ ] **Step 2: Run helper tests and verify RED**

Run: `python -m unittest tests.test_rules_ai_bem_meiko_payment_deadline -v`

Expected: import failure because `_build_nguyenvatlieu_payment_deadline_source` does not exist.

- [ ] **Step 3: Implement the parser and calculator**

Add helpers near the existing payment deadline functions:

```python
def _parse_fixed_compare_document_blocks(content_text: str) -> list[dict[str, str]]: ...
def _parse_payment_term_key(value: object) -> tuple[str, int] | None: ...
def _parse_payment_anchor_date(value: object) -> datetime | None: ...
def _build_nguyenvatlieu_payment_deadline_source(content_text: str) -> dict: ...
```

The implementation must preserve source order, deduplicate anchors and DueDates, ignore invalid PO terms, cap tied filenames at ten, and never call LLM.

- [ ] **Step 4: Run helper tests and verify GREEN**

Run: `python -m unittest tests.test_rules_ai_bem_meiko_payment_deadline -v`

Expected: all helper tests pass.

### Task 2: Integrate the deterministic branch

**Files:**
- Modify: `tests/test_rules_ai_bem_meiko_payment_deadline.py`
- Modify: `App/Rules_AI_BEM_MEIKO.py`

- [ ] **Step 1: Write a failing integration test**

Call `process_ai_llms_models_rules` with the fixed prompt and a `generate_with_trim_fn` stub that raises if called. Assert status 200, `CriteriaStatus == "NG"`, the expected `DueDateAI`, and zero LLM calls.

- [ ] **Step 2: Run integration test and verify RED**

Run: `python -m unittest tests.test_rules_ai_bem_meiko_payment_deadline.PaymentDeadlineIntegrationTests -v`

Expected: failure because the existing flow calls `generate_with_trim_fn`.

- [ ] **Step 3: Add the early compare branch**

Insert a branch after prompt normalization:

```python
if is_compare_mode and dntt_prompt_key == "NGUYENVATLIEU" and criterion_key == "HANTHANHTOAN":
    payment_source = _build_nguyenvatlieu_payment_deadline_source(content_user_process)
    result = _build_payment_deadline_result(
        prompt_info=prompt_info,
        parsed_llm=payment_source,
        raw_llm_text="",
        criterion_name=criterion_name,
        data_holidays_dir=str(data_holidays_dir or ""),
    )
    append_response_log_fn(_build_payment_deadline_log_payload(result, payment_source))
    light_cuda_cleanup_fn()
    return result, 200
```

- [ ] **Step 4: Run integration and full feature tests**

Run: `python -m unittest tests.test_rules_ai_bem_meiko_payment_deadline -v`

Expected: all tests pass and the LLM stub is not called for the scoped branch.

### Task 3: Verify syntax and scope

**Files:**
- Verify: `App/Rules_AI_BEM_MEIKO.py`
- Verify: `tests/test_rules_ai_bem_meiko_payment_deadline.py`

- [ ] **Step 1: Compile changed Python files**

Run: `python -m py_compile App/Rules_AI_BEM_MEIKO.py tests/test_rules_ai_bem_meiko_payment_deadline.py`

Expected: exit code 0 with no output.

- [ ] **Step 2: Run the feature suite fresh**

Run: `python -m unittest tests.test_rules_ai_bem_meiko_payment_deadline -v`

Expected: all tests pass with zero failures and zero errors.

- [ ] **Step 3: Inspect the focused diff**

Run: `git diff -- App/Rules_AI_BEM_MEIKO.py tests/test_rules_ai_bem_meiko_payment_deadline.py docs/superpowers/specs/2026-07-23-nguyen-vat-lieu-han-thanh-toan-design.md docs/superpowers/plans/2026-07-23-nguyen-vat-lieu-han-thanh-toan.md`

Expected: only the scoped deterministic payment-deadline changes, tests and documentation.
