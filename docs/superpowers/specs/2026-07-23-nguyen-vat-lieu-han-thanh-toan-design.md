# Thiết kế xử lý Hạn thanh toán Nguyên vật liệu bằng Python

## Mục tiêu

Thay phần gọi LLM để xác định `DueDate` bằng logic Python xác định, chỉ trong nhánh:

- `PromptType = Đối chiếu`
- `DnttType = Nguyên vật liệu`
- `CriterionName = Hạn thanh toán`

Mọi nhánh và tiêu chí khác giữ nguyên hành vi hiện tại.

## Đầu vào cố định

Sau block directive `***...***`, dữ liệu chứng từ luôn gồm các block độc lập dạng `{ ... }`. Các trường trong block được phân cách bằng ký tự `|`; thứ tự các block có thể xen kẽ.

```text
{ Loại chứng từ: PO | PaymentTerm: ... | Tên file: ... }
{ Loại chứng từ: CUSTOMSHEET | Ngày hoàn thành kiểm tra: ... | Tên file: ... }
{ Loại chứng từ: INVOICE | Ngày hóa đơn: ... | Tên file: ... }
{ Loại chứng từ: COMMERCIALINVOICE | Ngày hóa đơn: ... | Tên file: ... }
```

Không xây dựng parser OCR tổng quát ngoài cấu trúc cố định này.

## Phạm vi tích hợp

Logic mới chạy trong `process_ai_llms_models_rules`, sau khi directive và nội dung prompt đã được tách, nhưng trước bước gọi `generate_with_trim_fn`.

Khi đúng ba điều kiện phạm vi, hàm Python tạo object trung gian root-level gồm `DueDate`, `FileName` và `Description`. Object này được chuyển vào `_build_payment_deadline_result` để giữ nguyên chuẩn hóa ngày nghỉ, đối chiếu `Deadline`, schema `criteria`, logging và dọn CUDA hiện tại.

Nhánh này không gọi LLM, kể cả khi dữ liệu không hợp lệ hoặc không đầy đủ.

## Phân tích chứng từ

1. Tách tất cả nội dung nằm trong cặp `{` và `}`.
2. Tách từng block theo `|`.
3. Tách mỗi trường tại dấu `:` đầu tiên.
4. Chuẩn hóa tên trường bằng `_norm_key` và loại chứng từ bằng `_normalize_doc_type`.
5. Giữ thứ tự xuất hiện ban đầu để danh sách tên file ổn định.

## Chuẩn hóa PaymentTerm

Chuyển `PaymentTerm` sang chữ hoa và chuẩn hóa khoảng trắng.

- `AMS`: nhận các dạng `AMS 90`, `AMS90`, `AMS 90 DAYS BY TT`.
- `AFTER_BL`: nhận các dạng `90 AFTER B/L`, `90 AFTER BL`, `90 DAY AFTER BL`, `90 DAYS AFTER B/L`.

Khóa đếm là `(loại điều khoản, số ngày)`. `AMS 90` và `AMS90` là cùng điều khoản; `AMS 90` và `AMS 60` là hai điều khoản khác nhau.

PO không nhận diện được loại hoặc không có số ngày nguyên dương bị bỏ qua.

## Chọn điều khoản đa số

Đếm từng khóa hợp lệ và chọn khóa có số lượng lớn nhất. Nếu nhiều khóa đồng hạng, trả `DueDate: null`, mô tả `Có nhiều điều khoản thanh toán khác nhau`, cùng tối đa 10 tên PO thuộc các nhóm đồng hạng; tên file không trùng và giữ thứ tự đầu vào.

Nếu không có PaymentTerm hợp lệ, trả `DueDate: null`, `FileName` là chuỗi rỗng và mô tả không tìm thấy điều khoản AMS hoặc AFTER B/L hợp lệ.

## Tính DueDate

### AMS

Lấy `Ngày hoàn thành kiểm tra` từ mọi `CUSTOMSHEET`, bỏ ngày rỗng/null/sai định dạng, rồi cộng số ngày của điều khoản.

Nếu không có ngày hợp lệ, trả `DueDate: null` và mô tả không tìm thấy `Ngày hoàn thành kiểm tra` hợp lệ của `CUSTOMSHEET`.

### AFTER B/L

Lấy `Ngày hóa đơn` từ mọi `INVOICE` và `COMMERCIALINVOICE`, bỏ ngày rỗng/null/sai định dạng, rồi cộng số ngày của điều khoản.

Nếu không có ngày hợp lệ, trả `DueDate: null` và mô tả không tìm thấy `Ngày hóa đơn` hợp lệ của `INVOICE` hoặc `COMMERCIALINVOICE`.

### Danh sách kết quả

- Loại DueDate trùng nhau.
- Giữ thứ tự ngày mốc xuất hiện trong dữ liệu đầu vào.
- Định dạng `dd/mm/yyyy`.
- Nối nhiều ngày bằng `, `.
- Khi thành công, `FileName` và `Description` là chuỗi rỗng.

## Xử lý lỗi

Lỗi dữ liệu nghiệp vụ được biểu diễn bằng object có `DueDate: null` và mô tả cụ thể, sau đó `_build_payment_deadline_result` chuyển thành `CriteriaStatus = NG`. Không fallback sang LLM.

## Kiểm thử

Kiểm thử đơn vị bao phủ:

1. AMS với nhiều ngày, loại trùng và sắp xếp.
2. Các biến thể AMS được gom đúng.
3. AFTER B/L đọc cả INVOICE và COMMERCIALINVOICE.
4. PaymentTerm không hợp lệ bị bỏ qua.
5. Đồng hạng trả lỗi và tối đa 10 tên PO.
6. Không có PaymentTerm hợp lệ trả lỗi.
7. Thiếu ngày mốc AMS trả lỗi.
8. Thiếu ngày mốc AFTER B/L trả lỗi.
9. Đúng phạm vi thì callback LLM không được gọi.
10. Ngoài phạm vi tiếp tục dùng luồng cũ.

## Ngoài phạm vi

- Không thay đổi cấu trúc prompt user.
- Không áp dụng cho DnttType ngoài `Nguyên vật liệu`.
- Không áp dụng cho tiêu chí ngoài `Hạn thanh toán`.
- Không thay đổi nhánh `Trích xuất`.
- Không thay đổi quy tắc ngày nghỉ hoặc schema API cuối cùng.
