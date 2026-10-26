# NVL Amount Statement And Ringi Design

## Scope

- Chỉ sửa tiêu chí `CRITERIA_AMOUNT` của bộ Nguyên vật liệu.
- Không sửa tiêu chí Chữ ký, con dấu và không thay đổi các tiêu chí NVL khác.

## Statement Amount

- Prompt phải truyền `STATEMENT.VoucherNo` với nhãn `Số hóa đơn` và `STATEMENT.Amount` với nhãn `Số tiền`.
- `STATEMENT` là chứng từ tùy chọn. Khi không có `STATEMENT`, luồng Số tiền hiện tại giữ nguyên.
- Khi có `STATEMENT`, từng bảng kê phải có cả `VoucherNo` và `Amount`; thiếu dữ liệu trả `REVIEW` và chỉ liệt kê file thiếu dữ liệu.
- `STATEMENT.Amount` phải khớp tổng số tiền của một trong hai nhóm `INVOICE` hoặc `COMMERCIALINVOICE` có số hóa đơn tương ứng, với sai số hiện tại là `10`.
- Không yêu cầu tổng `STATEMENT.Amount` phải khớp tổng tiền ĐNTT.

## Ringi Amount

- Đối chiếu theo từng `RingiNo` khi có đủ số Ringi.
- Tổng tiền Ringi phải lớn hơn hoặc bằng tổng tiền ĐNTT cùng `RingiNo`.
- Không còn giới hạn tối đa 110%.
- Nếu không có số Ringi để chia nhóm, áp dụng cùng quy tắc cho tổng Ringi và tổng ĐNTT.

## Configuration

- Bổ sung mapping `STATEMENT.Amount` vào nhóm `NVL_SO_TIEN_V1` trong `BEMT2009`.
- Cập nhật `CompareParams` để dùng `ringiMinRatio=1`, `ringiMaxRatio=NONE` và khai báo trường Statement.
- Cập nhật seed SQL, script amount hiện có và thêm migration idempotent dành cho DB đã triển khai.

## Verification

- Test Statement khớp, lệch tiền, thiếu tiền và thiếu số hóa đơn.
- Test Ringi bằng, lớn hơn và nhỏ hơn tổng ĐNTT.
- Chạy toàn bộ test NVL Rule Engine.
- Chạy migration và prompt trên `MEIKO2026_T`, sau đó kiểm tra cấu hình được runtime load đúng.
