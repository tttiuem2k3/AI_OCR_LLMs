# Đồng bộ ba tiêu chí NVL với yêu cầu mới

## Phạm vi

Chỉ cập nhật ba tiêu chí của bộ Nguyên vật liệu:

- Ngày hóa đơn.
- Loại tiền.
- Điều kiện giao hàng.

Không thay đổi Tên nhà cung cấp, Số hóa đơn, Số tiền, Deadline thanh toán, Ngày hoàn thành kiểm tra hoặc Chữ ký/con dấu.

## Thiết kế

### Ngày hóa đơn

- Bổ sung Packing list vào dữ liệu đối chiếu.
- Dùng Số Packing list làm khóa ghép nhóm và Ngày Packing list làm ngày đối chiếu.
- Ngày giữa các chứng từ cùng nhóm phải khớp tuyệt đối; không cho phép chênh lệch một ngày.
- Prompt chỉ dùng tên nghiệp vụ như "Số Packing list" và "Ngày Packing list" trong phần hướng dẫn.

### Loại tiền

- Bổ sung Loại tiền trên Ringi vào dữ liệu đối chiếu.
- Loại tiền trên Ringi phải khớp Loại tiền trên ĐNTT.
- Không bổ sung Packing list vào tiêu chí này.

### Điều kiện giao hàng

- Chỉ dùng Tờ khai hải quan, PO và Hóa đơn thương mại.
- Loại bỏ hóa đơn VAT/INVOICE khỏi prompt và cấu hình Rule Engine.
- Không bổ sung Packing list.

## Đồng bộ triển khai

- Cập nhật prompt nguồn SQL.
- Cập nhật seed `BEMT2009`.
- Tạo script đồng bộ tăng dần để chạy trên DB hiện hữu.
- Chạy script trên DB hiện tại và cập nhật các prompt tương ứng trong `ONT1042`.
- Bổ sung test runtime và test kiểm tra nội dung prompt/script.

## Quy tắc viết prompt

- Phần mô tả nghiệp vụ không viết tên kỹ thuật dạng `PACKINGLIST.PackingListDate` hoặc `RINGI.Currency`.
- Template Handlebars vẫn giữ tên field kỹ thuật như `{{this.PackingListDate}}` vì đây là cú pháp lấy dữ liệu, không phải nội dung hướng dẫn nghiệp vụ.
