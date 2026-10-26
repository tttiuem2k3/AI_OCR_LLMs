# AI Python Service Error Response Implementation Plan

**Goal:** Giữ nguyên request/response body hiện có của OCR và LLM, nhưng trả HTTP status đúng cho lỗi service/model để Hangfire API-AI retry đúng job.

**Constraints:**
- OCR thành công vẫn trả text/plain như hiện tại; lỗi OCR vẫn trả JSON detail như hiện tại.
- LLM thành công và lỗi vẫn giữ wrapper text chứa JSON string.
- Không thêm field bắt buộc vào request từ API-AI.
- Không thay đổi quyết định nghiệp vụ OK/NG/REVIEW và không coi sections rỗng là lỗi service.

## Tasks

- [x] Viết test phân loại lỗi service: OOM -> 503, timeout -> 504, connection/model unavailable -> 503, lỗi runtime khác -> 500.
- [x] Tạo helper dùng chung cho OCR/LLM để phân loại lỗi nhưng không thay đổi format response.
- [x] Cập nhật /ocr: engine chưa sẵn sàng, OCR infer, lưu kết quả và batch runtime đều trả lỗi rõ; giữ nguyên xử lý PDF dữ liệu lỗi hiện tại.
- [x] Cập nhật /llms/api/ai_llms_models: LLM chưa sẵn sàng/OOM/timeout/lỗi runtime trả HTTP status đúng với wrapper cũ.
- [x] Chạy unit test hiện có và test mới.
