# Thiết kế Rule Engine NVL: Đặt cọc/Trả trước và STATEMENT

## Mục tiêu

Mở rộng Rules Engine cho ĐNTT Nguyên vật liệu (NGUYENVATLIEU) để bỏ qua đúng các tiêu chí phụ thuộc hóa đơn/tờ khai khi Đặt cọc/Trả trước, và đối chiếu Số hóa đơn theo chuỗi chứng từ có hoặc không có bảng kê hóa đơn thương mại (STATEMENT).

## Dữ liệu đầu vào

ONT1041 đã được bổ sung:

- ParameterID: FieldID30
- ParameterName: ListNo
- DisplayName: Số bảng kê

Mỗi STATEMENT là một detail, tách theo ListNo. VoucherNo chứa các số hóa đơn chi tiết, phân tách bằng dấu phẩy, ví dụ A123, B456, C678. Engine phải tách danh sách, bỏ khoảng trắng, phần tử rỗng và giá trị trùng sau chuẩn hóa.

## Đặt cọc/Trả trước

Áp dụng khi DnttType là NGUYENVATLIEU và FormationID chuẩn hóa là DATCOC_TRATRUOC.

Các tiêu chí được bỏ qua: SOHOADON, NGAYHOADON, NGAYHOANTHANHKIEMTRA, HANTHANHTOAN.

Mỗi tiêu chí skip trả:

    CriteriaStatus: OK
    FileName: ""
    Description: "Với nguồn hình thành Đặt cọc/Trả trước, tiêu chí này được bỏ qua khi đối chiếu."

Các tiêu chí khác vẫn chạy theo rule hiện hành. Việc skip phải xảy ra trước loader BEMT2009 và các nhánh Python đặc biệt.

## Quy tắc Số hóa đơn

Chuẩn hóa giữ theo engine hiện tại: bỏ khoảng trắng, dấu -, ., / và chấp nhận OCR O/0, I/1.

### Không có STATEMENT

Chạy hai nhánh độc lập:

1. Nội địa: DNTT.InvoiceNo -> INVOICE.VoucherNo -> CUSTOMSHEET.VoucherNo.
2. Nước ngoài: DNTT.InvoiceNo -> COMMERCIALINVOICE.VoucherNo -> CUSTOMSHEET.VoucherNo.

Nhánh đạt khi toàn bộ số trên DNTT khớp chứng từ hóa đơn của nhánh và số hóa đơn của nhánh khớp tờ khai. Có cả INVOICE và COMMERCIALINVOICE thì chạy cả hai; chỉ cần một nhánh hoàn chỉnh đạt là OK.

### Có STATEMENT

Chạy hai nhánh độc lập:

1. Nội địa: DNTT.InvoiceNo -> INVOICE.VoucherNo; INVOICE.VoucherNo phải nằm trong STATEMENT.VoucherNo; STATEMENT.ListNo phải khớp CUSTOMSHEET.VoucherNo.
2. Nước ngoài: DNTT.InvoiceNo -> COMMERCIALINVOICE.VoucherNo; COMMERCIALINVOICE.VoucherNo phải nằm trong STATEMENT.VoucherNo; STATEMENT.ListNo phải khớp CUSTOMSHEET.VoucherNo.

Nếu có nhiều STATEMENT, một nhánh đạt khi tồn tại ít nhất một STATEMENT đồng thời thỏa danh sách hóa đơn chi tiết và số bảng kê/tờ khai. Nếu một nhánh thiếu/sai nhưng nhánh còn lại hoàn chỉnh và đạt, kết quả chung là OK.

## Trạng thái

- OK: ít nhất một nhánh hoàn chỉnh đạt, hoặc tiêu chí được skip.
- BLANK: không có nhánh nào có đủ dữ liệu bắt buộc.
- NG: có nhánh đủ dữ liệu để kiểm tra nhưng mọi nhánh đủ dữ liệu đều không khớp.

FileName chỉ ghi file liên quan đến nguyên nhân BLANK/NG; OK để rỗng.

## BEMT2009 và phạm vi

Giữ CompareMode NVL_INVOICE_NO_MATCH. Mapping phải nhận diện DNTT.InvoiceNo, INVOICE.VoucherNo, COMMERCIALINVOICE.VoucherNo, CUSTOMSHEET.VoucherNo, STATEMENT.VoucherNo và STATEMENT.ListNo.

Quan hệ STATEMENT.ListNo -> CUSTOMSHEET.VoucherNo là evidence-to-evidence nên được thực thi trong thuật toán NVL_INVOICE_NO_MATCH. Python đọc tên field từ Mapping/field code ổn định; không route bằng nhãn tiếng Việt. CompareParams bổ sung mặc định tương thích ngược: statementType=STATEMENT, statementKeyField=ListNo, statementInvoiceField=VoucherNo, branchPolicy=ANY_COMPLETE_BRANCH_OK.

Không thay đổi response schema, loại ĐNTT khác, hay prompt Prompt_ReadFile_1.sql mà người dùng đã cập nhật. RULE_ENGINE không gọi LLM; AUTO chỉ fallback theo LLMPolicy.

## Kiểm thử bắt buộc

1. Bốn tiêu chí skip Đặt cọc/Trả trước trả OK và đúng Description.
2. Tiêu chí không skip vẫn chạy rule.
3. Không có STATEMENT: INVOICE đạt; COMMERCIALINVOICE đạt; một nhánh sai nhưng nhánh còn lại đạt vẫn OK.
4. Có STATEMENT: chuỗi DNTT -> hóa đơn -> STATEMENT.VoucherNo và STATEMENT.ListNo -> CUSTOMSHEET đạt thì OK.
5. Có STATEMENT: hóa đơn không thuộc danh sách hoặc ListNo không khớp tờ khai thì NG.
6. Có STATEMENT: thiếu ListNo hoặc VoucherNo thì BLANK khi không có nhánh khác đạt.
7. VoucherNo dạng danh sách có khoảng trắng và giá trị trùng vẫn được parse đúng.
