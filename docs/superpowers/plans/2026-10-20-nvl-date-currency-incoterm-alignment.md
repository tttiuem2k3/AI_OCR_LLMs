# NVL Date Currency Incoterm Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đồng bộ tiêu chí Ngày hóa đơn, Loại tiền và Điều kiện giao hàng của bộ NVL với yêu cầu nghiệp vụ đã chốt.

**Architecture:** Giữ nguyên bộ máy Rule Engine hiện tại và điều khiển phạm vi chứng từ bằng prompt cùng mapping `BEMT2009`. Bổ sung mapping Packing list cho ngày hóa đơn, mapping Ringi cho loại tiền và loại bỏ INVOICE khỏi điều kiện giao hàng.

**Tech Stack:** Python 3.11, unittest/pytest, SQL Server, Handlebars prompt SQL.

## Global Constraints

- Ngày Packing list phải khớp tuyệt đối, không có dung sai ngày.
- Loại tiền chỉ bổ sung Ringi, không bổ sung Packing list.
- Điều kiện giao hàng chỉ dùng Tờ khai, PO và Hóa đơn thương mại.
- Nội dung hướng dẫn prompt dùng tên nghiệp vụ tiếng Việt, không dùng dạng `LOAICHUNGTU.FieldName`.

---

### Task 1: Viết test khóa yêu cầu

**Files:**
- Create: `tests/test_nvl_date_currency_incoterm_alignment.py`

- [x] Kiểm tra Packing list tham gia Ngày hóa đơn và lệch một ngày trả NG.
- [x] Kiểm tra Ringi tham gia Loại tiền và sai loại tiền trả NG.
- [x] Kiểm tra prompt Điều kiện giao hàng không còn INVOICE/PACKINGLIST.
- [x] Kiểm tra prompt không dùng tên field kỹ thuật trong phần hướng dẫn.
- [x] Chạy test và xác nhận test thất bại trước khi sửa.

### Task 2: Cập nhật prompt và seed DB

**Files:**
- Modify: `Prompt_AI_BEM_v11/WareHouse/Prompt_WareHouse_VoucherDate.sql`
- Modify: `Prompt_AI_BEM_v11/WareHouse/Prompt_WareHouse_Currency.sql`
- Modify: `Prompt_AI_BEM_v11/WareHouse/Prompt_WareHouse_DeliveryTerm.sql`
- Modify: `scripts/sql/0_bemt2009.sql`
- Create: `scripts/sql/6_sync_nvl_date_currency_incoterm.sql`

- [x] Bổ sung Số Packing list và Ngày Packing list cho tiêu chí Ngày hóa đơn.
- [x] Giữ `dateToleranceDays=0` và diễn đạt khớp tuyệt đối trong prompt.
- [x] Bổ sung Ringi cho tiêu chí Loại tiền.
- [x] Loại INVOICE khỏi Điều kiện giao hàng.
- [x] Viết script idempotent đồng bộ `BEMT2009`; dùng ba prompt SQL tương ứng để đồng bộ `ONT1042`.

### Task 3: Kiểm thử và cập nhật DB hiện tại

**Files:**
- Test: `tests/test_nvl_date_currency_incoterm_alignment.py`
- Test: `tests/test_nvl_rule_engine.py`

- [x] Chạy test mục tiêu.
- [x] Chạy toàn bộ test Rule Engine liên quan.
- [x] Chạy `py_compile` các file Python liên quan.
- [x] Chạy script đồng bộ trên DB hiện tại.
- [x] Truy vấn lại `BEMT2009` và `ONT1042` để xác nhận cấu hình thực tế.
