# NVL FileName Filtering Design

## Mục tiêu

Đảm bảo `criteria.FileName` của Rules Engine bộ Nguyên vật liệu chỉ chứa tên file thực sự thiếu dữ liệu hoặc tham gia trực tiếp vào sai lệch. Không thay đổi cách xác định `CriteriaStatus` (`OK`, `NG`, `REVIEW`) và không thay đổi ngưỡng hay quy tắc nghiệp vụ hiện tại.

## Phạm vi

- `Số hóa đơn`: loại file hóa đơn/tờ khai đã khớp khỏi nhánh NG một phần; nhánh có `STATEMENT` chỉ giữ bảng kê và tờ khai không ghép được.
- `Chữ ký và con dấu`: lọc theo từng file có `INVALID` hoặc `BLANK`, thay vì lấy toàn bộ file cùng loại chứng từ.
- `Số tiền`: khi tổng theo loại chứng từ lệch, ưu tiên xác định file lệch theo số hóa đơn; nếu không xác định chắc chắn file cụ thể thì không liệt kê file đã khớp.
- Giữ nguyên schema response và nội dung kết luận nghiệp vụ.

## Thiết kế

1. Tạo các danh sách file lỗi trực tiếp từ document/entry thay vì suy ra từ toàn bộ loại chứng từ.
2. Với đối chiếu số hóa đơn, một file được coi là lỗi khi các số hóa đơn của file không khớp tập số tham chiếu tương ứng. File đã có ít nhất dữ liệu khớp không bị đưa vào chỉ vì file khác cùng nhánh bị lỗi.
3. Với chuỗi `INVOICE -> STATEMENT -> CUSTOMSHEET`, xác định độc lập bảng kê không có `ListNo` khớp tờ khai và tờ khai không có giá trị khớp bất kỳ `ListNo` hợp lệ.
4. Với số tiền, dùng số hóa đơn để xác định document lệch. Nếu chỉ phát hiện lệch tổng nhưng không thể quy trách nhiệm chắc chắn cho document cụ thể, trả `FileName` rỗng thay vì liệt kê toàn bộ file.

## Kiểm thử

- Tờ khai đã khớp như `108590490150` không xuất hiện trong `FileName`.
- Hóa đơn đã khớp không xuất hiện khi một hóa đơn khác trong cùng nhánh bị lệch.
- Tờ khai đã ghép được với `STATEMENT.ListNo` không xuất hiện khi chuỗi khác bị lệch.
- File chữ ký `VALID` không xuất hiện cùng file `INVALID`.
- File số tiền khớp không xuất hiện khi file khác cùng loại bị lệch tổng.
- Toàn bộ test NVL hiện có tiếp tục đạt.
