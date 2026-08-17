# Delivery Term Code Logic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace LLM-based delivery-term comparison with deterministic Python logic for every dossier branch whose resolved rule enables `DIEUKIENGIAOHANG`.

**Architecture:** Reuse the existing fixed document-block parser, add data-driven Incoterm/country/province catalogs and pure normalization/comparison helpers in `App/Rules_AI_BEM_MEIKO.py`, then add an early return in `process_ai_llms_models_rules`. The specialized handler owns `OK`, `NG`, and `BLANK` semantics and never calls the LLM.

**Tech Stack:** Python 3, standard library `re`, `unicodedata`, `unittest`.

---

## File structure

- Create `tests/test_rules_ai_bem_meiko_delivery_term.py`: focused normalization, comparison, result-building, and integration tests.
- Modify `App/Rules_AI_BEM_MEIKO.py:139`: add delivery-term catalogs near other comparison support configuration.
- Modify `App/Rules_AI_BEM_MEIKO.py:1328`: add pure helpers beside the existing fixed compare-block parser.
- Modify `App/Rules_AI_BEM_MEIKO.py:2391`: add the deterministic early-return branch before generic missing-document guards and LLM generation.

Repository policy does not allow commits unless the user explicitly requests them, so this plan intentionally contains no commit steps.

### Task 1: Add parsing and normalization behavior

**Files:**
- Create: `tests/test_rules_ai_bem_meiko_delivery_term.py`
- Modify: `App/Rules_AI_BEM_MEIKO.py:139`
- Modify: `App/Rules_AI_BEM_MEIKO.py:1328`

- [ ] **Step 1: Write failing parser and normalization tests**

Create the test module and import the planned helpers:

```python
import unittest

from App.Rules_AI_BEM_MEIKO import (
    _normalize_delivery_term,
    _parse_fixed_compare_document_blocks,
)


class DeliveryTermNormalizationTests(unittest.TestCase):
    def test_parser_handles_interleaved_blocks_and_field_order(self):
        content = """
{ Ten file: PO.pdf | Dieu kien giao hang: CIF TOKYO | Loai chung tu: PO }
{ Loai chung tu: INVOICE | Ten file: INV.pdf | Dieu kien giao hang: CIF }
"""
        self.assertEqual(
            _parse_fixed_compare_document_blocks(content),
            [
                {"TENFILE": "PO.pdf", "DIEUKIENGIAOHANG": "CIF TOKYO", "LOAICHUNGTU": "PO"},
                {"LOAICHUNGTU": "INVOICE", "TENFILE": "INV.pdf", "DIEUKIENGIAOHANG": "CIF"},
            ],
        )

    def test_normalizes_bare_incoterm(self):
        self.assertEqual(
            _normalize_delivery_term(" cif "),
            {"incoterm": "CIF", "country": "", "province": "", "location": ""},
        )

    def test_normalizes_special_ex_factory_alias(self):
        self.assertEqual(
            _normalize_delivery_term("EX-FACTORY"),
            {"incoterm": "EXW", "country": "", "province": "", "location": ""},
        )

    def test_normalizes_country_alias(self):
        self.assertEqual(
            _normalize_delivery_term("CIF Viet Nam"),
            {"incoterm": "CIF", "country": "VIETNAM", "province": "", "location": ""},
        )

    def test_normalizes_province_with_parent_country(self):
        self.assertEqual(
            _normalize_delivery_term("CIF HAI-PHONG"),
            {"incoterm": "CIF", "country": "VIETNAM", "province": "HAI_PHONG", "location": ""},
        )

    def test_preserves_unknown_location_without_inference(self):
        self.assertEqual(
            _normalize_delivery_term("CIP NOI BAI"),
            {"incoterm": "CIP", "country": "", "province": "", "location": "NOI BAI"},
        )

    def test_rejects_noise_and_invalid_prefix(self):
        self.assertIsNone(_normalize_delivery_term("T/T BASE"))
        self.assertIsNone(_normalize_delivery_term("HAI PHONG CIF"))
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m unittest tests.test_rules_ai_bem_meiko_delivery_term.DeliveryTermNormalizationTests -v
```

Expected: import failure because `_normalize_delivery_term` does not exist.

- [ ] **Step 3: Add the extendable catalogs**

Add these constants near `OPTIONAL_COMPARE_DOC_TYPES`:

```python
DELIVERY_TERM_DOCUMENT_TYPES = {"PO", "CUSTOMSHEET", "INVOICE", "COMMERCIALINVOICE"}
DELIVERY_TERM_INCOTERM_CODES = {
    "EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT",
    "CIP", "DAP", "DPU", "DAT", "DDP", "DDU",
}
DELIVERY_TERM_NOISE_VALUES = {
    "T/T", "T/ T", "T/T BASE", "TT BASE", "BY TT", "PAYMENT",
    "PAYMENT TERM", "L/C", "LC", "NET 30", "NET 60",
}
DELIVERY_TERM_COUNTRY_CATALOG = {
    "VIETNAM": ["VIETNAM", "VIET NAM", "VN", "VIE", "VIET NAM"],
    "JAPAN": ["JAPAN", "JP", "JPN", "NHAT BAN"],
    "CHINA": ["CHINA", "CN", "CHN", "TRUNG QUOC"],
}
DELIVERY_TERM_PROVINCE_CATALOG = {
    ("VIETNAM", "HA_NOI"): ["HA NOI", "HANOI"],
    ("VIETNAM", "HAI_PHONG"): ["HAI PHONG", "HP"],
    ("VIETNAM", "BAC_NINH"): ["BAC NINH"],
    ("VIETNAM", "BAC_GIANG"): ["BAC GIANG"],
    ("VIETNAM", "HAI_DUONG"): ["HAI DUONG"],
    ("VIETNAM", "HUNG_YEN"): ["HUNG YEN"],
    ("VIETNAM", "VINH_PHUC"): ["VINH PHUC"],
    ("VIETNAM", "THAI_NGUYEN"): ["THAI NGUYEN"],
    ("VIETNAM", "PHU_THO"): ["PHU THO"],
    ("VIETNAM", "QUANG_NINH"): ["QUANG NINH"],
    ("VIETNAM", "HA_NAM"): ["HA NAM"],
    ("VIETNAM", "NAM_DINH"): ["NAM DINH"],
    ("VIETNAM", "NINH_BINH"): ["NINH BINH"],
    ("VIETNAM", "THAI_BINH"): ["THAI BINH"],
    ("VIETNAM", "LAO_CAI"): ["LAO CAI"],
    ("VIETNAM", "LANG_SON"): ["LANG SON"],
    ("VIETNAM", "CAO_BANG"): ["CAO BANG"],
    ("VIETNAM", "TUYEN_QUANG"): ["TUYEN QUANG"],
    ("VIETNAM", "YEN_BAI"): ["YEN BAI"],
    ("VIETNAM", "SON_LA"): ["SON LA"],
    ("VIETNAM", "DIEN_BIEN"): ["DIEN BIEN"],
    ("VIETNAM", "LAI_CHAU"): ["LAI CHAU"],
    ("VIETNAM", "HOA_BINH"): ["HOA BINH"],
    ("JAPAN", "TOKYO"): ["TOKYO", "TOKYO TO"],
    ("JAPAN", "OSAKA"): ["OSAKA", "OSAKA FU"],
    ("JAPAN", "KYOTO"): ["KYOTO", "KYOTO FU"],
    ("JAPAN", "AICHI"): ["AICHI", "AICHI KEN", "NAGOYA"],
    ("JAPAN", "KANAGAWA"): ["KANAGAWA", "KANAGAWA KEN", "YOKOHAMA", "KAWASAKI"],
    ("JAPAN", "HYOGO"): ["HYOGO", "HYOGO KEN", "KOBE"],
    ("JAPAN", "SHIZUOKA"): ["SHIZUOKA", "SHIZUOKA KEN"],
    ("JAPAN", "FUKUOKA"): ["FUKUOKA", "FUKUOKA KEN"],
    ("JAPAN", "SAITAMA"): ["SAITAMA", "SAITAMA KEN"],
    ("JAPAN", "CHIBA"): ["CHIBA", "CHIBA KEN"],
    ("JAPAN", "IBARAKI"): ["IBARAKI", "IBARAKI KEN"],
    ("JAPAN", "TOCHIGI"): ["TOCHIGI", "TOCHIGI KEN"],
    ("JAPAN", "GUNMA"): ["GUNMA", "GUNMA KEN"],
    ("JAPAN", "MIE"): ["MIE", "MIE KEN"],
    ("JAPAN", "SHIGA"): ["SHIGA", "SHIGA KEN"],
    ("JAPAN", "GIFU"): ["GIFU", "GIFU KEN"],
    ("JAPAN", "NAGANO"): ["NAGANO", "NAGANO KEN"],
    ("JAPAN", "NIIGATA"): ["NIIGATA", "NIIGATA KEN"],
    ("JAPAN", "HIROSHIMA"): ["HIROSHIMA", "HIROSHIMA KEN"],
    ("JAPAN", "OKAYAMA"): ["OKAYAMA", "OKAYAMA KEN"],
    ("JAPAN", "MIYAGI"): ["MIYAGI", "MIYAGI KEN", "SENDAI"],
    ("JAPAN", "HOKKAIDO"): ["HOKKAIDO", "SAPPORO"],
    ("JAPAN", "KUMAMOTO"): ["KUMAMOTO", "KUMAMOTO KEN"],
    ("JAPAN", "OKINAWA"): ["OKINAWA", "OKINAWA KEN"],
    ("CHINA", "SHANGHAI"): ["SHANGHAI"],
    ("CHINA", "BEIJING"): ["BEIJING"],
    ("CHINA", "GUANGDONG"): ["GUANGDONG", "GUANGZHOU", "GUANG ZHOU", "SHENZHEN", "DONGGUAN"],
    ("CHINA", "JIANGSU"): ["JIANGSU", "SUZHOU", "NANJING"],
    ("CHINA", "ZHEJIANG"): ["ZHEJIANG", "HANGZHOU", "NINGBO"],
    ("CHINA", "SHANDONG"): ["SHANDONG", "QINGDAO"],
    ("CHINA", "TIANJIN"): ["TIANJIN"],
}
```

Build alias maps with a helper that normalizes Latin accents and punctuation but preserves CJK aliases. Include the accented Vietnamese and CJK aliases from the approved system prompt in the actual catalog entries; normalized Vietnamese aliases collapse onto the ASCII forms.

- [ ] **Step 4: Implement minimal normalization helpers**

Add these helpers after `_parse_fixed_compare_document_blocks`:

```python
def _normalize_delivery_term_lookup_text(value: object) -> str:
    raw = str(value or "").strip().upper()
    no_accent = "".join(
        char for char in unicodedata.normalize("NFKD", raw)
        if not unicodedata.combining(char)
    )
    normalized = re.sub(r"[-_.]+", " ", no_accent)
    return " ".join(normalized.split())


def _normalize_delivery_term(value: object) -> dict[str, str] | None:
    normalized = _normalize_delivery_term_lookup_text(value)
    if not normalized or normalized in DELIVERY_TERM_NOISE_NORMALIZED:
        return None
    if normalized in {"EX FACTORY", "EXW FACTORY"}:
        return {"incoterm": "EXW", "country": "", "province": "", "location": ""}
    match = re.match(r"^([A-Z]{3})(?:\s+(.*))?$", normalized)
    if not match or match.group(1) not in DELIVERY_TERM_INCOTERM_CODES:
        return None
    incoterm = match.group(1)
    suffix = str(match.group(2) or "").strip()
    country = DELIVERY_TERM_COUNTRY_ALIAS_MAP.get(suffix, "")
    province_info = DELIVERY_TERM_PROVINCE_ALIAS_MAP.get(suffix)
    if province_info:
        return {"incoterm": incoterm, "country": province_info[0], "province": province_info[1], "location": ""}
    if country:
        return {"incoterm": incoterm, "country": country, "province": "", "location": ""}
    return {"incoterm": incoterm, "country": "", "province": "", "location": suffix}
```

- [ ] **Step 5: Run normalization tests and verify GREEN**

Run:

```powershell
python -m unittest tests.test_rules_ai_bem_meiko_delivery_term.DeliveryTermNormalizationTests -v
```

Expected: all normalization tests pass.

### Task 2: Build representative selection and all-pairs comparison

**Files:**
- Modify: `tests/test_rules_ai_bem_meiko_delivery_term.py`
- Modify: `App/Rules_AI_BEM_MEIKO.py:1328`

- [ ] **Step 1: Write failing comparison tests**

Add tests importing `_build_delivery_term_result`:

```python
from App.Rules_AI_BEM_MEIKO import _build_delivery_term_result


class DeliveryTermResultTests(unittest.TestCase):
    def test_bare_incoterm_covers_one_detailed_value(self):
        result = _build_delivery_term_result("""
{ Loai chung tu: PO | Dieu kien giao hang: CIF TOKYO | Ten file: PO.pdf }
{ Loai chung tu: CUSTOMSHEET | Dieu kien giao hang: CIF | Ten file: CUS.xlsx }
""", "Dieu kien giao hang")
        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_bare_incoterm_does_not_hide_two_province_conflicts(self):
        result = _build_delivery_term_result("""
{ Loai chung tu: CUSTOMSHEET | Dieu kien giao hang: CIF | Ten file: CUS.xlsx }
{ Loai chung tu: PO | Dieu kien giao hang: CIF TOKYO | Ten file: PO.pdf }
{ Loai chung tu: COMMERCIALINVOICE | Dieu kien giao hang: CIF OSAKA | Ten file: CINV.pdf }
""", "Dieu kien giao hang")
        self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")
        self.assertEqual(result["criteria"]["FileName"], "PO.pdf, CINV.pdf")

    def test_country_matches_province_inside_country(self):
        result = _build_delivery_term_result("""
{ Loai chung tu: PO | Dieu kien giao hang: CIF JAPAN | Ten file: PO.pdf }
{ Loai chung tu: INVOICE | Dieu kien giao hang: CIF TOKYO | Ten file: INV.pdf }
""", "Dieu kien giao hang")
        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")

    def test_invoice_and_commercial_invoice_are_both_compared(self):
        result = _build_delivery_term_result("""
{ Loai chung tu: PO | Dieu kien giao hang: CIF | Ten file: PO.pdf }
{ Loai chung tu: INVOICE | Dieu kien giao hang: CIF TOKYO | Ten file: INV.pdf }
{ Loai chung tu: COMMERCIALINVOICE | Dieu kien giao hang: CIF OSAKA | Ten file: CINV.pdf }
""", "Dieu kien giao hang")
        self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")

    def test_majority_value_wins_and_noise_is_ignored(self):
        result = _build_delivery_term_result("""
{ Loai chung tu: PO | Dieu kien giao hang: T/T BASE | Ten file: noise.pdf }
{ Loai chung tu: PO | Dieu kien giao hang: CIF TOKYO | Ten file: PO1.pdf }
{ Loai chung tu: PO | Dieu kien giao hang: CIF TOKYO | Ten file: PO2.pdf }
{ Loai chung tu: PO | Dieu kien giao hang: CIF OSAKA | Ten file: PO3.pdf }
{ Loai chung tu: CUSTOMSHEET | Dieu kien giao hang: CIF JAPAN | Ten file: CUS.xlsx }
""", "Dieu kien giao hang")
        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")
        self.assertEqual(result["criteria"]["FileName"], "")

    def test_top_count_tie_inside_document_type_is_ng(self):
        result = _build_delivery_term_result("""
{ Loai chung tu: PO | Dieu kien giao hang: CIF TOKYO | Ten file: PO1.pdf }
{ Loai chung tu: PO | Dieu kien giao hang: CIF OSAKA | Ten file: PO2.pdf }
{ Loai chung tu: CUSTOMSHEET | Dieu kien giao hang: CIF | Ten file: CUS.xlsx }
""", "Dieu kien giao hang")
        self.assertEqual(result["criteria"]["CriteriaStatus"], "NG")
        self.assertEqual(result["criteria"]["FileName"], "PO1.pdf, PO2.pdf")

    def test_zero_or_one_valid_document_type_is_blank(self):
        result = _build_delivery_term_result("""
{ Loai chung tu: PO | Dieu kien giao hang: CIF | Ten file: PO.pdf }
{ Loai chung tu: CUSTOMSHEET | Dieu kien giao hang: T/T | Ten file: CUS.xlsx }
""", "Dieu kien giao hang")
        self.assertEqual(result["criteria"]["CriteriaStatus"], "BLANK")

    def test_unknown_locations_match_only_when_equal(self):
        ok_result = _build_delivery_term_result("""
{ Loai chung tu: PO | Dieu kien giao hang: CIP NOI BAI | Ten file: PO.pdf }
{ Loai chung tu: INVOICE | Dieu kien giao hang: CIP NOI-BAI | Ten file: INV.pdf }
""", "Dieu kien giao hang")
        ng_result = _build_delivery_term_result("""
{ Loai chung tu: PO | Dieu kien giao hang: CIP NOI BAI | Ten file: PO.pdf }
{ Loai chung tu: INVOICE | Dieu kien giao hang: CIP TAN SON NHAT | Ten file: INV.pdf }
""", "Dieu kien giao hang")
        self.assertEqual(ok_result["criteria"]["CriteriaStatus"], "OK")
        self.assertEqual(ng_result["criteria"]["CriteriaStatus"], "NG")
```

Also add explicit tests for different Incoterms, different countries, same province aliases, ten-file limits, and stable input ordering.

- [ ] **Step 2: Run result tests and verify RED**

Run:

```powershell
python -m unittest tests.test_rules_ai_bem_meiko_delivery_term.DeliveryTermResultTests -v
```

Expected: import failure because `_build_delivery_term_result` does not exist.

- [ ] **Step 3: Implement formatting and pair compatibility helpers**

Add:

```python
def _delivery_term_key(value: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        value.get("incoterm", ""),
        value.get("country", ""),
        value.get("province", ""),
        value.get("location", ""),
    )


def _format_delivery_term(value: dict[str, str]) -> str:
    suffix = value.get("province") or value.get("country") or value.get("location") or ""
    return " ".join(part for part in [value.get("incoterm", ""), suffix] if part)


def _delivery_term_mismatch(left: dict[str, str], right: dict[str, str]) -> str:
    if left["incoterm"] != right["incoterm"]:
        return "incoterm"
    left_is_bare = not any(left[key] for key in ("country", "province", "location"))
    right_is_bare = not any(right[key] for key in ("country", "province", "location"))
    if left_is_bare or right_is_bare:
        return ""
    if left["location"] or right["location"]:
        return "" if left["location"] and left["location"] == right["location"] else "location"
    if left["country"] != right["country"]:
        return "country"
    if left["province"] and right["province"] and left["province"] != right["province"]:
        return "province"
    return ""
```

- [ ] **Step 4: Implement deterministic result building**

Implement `_build_delivery_term_result(content_text, criterion_name)` with these exact stages:

1. Parse blocks with `_parse_fixed_compare_document_blocks`.
2. Keep only `DELIVERY_TERM_DOCUMENT_TYPES`.
3. Normalize field `DIEUKIENGIAOHANG` and retain document type, file, normalized value, and source index.
4. Count complete normalized keys per document type.
5. Return `NG` immediately for a top-count tie, listing first files from tied groups in source order.
6. If fewer than two document groups have representatives, return `BLANK` with invalid/missing files capped at ten.
7. Compare every representative pair and collect mismatches.
8. Select the first mismatch by priority `incoterm > country > province > location` and then source order.
9. Return `NG` with the two representative files and description formatted as `PO = CIF TOKYO, COMMERCIALINVOICE = CIF OSAKA.`.
10. Otherwise return the exact success text `Dieu kien giao hang da hoan toan khop voi nhau.` using accented Vietnamese in source.

Return schema:

```python
{
    "criteria": {
        "CriteriaName": criterion_name or "Dieu kien giao hang",
        "CriteriaStatus": status,
        "FileName": file_name,
        "Description": description,
    }
}
```

- [ ] **Step 5: Run result tests and verify GREEN**

Run:

```powershell
python -m unittest tests.test_rules_ai_bem_meiko_delivery_term.DeliveryTermResultTests -v
```

Expected: all result tests pass.

### Task 3: Integrate the no-LLM early-return branch

**Files:**
- Modify: `tests/test_rules_ai_bem_meiko_delivery_term.py`
- Modify: `App/Rules_AI_BEM_MEIKO.py:2391`

- [ ] **Step 1: Write failing integration tests**

Add a shared no-op logger and call `process_ai_llms_models_rules` with a generator callback that raises:

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from App.Rules_AI_BEM_MEIKO import process_ai_llms_models_rules


class DeliveryTermIntegrationTests(unittest.TestCase):
    def test_enabled_delivery_term_rule_returns_without_llm(self):
        latest_user = """***
{
 "PromptType": "Doi chieu",
 "DnttType": "Nguyen vat lieu",
 "FormationID": "Ke thua cong no",
 "Installment": "",
 "CriterionName": "Dieu kien giao hang"
}
***
{ Loai chung tu: PO | Dieu kien giao hang: CIF TOKYO | Ten file: PO.pdf }
{ Loai chung tu: CUSTOMSHEET | Dieu kien giao hang: CIF | Ten file: CUS.xlsx }
{ Loai chung tu: COMMERCIALINVOICE | Dieu kien giao hang: CIF JAPAN | Ten file: CINV.pdf }
"""
        response_logs = []
        cleanup_calls = []

        def fail_if_llm_called(**kwargs):
            raise AssertionError("LLM must not run for delivery-term logic")

        class Logger:
            def info(self, *args, **kwargs):
                pass
            def warning(self, *args, **kwargs):
                pass

        with TemporaryDirectory() as temp_dir:
            result, status_code = process_ai_llms_models_rules(
                latest_system="unused",
                latest_user=latest_user,
                cfg={},
                special_id="test-model",
                max_new_tokens=128,
                temperature=0.0,
                ocr_split_max_pages=5,
                ocr_split_overlap_pages=0,
                normalize_txt_path=Path(temp_dir) / "normalize.txt",
                sections_txt_path=Path(temp_dir) / "sections.txt",
                data_holidays_dir=Path("App/Data_Holidays"),
                split_ocr_text_fn=lambda **kwargs: [],
                generate_with_trim_fn=fail_if_llm_called,
                append_response_log_fn=response_logs.append,
                light_cuda_cleanup_fn=lambda: cleanup_calls.append(True),
                logger=Logger(),
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["criteria"]["CriteriaStatus"], "OK")
        self.assertEqual(len(response_logs), 1)
        self.assertEqual(cleanup_calls, [True])
```

Add a second integration test for an enabled `MAYMOC + KETHUA_CONGNO + DEFAULT` prompt. Add a third test proving a skipped or unresolved branch keeps existing behavior and does not accidentally enter the specialized handler.

- [ ] **Step 2: Run integration tests and verify RED**

Run:

```powershell
python -m unittest tests.test_rules_ai_bem_meiko_delivery_term.DeliveryTermIntegrationTests -v
```

Expected: the enabled branch reaches `generate_with_trim_fn` and raises.

- [ ] **Step 3: Add the scoped early return**

Insert after `is_compare_mode` is computed and after the existing payment-deadline special branch, but before `skip_compare` and all generic missing-document handling:

```python
if (
    is_compare_mode
    and criterion_key == "DIEUKIENGIAOHANG"
    and compare_cfg
    and not compare_cfg.get("skip_compare")
):
    result = _build_delivery_term_result(content_user_process, criterion_name)
    append_response_log_fn(result)
    light_cuda_cleanup_fn()
    return result, 200
```

Do not scope by a hard-coded DNTT set; resolved rule configuration is the source of truth, so future dossier branches can enable the criterion without changing the handler.

- [ ] **Step 4: Run integration and feature tests**

Run:

```powershell
python -m unittest tests.test_rules_ai_bem_meiko_delivery_term -v
```

Expected: all delivery-term tests pass and enabled branches never call the LLM stub.

### Task 4: Regression and final verification

**Files:**
- Verify: `App/Rules_AI_BEM_MEIKO.py`
- Verify: `tests/test_rules_ai_bem_meiko_delivery_term.py`
- Verify: `tests/test_rules_ai_bem_meiko_payment_deadline.py`
- Verify: `tests/test_rules_ai_bem_meiko_extract_prompt_filter.py`

- [ ] **Step 1: Compile changed Python files**

Run:

```powershell
python -m py_compile App/Rules_AI_BEM_MEIKO.py tests/test_rules_ai_bem_meiko_delivery_term.py
```

Expected: exit code 0 with no output.

- [ ] **Step 2: Run the focused delivery-term suite**

Run:

```powershell
python -m unittest tests.test_rules_ai_bem_meiko_delivery_term -v
```

Expected: all tests pass with zero failures and zero errors.

- [ ] **Step 3: Run adjacent rule regressions**

Run:

```powershell
python -m unittest tests.test_rules_ai_bem_meiko_payment_deadline tests.test_rules_ai_bem_meiko_extract_prompt_filter -v
```

Expected: all existing adjacent tests pass.

- [ ] **Step 4: Run diff validation**

Run:

```powershell
git diff --check -- App/Rules_AI_BEM_MEIKO.py tests/test_rules_ai_bem_meiko_delivery_term.py docs/superpowers/specs/2026-07-24-delivery-term-code-logic-design.md docs/superpowers/plans/2026-07-24-delivery-term-code-logic.md
git diff --stat -- App/Rules_AI_BEM_MEIKO.py tests/test_rules_ai_bem_meiko_delivery_term.py docs/superpowers/specs/2026-07-24-delivery-term-code-logic-design.md docs/superpowers/plans/2026-07-24-delivery-term-code-logic.md
```

Expected: no whitespace errors; the diff contains only delivery-term logic, tests, and approved documentation.
