# Delivery Term Compatible Tie Bugfix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Treat equally frequent delivery-term variants as one logical condition when every tied value is mutually compatible, while preserving `NG` for conflicting Incoterms, countries, provinces, or locations.

**Architecture:** Keep exact normalized counting and majority selection unchanged. Only refine the highest-frequency tie branch: compare all tied representatives with `_delivery_term_mismatch`; collapse a mutually compatible tie to the most specific representative, otherwise retain the existing tie error.

**Tech Stack:** Python 3, standard library `unittest`.

---

### Task 1: Reproduce compatible and incompatible ties

**Files:**
- Modify: `tests/test_rules_ai_bem_meiko_delivery_term.py`

- [ ] **Step 1: Add failing compatible-tie tests**

Add tests asserting:

```python
def test_bare_and_one_unknown_location_tie_is_one_condition(self):
    result = self.build_result(
        _delivery_block("INVOICE", "invoice-bare.pdf", "DDP"),
        _delivery_block("INVOICE", "invoice-meiko.pdf", "DDP MEIKO"),
        _delivery_block("PO", "po.pdf", "DDP"),
    )
    self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")


def test_bare_country_and_province_tie_is_one_condition(self):
    result = self.build_result(
        _delivery_block("INVOICE", "invoice-bare.pdf", "DDP"),
        _delivery_block("INVOICE", "invoice-japan.pdf", "DDP JAPAN"),
        _delivery_block("INVOICE", "invoice-tokyo.pdf", "DDP TOKYO"),
        _delivery_block("PO", "po.pdf", "DDP"),
    )
    self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")
```

- [ ] **Step 2: Add incompatible-tie regression tests**

Add the four approved examples:

- `DDP JAPAN + DDP VIETNAM + DDP` returns `NG`.
- `DDP JAPAN + CIF VIETNAM + DDP` returns `NG`.
- `CIF + DDP JAPAN + CIF VIETNAM + DDP` returns `NG`.
- `DDP + DDP JAPAN + DDP TOKYO` returns `OK`.

Assert the `NG` cases still include the existing equally-frequent description and representative filenames.

- [ ] **Step 3: Add representative-specificity test**

Use a compatible `DDP + DDP JAPAN + DDP TOKYO` tie against another document group containing `DDP OSAKA`. Assert the selected mismatch description identifies the compatible tie representative as `DDP TOKYO`, proving specificity order `province > country > location > bare`.

- [ ] **Step 4: Run focused tests and verify RED**

Run:

```powershell
python -B -m unittest tests.test_rules_ai_bem_meiko_delivery_term.DeliveryTermResultTests -v
```

Expected: the compatible-tie tests fail because the current branch returns `NG` before document-level comparison.

### Task 2: Collapse mutually compatible highest-frequency ties

**Files:**
- Modify: `App/Rules_AI_BEM_MEIKO.py:1555`

- [ ] **Step 1: Add a specificity helper**

Add near the existing delivery-term comparison helpers:

```python
def _delivery_term_specificity(value: object) -> int:
    _, country, province, location = _delivery_term_key(value)
    if province:
        return 3
    if country:
        return 2
    if location:
        return 1
    return 0
```

- [ ] **Step 2: Detect mutually compatible ties**

After `first_records` is built and before appending `tie_results`, compare every pair:

```python
tie_is_compatible = all(
    not _delivery_term_mismatch(left["term"], right["term"])
    for left_index, left in enumerate(first_records)
    for right in first_records[left_index + 1:]
)
```

- [ ] **Step 3: Select the most specific compatible representative**

When `len(tied_keys) > 1` and `tie_is_compatible`:

```python
representative_record = min(
    first_records,
    key=lambda record: (
        -_delivery_term_specificity(record["term"]),
        int(record["source_index"]),
    ),
)
representatives.append({"document_type": document_type, **representative_record})
continue
```

When any pair is incompatible, retain the existing `tie_results` path unchanged.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
python -B -m unittest tests.test_rules_ai_bem_meiko_delivery_term.DeliveryTermResultTests -v
```

Expected: all result tests pass.

### Task 3: Verify integration and regressions

**Files:**
- Verify: `App/Rules_AI_BEM_MEIKO.py`
- Verify: `tests/test_rules_ai_bem_meiko_delivery_term.py`

- [ ] **Step 1: Compile changed Python files**

Run:

```powershell
python -m py_compile App/Rules_AI_BEM_MEIKO.py tests/test_rules_ai_bem_meiko_delivery_term.py
```

Expected: exit code 0.

- [ ] **Step 2: Run all repository tests**

Run:

```powershell
python -B -m unittest discover -s tests -v
```

Expected: all tests pass, including payment-deadline and extraction-filter regressions.

- [ ] **Step 3: Verify the reported production example**

Call `_build_delivery_term_result` with two `INVOICE` records containing `DDP` and `DDP MEIKO`, plus a compatible second document type. Assert the final status is `OK` and the old English tie description is absent.

- [ ] **Step 4: Validate focused diff**

Run `git diff --check` for the rule file, delivery-term tests, updated spec, and this plan. Confirm there are no whitespace errors and no unrelated behavioral changes.

No commit is created unless the user explicitly requests it.
