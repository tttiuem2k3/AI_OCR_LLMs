# NVL Amount Statement And Ringi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đồng bộ tiêu chí Số tiền NVL với `STATEMENT.VoucherNo`, `STATEMENT.Amount` và quy tắc Ringi chỉ có giới hạn tối thiểu.

**Architecture:** Mở rộng rule deterministic hiện tại thay vì tạo nhánh LLM mới. Cấu hình DB quyết định loại chứng từ được đưa vào rule; prompt dự phòng sử dụng cùng tên field và cùng nghiệp vụ.

**Tech Stack:** Python, unittest, SQL Server, Handlebars prompt SQL.

## Global Constraints

- Không sửa tiêu chí Chữ ký, con dấu.
- Không thay đổi hành vi khi hồ sơ không có STATEMENT.
- `FileName` chỉ chứa file thiếu hoặc không khớp.
- Migration phải idempotent và có transaction.

---

### Task 1: Rule Engine Amount Behavior

**Files:**
- Modify: `tests/test_nvl_rule_engine.py`
- Modify: `App/Rules_BE/nvl_rule_engine.py`

**Interfaces:**
- Consumes: cấu hình `config["mappings"]` và `config["rule"]["CompareParams"]`.
- Produces: JSON `criteria` với `CriteriaStatus`, `FileName`, `Description`.

- [ ] Thêm test Statement khớp, lệch, thiếu `VoucherNo`/`Amount` và Ringi lớn hơn 110%.
- [ ] Chạy test mới để xác nhận thất bại với code hiện tại.
- [ ] Bổ sung xử lý Statement và giới hạn Ringi tùy chọn.
- [ ] Chạy toàn bộ `tests.test_nvl_rule_engine`.

### Task 2: SQL Configuration And Prompt

**Files:**
- Modify: `scripts/sql/0_bemt2009.sql`
- Modify: `scripts/sql/3_add_nvl_amount_rule.sql`
- Create: `scripts/sql/5_sync_nvl_amount_statement_ringi_rule.sql`
- Modify: `Prompt_AI_BEM_v11/WareHouse/Prompt_WareHouse_Amount.sql`

**Interfaces:**
- Consumes: bảng `dbo.BEMT2009`, prompt `ONT1042` của `CRITERIA_AMOUNT`.
- Produces: 5 mapping amount, gồm `STATEMENT.Amount`, và rule params mới.

- [ ] Bổ sung mapping Statement và cập nhật validation row count.
- [ ] Cập nhật prompt với nhãn `Số hóa đơn`/`Số tiền` cho Statement và quy tắc Ringi mới.
- [ ] Chạy migration và prompt trên `MEIKO2026_T`.
- [ ] Xác minh DB có 5 mapping amount và runtime load được params mới.

### Task 3: Final Verification

**Files:**
- Test: `tests/test_nvl_rule_engine.py`

**Interfaces:**
- Consumes: code và cấu hình DB sau migration.
- Produces: bằng chứng test và kiểm tra tích hợp DB.

- [ ] Chạy test NVL và test SQL liên quan.
- [ ] Chạy `pip check`.
- [ ] Chạy các case tích hợp bằng cấu hình load trực tiếp từ DB.
- [ ] Kiểm tra diff chỉ chứa thay đổi tiêu chí Số tiền và tài liệu triển khai.
