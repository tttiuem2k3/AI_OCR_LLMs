# NVL Signature and Stamp Rule Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route the NVL `Chu ky con dau` criterion through `nvl_rule_engine.py` with `LLMPolicy=NEVER` while preserving the current client contract and exact legacy result behavior.

**Architecture:** Add a seventh NVL compare mode and criterion mapping to the existing `App/Rules_BE` structure. Copy the current NVL signature parsing, primary-case evaluation, fallback evaluation, Vietnamese messages, and status precedence into `nvl_rule_engine.py`; keep `rules_ai_bem_meiko.py` as orchestration and retain its legacy signature path only for non-NVL DNTT types. Add canonical and idempotent SQL configuration for `BEMT2009`.

**Tech Stack:** Python 3, `unittest`, SQL Server T-SQL, existing Flask rules layer.

## Global Constraints

- Client request format must not change.
- Client response schema and existing NVL signature result text must not change.
- A request without `CompareExecutionMode` must continue to use `AUTO` and discover the Rules Engine configuration internally.
- The new stable codes are `CHUKICONDAU`, `CRITERIA_SIGNATURE_STAMP`, and `NVL_SIGNATURE_STAMP_VALIDATION`.
- The new rule must use `LLMPolicy=NEVER`.
- Only NVL signature handling moves; signature handling for `DICHVU`, `XAYDUNG`, `MAYMOC`, and `KHAC` remains unchanged.
- Do not commit changes unless the user explicitly asks for a commit.
- Preserve unrelated working-tree changes and untracked files.

## File Structure

- Modify `App/Rules_BE/nvl_rule_engine.py`: own the NVL signature algorithm and dispatch the new compare mode.
- Modify `App/Rules_BE/rule_engine_config_repository.py`: map `CHUKICONDAU` to `CRITERIA_SIGNATURE_STAMP`.
- Modify `App/Rules_BE/rules_ai_bem_meiko.py`: remove only NVL from the legacy shared signature interception branch.
- Modify `tests/test_nvl_rule_engine.py`: cover algorithm parity and AUTO orchestration without an explicit mode.
- Modify `tests/test_rule_engine_config_repository.py`: cover the stable criterion-code lookup.
- Modify `tests/test_rule_engine_message_contract.py`: lock the output contract for the new rule.
- Modify `scripts/sql/20261008_migrate_ont1043_to_bemt2009.sql`: extend the canonical seed from 35 to 39 rows.
- Create `scripts/sql/20261014_add_nvl_signature_rule.sql`: idempotently add/update the four deployed configuration rows.
- Create `tests/test_nvl_signature_rule_sql.py`: assert the canonical seed and migration contain the required active configuration.

---

### Task 1: Lock Legacy Signature Behavior With Failing Rules Engine Tests

**Files:**
- Modify: `tests/test_nvl_rule_engine.py`

**Interfaces:**
- Consumes: legacy `_build_signature_compare_result(content_text, criterion_name)` and `_build_signature_fallback_result(content_text, criterion_name)` from `rules_ai_bem_meiko.py`.
- Produces: `nvl_signature_config()` fixture and parity tests that call `execute_nvl_rule_engine` with `criterion_key="CHUKICONDAU"`.

- [ ] **Step 1: Add the signature config fixture**

Add a fixture beside `nvl_invoice_no_config()`:

```python
def nvl_signature_config():
    return {
        "rule": {
            "CompareMode": "NVL_SIGNATURE_STAMP_VALIDATION",
            "LLMPolicy": "NEVER",
            "CompareParams": (
                "requiredAll=PO;requiredAny=INVOICE,COMMERCIALINVOICE;"
                "selectedBlank=NG;fallbackBlank=BLANK;missing=BLANK"
            ),
        },
        "mappings": [
            {
                "DnttFieldCode": "BEMT2001.APK",
                "EvidenceTypeCode": "PO",
                "EvidenceFieldCode": "Signature",
                "MatchPolicy": "ALL",
                "Priority": 1,
            },
            {
                "DnttFieldCode": "BEMT2001.APK",
                "EvidenceTypeCode": "INVOICE",
                "EvidenceFieldCode": "Signature",
                "MatchPolicy": "ANY",
                "Priority": 1,
            },
            {
                "DnttFieldCode": "BEMT2001.APK",
                "EvidenceTypeCode": "COMMERCIALINVOICE",
                "EvidenceFieldCode": "Signature",
                "MatchPolicy": "ANY",
                "Priority": 1,
            },
        ],
    }
```

- [ ] **Step 2: Add a helper that compares new output with the legacy result**

```python
def run_signature_rule(content_text):
    return execute_nvl_rule_engine(
        prompt_info={},
        content_text=content_text,
        criterion_name="Chữ ký con dấu",
        criterion_key="CHUKICONDAU",
        config=nvl_signature_config(),
        payment_deadline_fn=lambda *_: None,
        delivery_term_fn=lambda *_: None,
    )


def legacy_signature_result(content_text):
    return (
        rules._build_signature_compare_result(content_text, "Chữ ký con dấu")
        or rules._build_signature_fallback_result(content_text, "Chữ ký con dấu")
    )
```

- [ ] **Step 3: Add table-driven parity cases**

Cover at least these contents and assert full dictionary equality with `legacy_signature_result`:

```python
cases = {
    "all_valid": """
        { Loại chứng từ: PO | Chữ ký và con dấu: VALID | Tên file: po.pdf }
        { Loại chứng từ: INVOICE | Chữ ký và con dấu: VALID | Tên file: invoice.pdf }
    """,
    "selected_invalid": """
        { Loại chứng từ: PO | Chữ ký và con dấu: VALID | Tên file: po.pdf }
        { Loại chứng từ: COMMERCIALINVOICE | Chữ ký và con dấu: INVALID | Tên file: ci.pdf }
    """,
    "selected_blank": """
        { Loại chứng từ: PO | Chữ ký và con dấu: VALID | Tên file: po.pdf }
        { Loại chứng từ: INVOICE | Chữ ký và con dấu: BLANK | Tên file: invoice.pdf }
    """,
    "fallback_valid_without_po": """
        { Loại chứng từ: INVOICE | Chữ ký và con dấu: VALID | Tên file: invoice.pdf }
    """,
    "fallback_blank_without_po": """
        { Loại chứng từ: INVOICE | Chữ ký và con dấu: BLANK | Tên file: invoice.pdf }
    """,
    "no_signature_data": "2. Dữ liệu đầu vào: không có thông tin chữ ký",
}
```

- [ ] **Step 4: Run the focused tests and verify RED**

Run:

```powershell
python -m unittest tests.test_nvl_rule_engine.NvlRuleEngineTests.test_signature_rule_matches_legacy_behavior -v
```

Expected: FAIL because `CHUKICONDAU` and `NVL_SIGNATURE_STAMP_VALIDATION` are not yet supported.

---

### Task 2: Implement the Signature Algorithm Inside `nvl_rule_engine.py`

**Files:**
- Modify: `App/Rules_BE/nvl_rule_engine.py`
- Test: `tests/test_nvl_rule_engine.py`

**Interfaces:**
- Consumes: `execute_nvl_rule_engine(prompt_info, content_text, criterion_name, criterion_key, config, payment_deadline_fn, delivery_term_fn)` with `criterion_key="CHUKICONDAU"` and `config=nvl_signature_config()`.
- Produces: `_signature_rule(content_text: str, criterion_name: str, config: dict) -> dict` and exact legacy-compatible responses.

- [ ] **Step 1: Register the new criterion and compare mode**

Extend the existing constants:

```python
SUPPORTED_CRITERIA = {
    "SOHOADON",
    "NGAYHOADON",
    "LOAITIEN",
    "HANTHANHTOAN",
    "DIEUKIENGIAOHANG",
    "NGAYHOANTHANHKIEMTRA",
    "CHUKICONDAU",
}

SUPPORTED_COMPARE_MODES = {
    "NVL_INVOICE_NO_MATCH",
    "NVL_INVOICE_DATE_BY_NO",
    "NVL_CURRENCY_ALL_MATCH",
    "NVL_PAYMENT_DEADLINE",
    "NVL_DELIVERY_TERM_COMPATIBILITY",
    "NVL_CLEARANCE_STATUS_ALL_YES",
    "NVL_SIGNATURE_STAMP_VALIDATION",
}
```

- [ ] **Step 2: Copy the existing signature parsers into the engine**

Add engine-local helpers by copying these source functions statement-for-statement:

```text
rules_ai_bem_meiko.py:_extract_signature_entries
    -> nvl_rule_engine.py:_extract_signature_entries
rules_ai_bem_meiko.py:_extract_file_names
    -> nvl_rule_engine.py:_extract_file_names
rules_ai_bem_meiko.py:_join_file_names
    -> nvl_rule_engine.py:_join_file_names
rules_ai_bem_meiko.py:_join_vi_list
    -> nvl_rule_engine.py:_join_vi_list
rules_ai_bem_meiko.py:_classify_signature_value
    -> nvl_rule_engine.py:_classify_signature_value
```

Allowed edits are limited to indentation and adding concrete return annotations such as `list[dict[str, str]]`. Keep the three parsing regexes, normalization, value precedence, and joining rules unchanged. Reuse `_normalize_doc_type` and `_doc_type_label` only when their output is byte-for-byte equivalent to the legacy Vietnamese labels; otherwise add `_signature_doc_type_vi_name` by copying the complete mapping from `_doc_type_vi_name`.

- [ ] **Step 3: Copy the primary-case evaluator exactly**

Copy and rename the complete function:

```text
rules_ai_bem_meiko.py:_build_signature_result_from_case
    -> nvl_rule_engine.py:_signature_result_from_case
```

Change only the function name. Preserve selected-type ordering, `INVALID` before `BLANK` precedence, filenames, statuses, and every Vietnamese message.

Use the existing NVL cases without simplification:

```python
cases = [
    {
        "required_all": ["PO"],
        "required_any_groups": [["INVOICE", "COMMERCIALINVOICE"]],
    },
    {
        "required_all": ["PO", "COMMERCIALINVOICE"],
        "required_any_groups": [],
    },
]
```

Preserve the legacy primary-path rule where selected `BLANK` entries return the same `NG` payload and wording as today.

- [ ] **Step 4: Copy the fallback evaluator exactly**

Copy and rename the complete function:

```text
rules_ai_bem_meiko.py:_build_signature_fallback_result
    -> nvl_rule_engine.py:_signature_fallback_result
```

Change only the function name and return annotation. Preserve both no-data branches, status precedence, filename selection, and final description assembly.

Preserve the fallback precedence:

```python
if invalid_types:
    status = "NG"
elif blank_types:
    status = "BLANK"
else:
    status = "OK"
```

- [ ] **Step 5: Add the Rules Engine entry point**

```python
def _signature_rule(content_text: str, criterion_name: str, config: dict) -> dict:
    primary = _signature_result_from_case(
        content_text,
        criterion_name,
        cases=[
            {
                "required_all": ["PO"],
                "required_any_groups": [["INVOICE", "COMMERCIALINVOICE"]],
            },
            {
                "required_all": ["PO", "COMMERCIALINVOICE"],
                "required_any_groups": [],
            },
        ],
    )
    if primary is not None:
        return primary
    return _signature_fallback_result(content_text, criterion_name)
```

The `config` argument remains part of the rule interface and proves configuration was resolved, even though behavior intentionally remains identical to the current hard-coded logic.

- [ ] **Step 6: Dispatch the new compare mode**

Add before the final `return None` in `execute_nvl_rule_engine`:

```python
if compare_mode == "NVL_SIGNATURE_STAMP_VALIDATION":
    return _signature_rule(content_text, criterion_name, config)
```

- [ ] **Step 7: Run parity tests and verify GREEN**

Run:

```powershell
python -m unittest tests.test_nvl_rule_engine.NvlRuleEngineTests.test_signature_rule_matches_legacy_behavior -v
```

Expected: PASS for all six parity cases.

---

### Task 3: Route `CHUKICONDAU` Through AUTO Without Changing the Client Contract

**Files:**
- Modify: `tests/test_rule_engine_config_repository.py`
- Modify: `tests/test_nvl_rule_engine.py`
- Modify: `App/Rules_BE/rule_engine_config_repository.py`
- Modify: `App/Rules_BE/rules_ai_bem_meiko.py`

**Interfaces:**
- Consumes: existing request directive fields and default `compare_execution_mode=AUTO`.
- Produces: config lookup with `("BEM_AGENT_BEMF2000_WAREHOUSE", "CRITERIA_SIGNATURE_STAMP")` and an AUTO response without calling `generate_with_trim_fn`.

- [ ] **Step 1: Add a failing repository mapping test**

Extend the fake cursor test to call:

```python
loader("NGUYENVATLIEU", "CHUKICONDAU")
```

Assert the final SQL parameters are:

```python
("BEM_AGENT_BEMF2000_WAREHOUSE", "CRITERIA_SIGNATURE_STAMP")
```

- [ ] **Step 2: Add a failing AUTO orchestration test**

Build `latest_user` with the existing directive and no request mode field:

```python
latest_user = """
***
{
  "PromptType": "Đối chiếu",
  "DnttType": "Nguyên vật liệu",
  "FormationID": "Kế thừa công nợ",
  "Installment": "Mặc định",
  "CriterionName": "Chữ ký con dấu"
}
***
2. Dữ liệu đầu vào:
{ Loại chứng từ: PO | Chữ ký và con dấu: VALID | Tên file: po.pdf }
{ Loại chứng từ: INVOICE | Chữ ký và con dấu: VALID | Tên file: invoice.pdf }
"""
```

Call `process_ai_llms_models_rules` without passing `compare_execution_mode`, return `nvl_signature_config()` from the loader, and use:

```python
generate_with_trim_fn=lambda **kwargs: self.fail("LLM must not run for NVL signature AUTO routing")
```

Assert:

```python
self.assertEqual(loader_calls, [("NGUYENVATLIEU", "CHUKICONDAU")])
self.assertEqual(status_code, 200)
self.assertEqual(result, legacy_signature_result(content_text))
```

- [ ] **Step 3: Run focused routing tests and verify RED**

Run:

```powershell
python -m unittest tests.test_rule_engine_config_repository -v
python -m unittest tests.test_nvl_rule_engine.NvlRuleEngineTests.test_signature_auto_mode_uses_rule_engine_without_llm -v
```

Expected: repository test fails because the criterion mapping is absent; orchestration fails or reaches the legacy path.

- [ ] **Step 4: Add the stable repository mapping**

Extend `_CRITERION_PARAMETER_NAMES`:

```python
"CHUKICONDAU": "CRITERIA_SIGNATURE_STAMP",
```

- [ ] **Step 5: Remove only NVL from the legacy shared branch**

Change:

```python
dntt_prompt_key in {"MAYMOC", "KHAC", "NGUYENVATLIEU"}
```

to:

```python
dntt_prompt_key in {"MAYMOC", "KHAC"}
```

Do not remove `_build_signature_compare_result` or `_build_signature_fallback_result`; other DNTT paths and parity tests still consume them.

- [ ] **Step 6: Run focused routing tests and verify GREEN**

Run:

```powershell
python -m unittest tests.test_rule_engine_config_repository -v
python -m unittest tests.test_nvl_rule_engine.NvlRuleEngineTests.test_signature_auto_mode_uses_rule_engine_without_llm -v
```

Expected: PASS; loader sees the stable codes and the LLM callback is never invoked.

---

### Task 4: Lock the Existing Output Message Contract

**Files:**
- Modify: `tests/test_rule_engine_message_contract.py`

**Interfaces:**
- Consumes: `execute_nvl_rule_engine` with the signature config.
- Produces: exact message-contract assertions for `OK`, `NG`, and `BLANK`.

- [ ] **Step 1: Add `_signature_config()`**

Use the same compare mode and three mappings defined in Task 1.

- [ ] **Step 2: Add exact contract assertions**

Add tests that assert the complete `criteria` object, not only status. Include:

```python
{
    "CriteriaName": "Chữ ký con dấu",
    "CriteriaStatus": "OK",
    "FileName": "",
    "Description": "Các loại chứng từ Yêu cầu mua hàng (PO) và Hóa đơn (VAT) đều được có chữ ký và con dấu hợp lệ",
}
```

Also lock the current invalid and missing/blank descriptions by obtaining the exact legacy values in the test setup and asserting dictionary equality.

- [ ] **Step 3: Run the message-contract suite**

Run:

```powershell
python -m unittest tests.test_rule_engine_message_contract -v
```

Expected: PASS with unchanged existing contracts and the new signature cases.

---

### Task 5: Add `BEMT2009` Seed and Idempotent Migration

**Files:**
- Modify: `scripts/sql/20261008_migrate_ont1043_to_bemt2009.sql`
- Create: `scripts/sql/20261014_add_nvl_signature_rule.sql`
- Create: `tests/test_nvl_signature_rule_sql.py`

**Interfaces:**
- Consumes: `BEM_AGENT_BEMF2000_WAREHOUSE` and `CRITERIA_SIGNATURE_STAMP` from the repository mapping.
- Produces: one active rule and three active mappings in group `NVL_CHU_KY_CON_DAU_V1`.

- [ ] **Step 1: Add failing SQL text-contract tests**

Create tests that read both SQL files as UTF-8 and assert they contain:

```python
required_tokens = [
    "NVL_CHU_KY_CON_DAU_V1",
    "CRITERIA_SIGNATURE_STAMP",
    "NVL_SIGNATURE_STAMP_VALIDATION",
    "'PO', 'Signature'",
    "'INVOICE', 'Signature'",
    "'COMMERCIALINVOICE', 'Signature'",
    "'NEVER'",
]
```

Also assert the canonical migration validates `39` rows instead of `35`.

- [ ] **Step 2: Run the SQL contract tests and verify RED**

Run:

```powershell
python -m unittest tests.test_nvl_signature_rule_sql -v
```

Expected: FAIL because the seed and migration do not yet exist.

- [ ] **Step 3: Add four canonical seed rows**

Append these stable APKs to the `SeedData` CTE before its closing parenthesis:

```text
D7B92E37-C8CE-451F-BEB8-17C0C155F976  MAPPING PO
00FD8D88-F403-4CDB-9470-180C530CBDDE  MAPPING INVOICE
4254C22F-99A2-4B23-A0AA-4167A654CC06  MAPPING COMMERCIALINVOICE
F83ACF96-4FBF-44FB-9AF0-8544C79662E2  RULE
```

Use these values:

```sql
'NVL_CHU_KY_CON_DAU_V1',
'BEM_AGENT_BEMF2000_WAREHOUSE',
'CRITERIA_SIGNATURE_STAMP',
'nvl-v1'
```

Mappings use `DnttFieldCode='BEMT2001.APK'`, `EvidenceFieldCode='Signature'`, priorities `1`, and policies `ALL` for `PO`, `ANY` for the invoice types. The rule uses:

```sql
NormalizeMode = 'SIGNATURE_STATUS'
CompareMode = 'NVL_SIGNATURE_STAMP_VALIDATION'
CompareParams = N'requiredAll=PO;requiredAny=INVOICE,COMMERCIALINVOICE;selectedBlank=NG;fallbackBlank=BLANK;missing=BLANK'
LLMPolicy = 'NEVER'
```

Update the exact row-count assertion and error message from `35` to `39`.

- [ ] **Step 4: Create the idempotent deployment migration**

The script must:

1. Begin a transaction with `SET XACT_ABORT ON`.
2. Throw a clear error if `dbo.BEMT2009` does not exist.
3. Deactivate conflicting active rows for the same DNTT/criterion but a different group/version.
4. Insert each stable APK only when absent.
5. Update each stable APK to the intended active values when already present.
6. Assert exactly one active `RULE` and exactly three active `MAPPING` rows for the group.
7. Commit on success and roll back in `CATCH`.

- [ ] **Step 5: Run SQL text-contract tests and verify GREEN**

Run:

```powershell
python -m unittest tests.test_nvl_signature_rule_sql -v
```

Expected: PASS.

---

### Task 6: Regression Verification

**Files:**
- Verify all modified files.

**Interfaces:**
- Consumes: completed Tasks 1-5.
- Produces: evidence that the feature works and existing Rules Engine behavior remains intact.

- [ ] **Step 1: Run focused Rules Engine suites**

```powershell
python -m unittest tests.test_compare_execution_mode -v
python -m unittest tests.test_rule_engine_config_repository -v
python -m unittest tests.test_nvl_rule_engine -v
python -m unittest tests.test_rule_engine_message_contract -v
python -m unittest tests.test_nvl_signature_rule_sql -v
```

Expected: all tests pass with zero failures and zero errors.

- [ ] **Step 2: Run adjacent rules regression suites**

```powershell
python -m unittest tests.test_rules_ai_bem_meiko_delivery_term -v
python -m unittest tests.test_rules_ai_bem_meiko_payment_deadline -v
python -m unittest tests.test_rules_ai_bem_meiko_construction_payment_deadline -v
```

Expected: all tests pass; moving NVL signature routing does not affect delivery/payment paths.

- [ ] **Step 3: Run syntax compilation**

```powershell
python -m compileall App/Rules_BE tests
```

Expected: command exits `0` with no syntax errors.

- [ ] **Step 4: Inspect the final diff without touching unrelated changes**

```powershell
git diff --check
git status --short
```

Confirm only the intended files from this plan were changed by this feature, while pre-existing unrelated modifications remain untouched.

- [ ] **Step 5: Report the contract and deployment requirements**

Report that the client payload remains unchanged, omitted execution mode still means `AUTO`, and production requires applying `scripts/sql/20261014_add_nvl_signature_rule.sql` with `RULE_ENGINE_ENABLED=true`.
