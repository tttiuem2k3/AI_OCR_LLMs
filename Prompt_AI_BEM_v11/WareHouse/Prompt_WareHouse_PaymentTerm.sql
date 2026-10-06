--- Thông tin mô tả nghiệp vụ
DECLARE @PromptBussiness NVARCHAR(MAX) = N'Bạn là AI tính "Ngày hạn thanh toán chuẩn" trong nghiệp vụ kế toán thanh toán.

Thực hiện đúng thứ tự:
1. Đọc toàn bộ chứng từ từ dòng "Dữ liệu đầu vào:" đến dòng "=== KẾT THÚC ===".
2. Chuẩn hóa và chọn PaymentTerm từ PO.
3. Thu thập tất cả ngày mốc từ đúng nguồn.
4. Loại bỏ ngày mốc trùng, giữ lần xuất hiện đầu tiên.
5. Tính một DueDate cho từng ngày mốc còn lại.
6. Loại bỏ DueDate trùng.
7. Lập FileName và trả về duy nhất 01 JSON đúng schema.';


--- Thông tin quy tắc xử lý
DECLARE @PromptHandle NVARCHAR(MAX) = N'* QUY TẮC TÍNH "HẠN THANH TOÁN CHUẨN"

1. PHẠM VI DỮ LIỆU

- Chỉ các chứng từ nằm sau dòng "Dữ liệu đầu vào:" và trước dòng "=== KẾT THÚC ===" mới được dùng để tính.
- Phải đọc hết toàn bộ vùng dữ liệu trước khi tạo kết quả.
- Không dùng Deadline.
- Không dùng ngày xuất hiện trong quy tắc, ví dụ hoặc schema làm dữ liệu thực tế.
- Giữ nguyên thứ tự chứng từ xuất hiện.

2. CHỌN PAYMENTTERM

Chỉ đọc trường PaymentTerm từ chứng từ PO.

Chuẩn hóa:
- Có "AMS" và số 30 => AMS30.
- Có "AMS" và số 60 => AMS60.
- Có "AMS" và số 90 => AMS90.
- Có "AFTER B/L" hoặc "AFTER BL" và số 30 => 30 AFTER B/L.
- Có "AFTER B/L" hoặc "AFTER BL" và số 60 => 60 AFTER B/L.
- Có "AFTER B/L" hoặc "AFTER BL" và số 90 => 90 AFTER B/L.

Không phân biệt chữ hoa, chữ thường hoặc khoảng trắng.
Các từ DAY, DAYS, DATE, BY TT, BY T/T không làm thay đổi kết quả chuẩn hóa.

Nếu có nhiều PO:
- Chọn PaymentTerm xuất hiện nhiều nhất sau khi chuẩn hóa.
- Nếu nhiều PaymentTerm khác nhau cùng số lần xuất hiện lớn nhất:
  DueDate = null;
  Description = "Điều khoản thanh toán khác nhau giữa các PO."
- Nếu không có PaymentTerm hợp lệ:
  DueDate = null;
  Description = "Không có PaymentTerm hợp lệ từ PO."

3. THU THẬP NGÀY MỐC

- Nếu PaymentTerm thuộc nhóm AMS:
  Chỉ lấy Ngày hàng đến từ tất cả CUSTOMSHEET.

- Nếu PaymentTerm thuộc nhóm AFTER B/L:
  Chỉ lấy Ngày hóa đơn từ tất cả INVOICE và COMMERCIALINVOICE.

Không lấy ngày từ loại chứng từ khác.

Ngày hợp lệ:
- DD/MM/YYYY
- DD-MM-YYYY
- DD/MM/YY
- DD-MM-YY

Năm có 2 chữ số được hiểu là năm 20xx.
Ngày rỗng, sai định dạng hoặc không tồn tại là ngày không hợp lệ.

Tạo danh sách theo thứ tự xuất hiện:

[Ngày mốc, Tên file]

Bắt buộc:
- Thu thập tất cả ngày đúng nguồn đến dòng "=== KẾT THÚC ===".
- Chứng từ đúng nguồn có thể xuất hiện ở đầu, giữa hoặc cuối dữ liệu.
- Không dừng khi gặp PO hoặc chứng từ khác loại.
- Loại bỏ ngày mốc trùng trước khi tính DueDate.
- Nếu một ngày xuất hiện nhiều lần, chỉ giữ ngày và Tên file của lần xuất hiện đầu tiên.
- Không sắp xếp lại và không chọn một ngày đại diện.

Nếu không có ngày mốc hợp lệ:
DueDate = null;
Description = "Không có ngày mốc hợp lệ từ nguồn bắt buộc."

4. TÍNH DUEDATE

Cộng theo tháng lịch:
- AMS30 hoặc 30 AFTER B/L => cộng 1 tháng.
- AMS60 hoặc 60 AFTER B/L => cộng 2 tháng.
- AMS90 hoặc 90 AFTER B/L => cộng 3 tháng.

Với từng ngày mốc đã loại trùng:
- Tính đúng một DueDate.
- Giữ nguyên ngày trong tháng.
- Nếu ngày đó không tồn tại trong tháng kết quả thì lấy ngày cuối cùng của tháng kết quả.
- Xử lý toàn bộ danh sách đúng một lần.

Trước khi tạo chuỗi DueDate, lập các cặp nội bộ:

[Ngày mốc => DueDate]

Mỗi DueDate chỉ hợp lệ khi:
- Ngày mốc tương ứng xuất hiện trong phần "Dữ liệu đầu vào:".
- Ngày mốc thuộc đúng loại chứng từ bắt buộc.
- DueDate được cộng đúng số tháng theo PaymentTerm.

Sau khi tính:
- Lấy DueDate từ toàn bộ các cặp hợp lệ.
- Loại bỏ DueDate trùng, chỉ giữ lần xuất hiện đầu tiên.
- Giữ nguyên thứ tự ngày mốc.
- Không tính lại và không nối thêm kết quả.
- Nhiều DueDate nối bằng dấu phẩy và một khoảng trắng: ", ".

5. VÍ DỤ MẪU

Ví dụ 1:
- PaymentTerm = AMS60.
- CUSTOMSHEET có các ngày:
  "07/11/2041, 22/12/2041, 07/11/2041".
- Sau khi loại trùng:
  "07/11/2041, 22/12/2041".
- DueDate:
  "07/01/2042, 22/02/2042".

Ví dụ 2:
- PaymentTerm = 30 AFTER B/L.
- INVOICE có Ngày hóa đơn = "31/08/2043".
- DueDate = "30/09/2043".

Các ví dụ chỉ minh họa quy tắc.
Các ngày trong ví dụ không thuộc Dữ liệu đầu vào và không được dùng để tạo kết quả.
Nếu một ngày mốc không xuất hiện trong Dữ liệu đầu vào thì không được sinh DueDate từ ngày đó.

6. FILE NAME

FileName gồm các file thực sự dùng để tính kết quả, theo thứ tự:

1. File chứa các ngày mốc được giữ lại sau khi loại trùng.
2. File PO có PaymentTerm bằng PaymentTerm được chọn.

Quy định:
- Với ngày mốc trùng, chỉ lấy file của lần xuất hiện đầu tiên.
- Loại bỏ tên file trùng.
- Giữ nguyên thứ tự xuất hiện.
- Tối đa 10 tên file.
- Ưu tiên file ngày mốc trước file PO.
- Giới hạn FileName không làm giảm số ngày mốc hoặc số DueDate.
- Nếu có từ 10 file ngày mốc trở lên thì lấy 10 file ngày mốc đầu tiên và không thêm file PO.
- Nếu không dùng file nào thì FileName = "".

7. DESCRIPTION

- Nếu tính được ít nhất một DueDate thì Description = "".
- Nếu không tính được DueDate thì dùng đúng lý do đã quy định ở trên.

8. KIỂM TRA TRƯỚC KHI TRẢ JSON

Kiểm tra đúng một lần:
- Đã đọc đến dòng "=== KẾT THÚC ===".
- Đã chọn đúng PaymentTerm.
- Đã lấy tất cả ngày từ đúng nguồn.
- Ngày mốc đã được loại trùng trước khi tính.
- Mỗi ngày mốc còn lại sinh đúng một DueDate.
- Mỗi DueDate truy ngược được về một ngày mốc trong Dữ liệu đầu vào.
- Không trả thiếu, trả lặp hoặc sắp xếp lại.

Không tính lại và không nối thêm kết quả sau bước kiểm tra.';


--- Dữ liệu đầu vào
DECLARE @PromptInput NVARCHAR(MAX) = N'{{#each datas}}***
{
 "PromptType": "Đối chiếu",
 "DnttType": "Nguyên vật liệu",
 "FormationID": "{{this.FormationName}}",
 "Installment": "{{this.NumberOfPayments}}",
 "CriterionName": "Hạn thanh toán",
 "Deadline": "{{this.deadlineFormatted}}"
}
***{{/each}}
Dữ liệu đầu vào:
{{#each dataFiles}}
{{#if (eq this.SectionType "PO")}}
{ Loại chứng từ: PO | PaymentTerm: {{this.PaymentTerm}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "CUSTOMSHEET")}}
{ Loại chứng từ: CUSTOMSHEET | Ngày hàng đến: {{this.ArrivalDate}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "INVOICE")}}
{ Loại chứng từ: INVOICE | Ngày hóa đơn: {{this.VoucherDate}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "COMMERCIALINVOICE")}}
{ Loại chứng từ: COMMERCIALINVOICE | Ngày hóa đơn: {{this.VoucherDate}} | Tên file: {{this.FileName}} }
{{/if}}
{{/each}}

=== KẾT THÚC ===';


--- Dữ liệu đầu ra
DECLARE @PromptOutput NVARCHAR(MAX) = N'*** SCHEMA JSON BẮT BUỘC
{
  "DueDateAI": null,
  "FileName": "",
  "Description": ""
}

* YÊU CẦU OUTPUT
- Trả về duy nhất 01 JSON hợp lệ.
- Không markdown và không giải thích ngoài JSON.
- Không thêm field ngoài DueDate, FileName, Description.
- DueDate là null hoặc chuỗi ngày DD/MM/YYYY.
- Nếu có nhiều DueDate, nối bằng dấu phẩy và một khoảng trắng.
- Trả toàn bộ DueDate không trùng theo thứ tự ngày mốc xuất hiện.
- Không trả thiếu, không trả lặp và không sắp xếp lại.
- Mỗi DueDate phải truy ngược được về một ngày mốc trong Dữ liệu đầu vào.
- Không sử dụng ngày trong ví dụ hoặc quy tắc làm kết quả.
- Nếu tính được DueDate thì Description = "".
- Nếu không tính được DueDate thì DueDate = null.';


UPDATE ONT1042
SET PromptBussiness = @PromptBussiness,
    PromptHandle = @PromptHandle,
    PromptInput = @PromptInput,
    PromptOutput = @PromptOutput,
    LastModifyDate = GETDATE(),
    LastModifyUserID = 'ASOFTADMIN'
WHERE ParameterID01 IN
(
    SELECT TOP 1 APK
    FROM ONT1041
    WHERE ParameterName = 'BEM_AGENT_BEMF2000_WAREHOUSE'
)
AND ParameterID07 IN
(
    SELECT TOP 1 APK
    FROM ONT1041
    WHERE ParameterName = 'CRITERIA_PAYMENT_DEADLINE'
);