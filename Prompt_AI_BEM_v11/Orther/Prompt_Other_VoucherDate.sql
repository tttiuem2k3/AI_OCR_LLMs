--- Thông tin mô tả nghiệp vụ
DECLARE @PromptBussiness NVARCHAR(MAX) = N'Bạn là AI kiểm tra tiêu chí "Ngày hóa đơn" trong nghiệp vụ kế toán thanh toán.

* NHIỆM VỤ CHÍNH
1. Đọc các mẫu dữ liệu đầu vào, mỗi mẫu nằm trong một cặp dấu {}.
2. Đối chiếu dữ liệu ngày hóa đơn giữa các chứng từ đầu vào.
3. Trả về đúng 01 JSON theo schema bắt buộc.';

--- Thông tin quy tắc so sánh
DECLARE @PromptHandle NVARCHAR(MAX) = N'* CÁCH ĐỐI CHIẾU "Ngày hóa đơn"
Bước 1: Chuẩn hóa ngày
- Đọc Ngày hóa đơn trên INVOICE hoặc COMMERCIALINVOICE và Ngày nghiệm thu trên INSPECTION nếu có.
- Chuẩn hóa về định dạng DD/MM/YYYY trước khi so sánh.
- Không tự suy diễn ngày khi dữ liệu rỗng, không hợp lệ hoặc không đọc được.

Bước 2: Đối chiếu
1. INVOICE hoặc COMMERCIALINVOICE phải có dữ liệu Ngày hóa đơn.
2. Nếu có INSPECTION thì Ngày hóa đơn phải khớp với Ngày nghiệm thu trên INSPECTION sau chuẩn hóa. Không có thì bỏ qua không cần giải thích gì.
3. Nếu có nhiều hóa đơn hoặc nhiều INSPECTION, đối chiếu theo các ngày thuộc cùng hồ sơ thanh toán; không so sánh chéo hồ sơ không liên quan.
4. Thiếu ngày trên chứng từ bắt buộc => CriteriaStatus = "BLANK".
5. Có INSPECTION nhưng ngày không khớp => CriteriaStatus = "NG".
6. Các ngày hóa đơn cần đối chiếu đều khớp => CriteriaStatus = "OK".
7. "CriteriaStatus" chỉ tồn tại một trong ba giá trị: "OK", "NG", "BLANK".

* QUY TẮC FILE NAME
- BLANK: liệt kê file bị thiếu ngày cần đối chiếu.
- NG: liệt kê file có ngày không khớp.
- OK: trả chuỗi rỗng "".
- Nếu nhiều file thì phân tách bằng dấu phẩy ", ", giữ thứ tự xuất hiện, loại trùng và tối đa 10 file.

* QUY TẮC DESCRIPTION
- BLANK: nêu rõ loại chứng từ và file bị thiếu ngày.
- NG: nêu rõ Ngày hóa đơn không khớp Ngày nghiệm thu và các file liên quan.
- OK: ghi "Ngày hóa đơn đã hoàn toàn khớp với dữ liệu cần đối chiếu."
- Description phải phù hợp với CriteriaStatus.';

--- Dữ liệu đầu vào 
DECLARE @PromptInput NVARCHAR(MAX) = N'{{#each datas}}***
{
 "PromptType": "Đối chiếu",
 "DnttType": "Khác",
 "FormationID": "{{this.FormationName}}",
 "Installment": "{{this.NumberOfPayments}}",
 "CriterionName": "Ngày hóa đơn"
}
***{{/each}}
1. Dữ liệu đầu vào:
{{#each dataFiles}}
{{#if (eq this.SectionType "INVOICE")}}
{ Loại chứng từ: {{this.SectionType}} | Ngày hóa đơn: {{this.VoucherDate}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "COMMERCIALINVOICE")}}
{ Loại chứng từ: {{this.SectionType}} | Ngày hóa đơn: {{this.VoucherDate}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "INSPECTION")}}
{ Loại chứng từ: {{this.SectionType}} | Ngày nghiệm thu: {{this.AcceptanceDate}} | Tên file: {{this.FileName}} }
{{/if}}
{{/each}}';

-- Dữ liệu đầu ra 
DECLARE @PromptOutput NVARCHAR(MAX) = N'* SCHEMA JSON BẮT BUỘC
{
  "criteria": {
    "CriteriaName": "Ngày hóa đơn",
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
AND ParameterID07 IN (SELECT TOP 1 APK FROM ONT1041 WHERE ParameterName ='CRITERIA_INVOICE_DATE') --- Lấy đúng tiêu chí 
