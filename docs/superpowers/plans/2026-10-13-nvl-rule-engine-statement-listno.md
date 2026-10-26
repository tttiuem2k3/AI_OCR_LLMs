# NVL Rule Engine Statement ListNo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend NVL Rules Engine behavior for Đặt cọc/Trả trước skip rules and STATEMENT.ListNo invoice matching without changing the API input/output schema.

**Architecture:** Keep API routing and prompt format unchanged. Add focused tests around `resolve_rules_ai_bem_meiko` and `execute_nvl_rule_engine`, then update existing rule config and `NVL_INVOICE_NO_MATCH` implementation to use Mapping plus deterministic branch evaluation.

**Tech Stack:** Python 3, unittest, existing `App/Rules_BE` modules, existing `BEMT2009` seed SQL.

## Global Constraints

- Do not modify `Prompt_AI_BEM_v11/Prompt_ReadFile_1.sql`; the user already updated it.
- Do not change API request or response schema; client calls must remain compatible.
- `CompareExecutionMode = RULE_ENGINE` must not call LLM.
- Keep changes scoped to NVL Rules Engine behavior and supporting tests/seed config.
- Preserve existing user work in the dirty tree.

---

### Task 1: Add Focused Rule Engine Tests

**Files:**
- Create: `tests/test_nvl_rule_engine.py`

**Interfaces:**
- Consumes: `App.Rules_BE.rules_ai_bem_meiko.resolve_rules_ai_bem_meiko`
- Consumes: `App.Rules_BE.nvl_rule_engine.execute_nvl_rule_engine`
- Produces: failing tests that describe required skip and STATEMENT matching behavior.

- [x] **Step 1: Write tests**

Create fixtures for minimal `prompt_info`, `content_text`, and BEMT2009-like config dictionaries. Tests must cover:

`test_nvl_prepayment_skips_invoice_dependent_criteria`: call `resolve_rules_ai_bem_meiko` with `DnttType=Nguyên vật liệu`, `FormationID=Đặt cọc/trả trước`, and each criterion `Số hóa đơn`, `Ngày hóa đơn`, `Ngày hoàn thành kiểm tra`, `Hạn thanh toán`; assert status `OK` and exact skip description.

`test_nvl_statement_invoice_branch_ok`: call `execute_nvl_rule_engine` with DNTT invoice `A123`, INVOICE `A123`, STATEMENT `ListNo=ST01, VoucherNo=A123, B456`, CUSTOMSHEET `VoucherNo=ST01`; assert `OK`.

`test_nvl_statement_invoice_list_mismatch_is_ng`: same data but STATEMENT `VoucherNo=B456`; assert `NG`.

`test_nvl_statement_listno_customs_mismatch_is_ng`: same data but CUSTOMSHEET `VoucherNo=OTHER`; assert `NG`.

`test_nvl_invoice_branch_can_pass_when_commercial_branch_fails`: include both INVOICE matching DNTT and COMMERCIALINVOICE not matching DNTT; assert `OK`.

- [x] **Step 2: Run tests and verify RED**

Run: `.\AI_BEM\Scripts\python.exe -m unittest tests.test_nvl_rule_engine -v`

Expected: fail because skip description/current NVL rule and STATEMENT.ListNo behavior are not implemented yet.

---

### Task 2: Implement Skip Rules and STATEMENT Branch Matching

**Files:**
- Modify: `App/Rules_BE/rules_ai_bem_meiko.py`
- Modify: `App/Rules_BE/nvl_rule_engine.py`

**Interfaces:**
- Consumes tests from Task 1.
- Produces updated `NGUYENVATLIEU_COMPARE_RULES` and deterministic `NVL_INVOICE_NO_MATCH` branch evaluation.

- [x] **Step 1: Update NVL skip config**

In `NGUYENVATLIEU_COMPARE_RULES`, replace `DATCOC_TRATRUOC.DEFAULT` for criteria `SOHOADON`, `NGAYHOADON`, `NGAYHOANTHANHKIEMTRA`, and `HANTHANHTOAN` with `_skip("Với nguồn hình thành Đặt cọc/Trả trước, tiêu chí này được bỏ qua khi đối chiếu.")`. Keep other criteria using normal rules.

Update the skip response builder so when `skip_message` exists, Description uses it exactly, instead of composing the old generic sentence.

- [x] **Step 2: Add ListNo support**

In `FIELD_ALIASES`, add aliases for `LISTNO`: `("LISTNO", "SOBANGKE", "STATEMENTNO")`.

- [x] **Step 3: Replace invoice number branch logic**

In `_invoice_number_rule`, evaluate invoice branches explicitly:

- Parse DNTT invoice values.
- Collect documents by type.
- If STATEMENT exists, branch success requires DNTT invoices match branch document invoices, branch invoice values are included in any STATEMENT.VoucherNo list, and the same STATEMENT.ListNo matches any CUSTOMSHEET.VoucherNo.
- If STATEMENT does not exist, branch success requires DNTT invoices match branch document invoices and branch invoice values match CUSTOMSHEET.VoucherNo.
- Return OK if any branch succeeds.
- Return BLANK if no branch has enough data to evaluate.
- Return NG if at least one branch has enough data but all evaluable branches fail.

- [x] **Step 4: Run focused tests and verify GREEN**

Run: `.\AI_BEM\Scripts\python.exe -m unittest tests.test_nvl_rule_engine -v`

Expected: all focused tests pass.

---

### Task 3: Update BEMT2009 Seed and Verify Compatibility

**Files:**
- Modify: `scripts/sql/20261008_migrate_ont1043_to_bemt2009.sql`

**Interfaces:**
- Consumes updated Rule Engine behavior.
- Produces seed config that includes `STATEMENT.ListNo` for `CRITERIA_INVOICE_NO`.

- [x] **Step 1: Add seed row**

Add an active `MAPPING` row for `NVL_SO_HOA_DON_V1`, `CRITERIA_INVOICE_NO`, `EvidenceTypeCode='STATEMENT'`, `EvidenceFieldCode='ListNo'`, and a DNTT field that allows the Python algorithm to discover the field. Keep existing `STATEMENT.VoucherNo` if present; if not present, add it too.

- [x] **Step 2: Adjust expected seed count**

If seed rows increase, update the expected BEMT2009 row count checks in that SQL file consistently.

- [x] **Step 3: Run validation**

Run: `.\AI_BEM\Scripts\python.exe -m py_compile App\Rules_BE\compare_execution_mode.py App\Rules_BE\rule_engine_config_repository.py App\Rules_BE\nvl_rule_engine.py App\Rules_BE\rules_ai_bem_meiko.py App\main_iis.py`

Run: `.\AI_BEM\Scripts\python.exe -m unittest tests.test_nvl_rule_engine -v`

Expected: compile succeeds and focused tests pass.
