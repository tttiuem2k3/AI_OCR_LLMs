# LLM Compare CriteriaStatus Validation Design

## Mục tiêu

Đảm bảo kết quả đối chiếu do LLM tạo ra chỉ trả `CriteriaStatus` thuộc một trong ba giá trị nghiệp vụ: `OK`, `NG`, `REVIEW`.

## Phạm vi

- Chỉ chuẩn hóa kết quả của nhánh `PromptType=Đối chiếu` có gọi LLM.
- Không thay đổi kết quả được tạo trực tiếp bởi Rules Engine.
- Không thay đổi schema response hiện tại.

## Quy tắc chuẩn hóa

1. Lấy `criteria.CriteriaStatus`, loại bỏ khoảng trắng và chuyển thành chữ hoa.
2. Giữ nguyên nếu giá trị sau chuẩn hóa là `OK`, `NG` hoặc `REVIEW`.
3. Chuyển thành `REVIEW` nếu field bị thiếu, rỗng hoặc chứa giá trị khác như `PASS`, `FAIL`, `BLANK`.
4. Giữ nguyên các field khác trong response của LLM.

## Điểm áp dụng

- JSON LLM được trả trực tiếp khi đã đủ chứng từ.
- JSON LLM được dùng để dựng response khi thiếu nhóm chứng từ hoặc thiếu chứng từ bắt buộc.

## Kiểm thử

- Giữ nguyên `OK`, `NG`, `REVIEW`.
- Chuẩn hóa chữ thường và khoảng trắng, ví dụ ` review ` thành `REVIEW`.
- Chuyển giá trị lạ, chuỗi rỗng và field bị thiếu thành `REVIEW`.
- Xác nhận các field `CriteriaName`, `FileName`, `Description` không bị thay đổi.
