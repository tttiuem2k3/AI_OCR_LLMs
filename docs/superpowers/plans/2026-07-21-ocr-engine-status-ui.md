# OCR Engine Status UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hiển thị giao diện OCR phù hợp với engine đang chạy mà không thay đổi request hoặc hành vi hiện tại của `POST /ocr`.

**Architecture:** Backend bổ sung endpoint chỉ đọc `GET /ocr/status`, trả engine đã được chọn khi tiến trình khởi động. UI gọi endpoint khi tải trang và khi ping, sau đó chỉ thay đổi badge, mô tả, nhãn nút và trạng thái; việc upload vẫn gửi nguyên `FormData` tới `POST /ocr`.

**Tech Stack:** Flask, HTML, Tailwind CSS CDN, JavaScript thuần.

---

### Task 1: Định nghĩa contract trạng thái OCR

**Files:**
- Modify: `App/main_iis.py:270`

- [ ] Thêm metadata `engine`, `engine_label` dựa trên engine đã chọn lúc startup.
- [ ] Thêm `GET /ocr/status` trả JSON gồm `status`, `ready`, `engine`, `engine_label`, `use_vlm_ocr`.
- [ ] Giữ nguyên `GET /ping` và `POST /ocr`.

### Task 2: Thêm khu vực engine vào OCR UI

**Files:**
- Modify: `UI/index_ocr.html:25`

- [ ] Thêm panel engine với trạng thái mặc định không xác định.
- [ ] Thêm hàm gọi `/ocr/status` khi tải trang và khi ping.
- [ ] Hiển thị nội dung riêng cho `ppstructure_v3` và `paddleocr_vl`.
- [ ] Đổi nhãn nút và trạng thái theo engine nhưng không đổi `FormData` hoặc URL `POST /ocr`.
- [ ] Fallback về giao diện cũ khi endpoint trạng thái lỗi.

### Task 3: Xác minh không hồi quy

**Files:**
- Verify: `App/main_iis.py`
- Verify: `UI/index_ocr.html`

- [ ] Kiểm tra contract endpoint và các ID UI bằng script tự động.
- [ ] Kiểm tra HTML/JavaScript không lỗi cú pháp cơ bản.
- [ ] Mở UI trong browser, xác minh responsive và trạng thái hai engine bằng mock API.
- [ ] Xác nhận payload OCR vẫn chỉ chứa các file như trước.
