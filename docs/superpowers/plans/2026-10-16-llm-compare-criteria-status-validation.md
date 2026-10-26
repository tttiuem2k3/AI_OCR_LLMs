# LLM Compare CriteriaStatus Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ràng buộc mọi `CriteriaStatus` do nhánh đối chiếu LLM trả về chỉ còn `OK`, `NG` hoặc `REVIEW`.

**Architecture:** Thêm một helper thuần để chuẩn hóa `criteria.CriteriaStatus` trên JSON đã parse, sau đó gọi helper tại các điểm trả kết quả LLM trong luồng đối chiếu. Rules Engine và nhánh trích xuất không thay đổi.

**Tech Stack:** Python 3, `unittest`, JSON response hiện có.

## Global Constraints

- Giá trị hợp lệ duy nhất: `OK`, `NG`, `REVIEW`.
- Loại bỏ khoảng trắng và chuyển chữ hoa trước khi kiểm tra.
- Giá trị thiếu, rỗng hoặc ngoài danh sách hợp lệ phải thành `REVIEW`.
- Không sửa prompt người dùng đã chỉnh và không thêm dependency.
- Không tạo commit nếu người dùng chưa yêu cầu.

---

### Task 1: Chuẩn hóa trạng thái đối chiếu LLM

**Files:**
- Modify: `tests/test_rules_ai_bem_meiko_amount_prompt.py`
- Modify: `App/Rules_BE/rules_ai_bem_meiko.py`

**Interfaces:**
- Consumes: JSON LLM dạng `dict` có `criteria.CriteriaStatus`.
- Produces: `_normalize_llm_compare_result_status(result: dict) -> dict` trả bản sao với trạng thái hợp lệ.

- [x] **Step 1: Viết test thất bại cho trạng thái LLM không hợp lệ**

Thêm test tích hợp để LLM trả `CriteriaStatus: "PASS"`; kỳ vọng response là `REVIEW` và các field còn lại không đổi.

- [x] **Step 2: Chạy test để xác nhận RED**

Run: `python -m unittest tests.test_rules_ai_bem_meiko_amount_prompt.AmountComparePromptTests.test_invalid_llm_criteria_status_becomes_review`

Expected: FAIL vì code hiện trả nguyên `PASS`.

- [x] **Step 3: Viết helper và áp dụng vào các điểm trả kết quả LLM Compare**

Helper thực hiện:

```python
LLM_COMPARE_CRITERIA_STATUSES = frozenset({"OK", "NG", "REVIEW"})

def _normalize_llm_compare_result_status(result: dict) -> dict:
    normalized_result = dict(result)
    criteria = normalized_result.get("criteria")
    if not isinstance(criteria, dict):
        return normalized_result
    normalized_criteria = dict(criteria)
    status = str(normalized_criteria.get("CriteriaStatus") or "").strip().upper()
    normalized_criteria["CriteriaStatus"] = status if status in LLM_COMPARE_CRITERIA_STATUSES else "REVIEW"
    normalized_result["criteria"] = normalized_criteria
    return normalized_result
```

Áp dụng sau khi parse JSON LLM ở nhánh đối chiếu có rule và ở fallback LLM khi `PromptType=Đối chiếu`.

- [x] **Step 4: Bổ sung test cho chữ thường, khoảng trắng và field bị thiếu**

Kiểm tra `" review "` thành `REVIEW`, `OK/NG/REVIEW` được giữ, và thiếu `CriteriaStatus` thành `REVIEW`.

- [x] **Step 5: Chạy test tập trung**

Run: `python -m unittest tests.test_rules_ai_bem_meiko_amount_prompt tests.test_review_status_contract`

Expected: tất cả test đạt.

- [x] **Step 6: Chạy kiểm tra hồi quy liên quan**

Run: `python -m unittest tests.test_rules_ai_bem_meiko_amount_prompt tests.test_rules_ai_bem_meiko_delivery_term tests.test_nvl_rule_engine tests.test_review_status_contract`

Expected: test mới đạt; các test cũ ngoài phạm vi nếu còn kỳ vọng `BLANK` phải được báo riêng, không sửa lan sang nghiệp vụ khác.

- [x] **Step 7: Kiểm tra cú pháp và diff**

Run: `python -m py_compile App/Rules_BE/rules_ai_bem_meiko.py`

Run: `git diff --check -- App/Rules_BE/rules_ai_bem_meiko.py tests/test_rules_ai_bem_meiko_amount_prompt.py docs/superpowers/specs/2026-10-16-llm-compare-criteria-status-validation-design.md docs/superpowers/plans/2026-10-16-llm-compare-criteria-status-validation.md`

Expected: exit code `0`.
