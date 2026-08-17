# Packing List Section Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuẩn hóa `INVOICE` và `COMMERCIALINVOICE` thành `PACKINGLIST` cho mọi tên file có basename bắt đầu bằng `PL`.

**Architecture:** Mở rộng hàm hậu xử lý `_normalize_extract_section_type_by_filename`, vốn đã chuẩn hóa `SectionType` theo prefix tên file sau bước merge. Rule mới dùng một tập source type cho prefix `PL`, không tạo thêm pipeline hoặc thay đổi logic lọc prompt.

**Tech Stack:** Python 3, `unittest`.

---

### Task 1: Thêm kiểm thử hồi quy cho prefix PL

**Files:**
- Modify: `tests/test_rules_ai_bem_meiko_extract_prompt_filter.py`
- Test: `tests/test_rules_ai_bem_meiko_extract_prompt_filter.py`

- [ ] **Step 1: Import hàm chuẩn hóa**

Thêm `_normalize_extract_section_type_by_filename` vào import từ `App.Rules_AI_BEM_MEIKO`.

- [ ] **Step 2: Viết test thất bại**

Thêm test case gọi hàm với `PL_001.pdf` và `PLABC.pdf`, xác nhận `INVOICE` và `COMMERCIALINVOICE` đều trở thành `PACKINGLIST`. Thêm một section `BILL` để xác nhận loại không liên quan được giữ nguyên.

```python
class ExtractSectionTypeNormalizationTests(unittest.TestCase):
    def test_pl_prefix_normalizes_invoice_types_to_packinglist(self):
        for file_name, source_type in (
            (PL_001.pdf, INVOICE),
            (PLABC.pdf, COMMERCIALINVOICE),
        ):
            with self.subTest(file_name=file_name, source_type=source_type):
                sections = [
                    {master: {SectionType: source_type}},
                    {master: {SectionType: BILL}},
                ]

                result = _normalize_extract_section_type_by_filename(sections, file_name)

                self.assertEqual(result[0][master][SectionType], PACKINGLIST)
                self.assertEqual(result[1][master][SectionType], BILL)
```

- [ ] **Step 3: Chạy test để xác nhận RED**

Run: `python -m unittest tests.test_rules_ai_bem_meiko_extract_prompt_filter.ExtractSectionTypeNormalizationTests -v`

Expected: FAIL vì rule hiện tại chưa đổi `INVOICE` hoặc `COMMERCIALINVOICE` thành `PACKINGLIST` cho prefix `PL`.

### Task 2: Mở rộng logic chuẩn hóa SectionType

**Files:**
- Modify: `App/Rules_AI_BEM_MEIKO.py:1661`
- Test: `tests/test_rules_ai_bem_meiko_extract_prompt_filter.py`

- [ ] **Step 1: Thêm rule PL tối thiểu**

Đổi biến source type đơn thành tập source type và thêm nhánh `PL` trước các nhánh hiện có:

```python
if name_upper.startswith(PL):
    source_types = {INVOICE, COMMERCIALINVOICE}
    target_type = PACKINGLIST
elif name_upper.startswith((IN, IV, INV)):
    source_types = {COMMERCIALINVOICE}
    target_type = INVOICE
elif name_upper.startswith(COM):
    source_types = {INVOICE}
    target_type = COMMERCIALINVOICE
else:
    return sections
```

Trong vòng lặp, đổi điều kiện thành:

```python
if _normalize_doc_type(master.get(SectionType)) in source_types:
    master[SectionType] = target_type
```

- [ ] **Step 2: Chạy test mới để xác nhận GREEN**

Run: `python -m unittest tests.test_rules_ai_bem_meiko_extract_prompt_filter.ExtractSectionTypeNormalizationTests -v`

Expected: PASS.

- [ ] **Step 3: Chạy toàn bộ test liên quan**

Run: `python -m unittest tests.test_rules_ai_bem_meiko_extract_prompt_filter -v`

Expected: Tất cả test PASS, bao gồm mapping prefix và integration hiện có.

- [ ] **Step 4: Kiểm tra diff giới hạn phạm vi**

Run: `git diff -- App/Rules_AI_BEM_MEIKO.py tests/test_rules_ai_bem_meiko_extract_prompt_filter.py docs/superpowers/specs/2026-07-24-packing-list-section-normalization-design.md docs/superpowers/plans/2026-07-24-packing-list-section-normalization.md`

Expected: Chỉ có rule `PL`, test hồi quy và tài liệu liên quan. Không commit vì người dùng chưa yêu cầu.
