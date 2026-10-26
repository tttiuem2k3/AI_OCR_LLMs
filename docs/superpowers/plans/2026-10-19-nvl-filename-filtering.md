# NVL FileName Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chỉ trả các file NVL thực sự thiếu dữ liệu hoặc không khớp trong `criteria.FileName` mà không thay đổi kết luận nghiệp vụ.

**Architecture:** Bổ sung regression test cho từng lỗi đã tái hiện, sau đó thay cách thu thập file từ cấp loại chứng từ sang cấp document/entry. Riêng lệch tổng số tiền chỉ trả file xác định được bằng đối chiếu số hóa đơn; trường hợp mơ hồ để trống `FileName`.

**Tech Stack:** Python 3.12, `unittest`, Rules Engine hiện có.

## Global Constraints

- Không thay đổi schema response.
- Không thay đổi logic `CriteriaStatus` và ngưỡng nghiệp vụ.
- Không sửa các file Prompt SQL do người dùng quản lý.
- Không reset hoặc dọn các thay đổi không liên quan trong workspace.

---

### Task 1: Khóa các lỗi FileName bằng regression test

**Files:**
- Modify: `tests/test_nvl_rule_engine.py`

**Interfaces:**
- Consumes: `execute_nvl_rule_engine(...)` và các helper test hiện có.
- Produces: test tái hiện chính xác bốn nhóm liệt kê dư.

- [x] **Step 1: Thêm bốn regression test**

Thêm test cho số hóa đơn lệch một phần, chuỗi `STATEMENT` lệch một phần, chữ ký hỗn hợp cùng loại và số tiền lệch một phần.

- [x] **Step 2: Chạy test để xác nhận thất bại đúng nguyên nhân**

Run: `.\AI_BEM\Scripts\python.exe -m unittest tests.test_nvl_rule_engine -v`

Expected: test mới FAIL vì `FileName` còn chứa file đã khớp.

### Task 2: Lọc FileName theo document lỗi

**Files:**
- Modify: `App/Rules_BE/nvl_rule_engine.py`
- Test: `tests/test_nvl_rule_engine.py`

**Interfaces:**
- Consumes: document dictionaries từ `_parse_documents()`, `_field_names()`, `_invoice_numbers_match()` và `_amount_matches()`.
- Produces: các nhánh `_invoice_number_rule()`, `_signature_result_from_case()`, `_signature_fallback_result()` và `_amount_rule()` trả danh sách file chính xác hơn.

- [x] **Step 1: Sửa số hóa đơn và STATEMENT**

Chỉ lấy document có số hóa đơn không khớp; nhánh `STATEMENT` loại các tờ khai đã khớp `ListNo`.

- [x] **Step 2: Sửa chữ ký theo từng entry**

Thu thập `invalid_files` và `blank_files` trực tiếp từ entry tương ứng.

- [x] **Step 3: Sửa số tiền theo số hóa đơn**

Khi tổng loại chứng từ lệch, tìm document lệch theo số hóa đơn; nếu không xác định chắc chắn thì để trống `FileName`.

- [x] **Step 4: Chạy toàn bộ test NVL**

Run: `.\AI_BEM\Scripts\python.exe -m unittest tests.test_nvl_rule_engine -v`

Expected: toàn bộ test PASS.

### Task 3: Kiểm tra cú pháp và diff

**Files:**
- Verify: `App/Rules_BE/nvl_rule_engine.py`
- Verify: `tests/test_nvl_rule_engine.py`

**Interfaces:**
- Consumes: thay đổi từ Task 2.
- Produces: bằng chứng cú pháp và định dạng diff hợp lệ.

- [x] **Step 1: Kiểm tra py_compile**

Run: `.\AI_BEM\Scripts\python.exe -m py_compile App\Rules_BE\nvl_rule_engine.py tests\test_nvl_rule_engine.py`

- [x] **Step 2: Kiểm tra diff whitespace**

Run: `git diff --check -- App/Rules_BE/nvl_rule_engine.py tests/test_nvl_rule_engine.py`

- [x] **Step 3: Chạy lại toàn bộ test NVL**

Run: `.\AI_BEM\Scripts\python.exe -m unittest tests.test_nvl_rule_engine -v`

Expected: toàn bộ test PASS.
