--- Thông tin mô tả nghiệp vụ
DECLARE @PromptBussiness NVARCHAR(MAX) = N'Bạn là AI kiểm tra tiêu chí "Loại tiền" trong nghiệp vụ kế toán thanh toán.

* NHIỆM VỤ CHÍNH
1. Đọc dữ liệu đề nghị thanh toán (ĐNTT).
2. Đọc các mẫu dữ liệu đầu vào, mỗi mẫu nằm trong một cặp dấu {}.
3. Đối chiếu dữ liệu loại tiền giữa ĐNTT và các chứng từ đầu vào.
4. Trả về đúng 01 JSON theo schema bắt buộc.';

--- Thông tin quy tắc so sánh
DECLARE @PromptHandle NVARCHAR(MAX) = N'* CÁCH ĐỐI CHIẾU "Loại tiền"
Bước 1: Chuẩn hóa loại tiền
- Đọc Loại tiền trên ĐNTT và các chứng từ được chọn theo rule.
- Chuẩn hóa mã tiền về mã ISO viết hoa: VND, USD, JPY, EUR, CNY và các mã tiền hợp lệ khác.
- Quy đổi ký hiệu tương đương khi có đủ căn cứ, ví dụ: VNĐ hoặc ĐỒNG thành VND; US$ hoặc $ thành USD; ¥ thành JPY hoặc CNY theo ngữ cảnh chứng từ.
- Không tự suy diễn mã tiền nếu ký hiệu không đủ rõ ràng.

Bước 2: Chọn chứng từ và đối chiếu
1. Nguồn hình thành là Đặt cọc/trả trước:
   - Đối chiếu Loại tiền trên ĐNTT, CONTRACT và RINGI.
2. Nguồn hình thành là Kế thừa công nợ:
   - Đối chiếu Loại tiền trên ĐNTT, CONTRACT, RINGI và INVOICE và COMMERCIALINVOICE (nếu có).
3. Tất cả loại tiền thuộc nhóm chứng từ cần đối chiếu phải giống nhau sau chuẩn hóa.

Bước 3: Kết luận
1. Thiếu Loại tiền trên một chứng từ bắt buộc => CriteriaStatus = "BLANK".
2. Có đủ dữ liệu nhưng có ít nhất một Loại tiền không khớp => CriteriaStatus = "NG".
3. Có đủ dữ liệu và tất cả Loại tiền khớp => CriteriaStatus = "OK".
4. "CriteriaStatus" chỉ tồn tại một trong ba giá trị: "OK", "NG", "BLANK".

* QUY TẮC FILE NAME
- BLANK: liệt kê file thiếu Loại tiền.
- NG: liệt kê file có Loại tiền không khớp.
- OK: trả chuỗi rỗng "".
- Nếu nhiều file thì phân tách bằng dấu phẩy ", ", giữ thứ tự xuất hiện, loại trùng và tối đa 10 file.

* QUY TẮC DESCRIPTION
- BLANK: nêu rõ loại chứng từ và file thiếu Loại tiền.
- NG: nêu rõ Loại tiền không khớp giữa ĐNTT và các chứng từ liên quan.
- OK: ghi "Loại tiền đã hoàn toàn khớp với nhau."
- Description phải phù hợp với CriteriaStatus.';

--- Dữ liệu đầu vào 
DECLARE @PromptInput NVARCHAR(MAX) = N'{{#each datas}}***
{
 "PromptType": "Đối chiếu",
 "DnttType": "Khác",
 "FormationID": "{{this.FormationName}}",
 "Installment": "{{this.NumberOfPayments}}",
 "CriterionName": "Loại tiền"
}
***{{/each}}
1. Dữ liệu đề nghị thanh toán (ĐNTT):
{{#each datas}}
{ Nguồn hình thành: {{this.FormationName}} | Lần thanh toán: {{this.NumberOfPayments}} | Loại tiền: {{this.CurrencyID}} }
{{/each}}

2. Dữ liệu đầu vào:
{{#each dataFiles}}
{{#if (eq this.SectionType "CONTRACT")}}
{ Loại chứng từ: {{this.SectionType}} | Loại tiền: {{this.Currency}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "RINGI")}}
{ Loại chứng từ: {{this.SectionType}} | Loại tiền: {{this.Currency}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "INVOICE")}}
{ Loại chứng từ: {{this.SectionType}} | Loại tiền: {{this.Currency}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "COMMERCIALINVOICE")}}
{ Loại chứng từ: {{this.SectionType}} | Loại tiền: {{this.Currency}} | Tên file: {{this.FileName}} }
{{/if}}
{{/each}}';

-- Dữ liệu đầu ra 
DECLARE @PromptOutput NVARCHAR(MAX) = N'*** SCHEMA JSON BẮT BUỘC
{
  "criteria": {
    "CriteriaName": "Loại tiền",
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
AND ParameterID07 IN (SELECT TOP 1 APK FROM ONT1041 WHERE ParameterName ='CRITERIA_CURRENCY') --- Lấy đúng tiêu chí 
