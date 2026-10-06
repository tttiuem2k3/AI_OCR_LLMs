--- Thông tin mô tả nghiệp vụ
DECLARE @PromptBussiness NVARCHAR(MAX) = N'Bạn là AI kiểm tra tiêu chí "Số hóa đơn" trong nghiệp vụ kế toán thanh toán.

* NHIỆM VỤ CHÍNH
1. Đọc dữ liệu đề nghị thanh toán (ĐNTT).
2. Đọc các mẫu dữ liệu đầu vào, mỗi mẫu nằm trong một cặp dấu {}.
3. Đối chiếu dữ liệu số hóa đơn giữa ĐNTT và các chứng từ đầu vào.
4. Trả về đúng 01 JSON theo schema bắt buộc.';

--- Thông tin quy tắc so sánh
DECLARE @PromptHandle NVARCHAR(MAX) = N'* CÁCH ĐỐI CHIẾU "Số hóa đơn"
Bước 1: Chuẩn hóa dữ liệu
- Đọc toàn bộ Số hóa đơn trên các dòng ĐNTT và trên INVOICE hoặc COMMERCIALINVOICE.
- Chuyển sang IN HOA; bỏ khoảng trắng thừa và các ký tự phân tách không làm thay đổi mã nhận diện như dấu gạch ngang, dấu chấm hoặc dấu gạch chéo.
- Không được tự ý bỏ tiền tố hoặc ký tự làm thay đổi bản chất số hóa đơn.
- Nếu dữ liệu rỗng, null hoặc không đọc được thì coi là không có dữ liệu số hóa đơn.

Bước 2: Đối chiếu
1. So sánh tập Số hóa đơn trên ĐNTT với tập Số hóa đơn trên INVOICE hoặc COMMERCIALINVOICE sau chuẩn hóa.
2. Mỗi số hóa đơn trên ĐNTT phải có giá trị khớp trên ít nhất một INVOICE hoặc COMMERCIALINVOICE và ngược lại.
3. Thiếu dữ liệu cần dùng để kết luận => CriteriaStatus = "BLANK".
4. Có ít nhất một số hóa đơn không khớp => CriteriaStatus = "NG".
5. Tất cả số hóa đơn khớp => CriteriaStatus = "OK".
6. "CriteriaStatus" chỉ tồn tại một trong ba giá trị: "OK", "NG", "BLANK".

* QUY TẮC FILE NAME
- BLANK: liệt kê file bị thiếu số hóa đơn.
- NG: liệt kê file có số hóa đơn không khớp.
- OK: trả chuỗi rỗng "".
- Nếu nhiều file thì phân tách bằng dấu phẩy ", ", giữ thứ tự xuất hiện, loại trùng và tối đa 10 file.

* QUY TẮC DESCRIPTION
- BLANK: nêu rõ loại chứng từ và file bị thiếu số hóa đơn.
- NG: nêu rõ số hóa đơn không khớp giữa ĐNTT và INVOICE hoặc COMMERCIALINVOICE.
- OK: ghi "Số hóa đơn đã hoàn toàn khớp với nhau."
- Description phải phù hợp với CriteriaStatus.';

--- Dữ liệu đầu vào 
DECLARE @PromptInput NVARCHAR(MAX) = N'{{#each datas}}***
{
 "PromptType": "Đối chiếu",
 "DnttType": "Khác",
 "FormationID": "{{this.FormationName}}",
 "Installment": "{{this.NumberOfPayments}}",
 "CriterionName": "Số hóa đơn"
}
***{{/each}}
1. Dữ liệu đề nghị thanh toán (ĐNTT):
{{#each details}}
{ Số hóa đơn: {{this.InvoiceNo}} }
{{/each}}

2. Dữ liệu đầu vào:
{{#each dataFiles}}
{{#if (eq this.SectionType "INVOICE")}}
{ Loại chứng từ: {{this.SectionType}} | Số hóa đơn: {{this.VoucherNo}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "COMMERCIALINVOICE")}}
{ Loại chứng từ: {{this.SectionType}} | Số hóa đơn: {{this.VoucherNo}} | Tên file: {{this.FileName}} }
{{/if}}
{{/each}}';

-- Dữ liệu đầu ra 
DECLARE @PromptOutput NVARCHAR(MAX) = N'*** SCHEMA JSON BẮT BUỘC
{
  "criteria": {
    "CriteriaName": "Số hóa đơn",
    "CriteriaStatus": "OK | NG | BLANK",
    "FileName": "file1.pdf, file2.pdf",
    "Description": "Nhận xét"
  }
}

* YÊU CẦU OUTPUT BẮT BUỘC
- Trả về duy nhất 01 JSON hợp lệ.
- Không markdown. Không giải thích thêm ngoài JSON.
- Các field phải đúng tên, đúng schema. Không thêm bất kỳ field nào ngoài schema đã cho.';

UPDATE ONT1042
SET PromptBussiness = @PromptBussiness, 
	PromptHandle = @PromptHandle,
	PromptInput = @PromptInput,
	PromptOutput = @PromptOutput,
	LastModifyDate = GETDATE(),
	LastModifyUserID = 'ASOFTADMIN'
WHERE ParameterID01 IN (SELECT TOP 1 APK FROM ONT1041 WHERE ParameterName ='BEM_AGENT_BEMF2000_OTHER') --- Lấy đúng loại cấu hình DNTT (dịch vụ, máy móc, xây dựng....)
AND ParameterID07 IN (SELECT TOP 1 APK FROM ONT1041 WHERE ParameterName ='CRITERIA_INVOICE_NO') --- Lấy đúng tiêu chí 
