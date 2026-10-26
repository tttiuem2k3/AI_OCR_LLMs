# Adaptive Unwarping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chỉ bật PPStructureV3 document unwarping khi góc nghiêng còn lại của trang lớn hơn 10 độ, không thêm cấu hình hoặc file code mới và giữ chi phí tiền xử lý thấp.

**Architecture:** Bổ sung bộ ước lượng góc nhanh bằng OpenCV vào `orientation.py`, chạy trên ảnh thu nhỏ và dùng weighted median của các đường ngang dài. `ocr_engine_iis.py` phân nhóm trang theo quyết định unwarping rồi gọi pipeline tối đa hai lần, giữ nguyên thứ tự kết quả và fallback về hành vi cũ nếu phân tích hoặc override tham số thất bại.

**Tech Stack:** Python, NumPy, OpenCV, PPStructureV3.

## Global Constraints

- Không sửa `App/settings_all.py`.
- Không tạo thêm file code hoặc file test trong repo.
- Chỉ sửa `App/OCR_BE/orientation.py` và `App/OCR_BE/ocr_engine_iis.py`.
- Ngưỡng bật unwarping được cố định ở 10 độ.
- Nếu không xác định được góc hoặc có lỗi, giữ hành vi cũ `use_doc_unwarping=True`.
- Không chạy OCR cục bộ; kiểm thử bằng ảnh tổng hợp và fake pipeline.

---

### Task 1: Fast skew estimator

**Files:**
- Modify: `App/OCR_BE/orientation.py`

**Interfaces:**
- Produces: `estimate_skew_angle_fast(image: np.ndarray) -> float | None`
- Produces: `should_use_doc_unwarping(image: np.ndarray, threshold_degrees: float = 10.0) -> tuple[bool, float | None]`

- [ ] Viết test tạm thời bằng ảnh đường ngang tổng hợp cho góc 0, 8 và 14 độ; xác nhận test fail vì hàm chưa tồn tại.
- [ ] Cài đặt resize tối đa 800 px, threshold/morphology, HoughLinesP và weighted median.
- [ ] Lọc đường ngắn, đường gần dọc và kết quả không nhất quán; trả `None` khi không đủ tin cậy.
- [ ] Chạy lại test: 0 và 8 độ không unwarp, 14 độ unwarp, ảnh trống fallback unwarp.

### Task 2: Adaptive grouped prediction

**Files:**
- Modify: `App/OCR_BE/ocr_engine_iis.py`

**Interfaces:**
- Consumes: `should_use_doc_unwarping`
- Produces: `_predict_pages_adaptive_unwarping(pipeline, images, logger) -> list`

- [ ] Viết fake-pipeline test tạm thời; xác nhận fail vì helper chưa tồn tại.
- [ ] Phân loại từng trang nhưng gom thành tối đa hai batch `False` và `True` để giữ tốc độ.
- [ ] Khôi phục đúng thứ tự trang sau hai batch.
- [ ] Tích hợp helper trước bước chuyển kết quả sang TXT.
- [ ] Nếu adaptive path lỗi, log warning và gọi lại luồng cũ không truyền override.
- [ ] Chạy fake-pipeline test và `py_compile` cho hai file.

### Task 3: Regression verification

**Files:**
- Verify only: `App/OCR_BE/orientation.py`
- Verify only: `App/OCR_BE/ocr_engine_iis.py`

- [ ] Kiểm tra diff chỉ có hai file production đã duyệt và plan document.
- [ ] Chạy lại toàn bộ test tổng hợp/fake pipeline.
- [ ] Xác nhận không sửa settings, formatter, rule engine hoặc API.
- [ ] Ghi rõ OCR thực tế cần được xác nhận trên máy chủ AI với PO 354, PO 364 và ít nhất một ảnh nghiêng trên 10 độ.
