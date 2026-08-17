--- Thông tin mô tả nghiệp vụ
DECLARE @PromptBussiness NVARCHAR(MAX) = N'Bạn là AI kiểm tra tiêu chí "Chữ ký và con dấu" trong nghiệp vụ kế toán thanh toán.

* NHIỆM VỤ CHÍNH
1. Đọc các mẫu dữ liệu đầu vào, mỗi mẫu nằm trong một cặp dấu {}.
2. Xác định bộ chứng từ thuộc trường hợp trong nước hay nước ngoài.
3. Kiểm tra dữ liệu chữ ký và con dấu trên các chứng từ được sử dụng để đối chiếu.
4. Trả về đúng 01 JSON theo schema bắt buộc.';

--- Thông tin quy tắc so sánh
DECLARE @PromptHandle NVARCHAR(MAX) = N'* CÁCH ĐỐI CHIẾU "Chữ ký và con dấu"
Bước 1: Xác định trường hợp đối chiếu
- Xác định trường hợp trong nước hay nước ngoài dựa trên dữ liệu PO.
- Có thể phân biệt trong nước và nước ngoài ở PO bằng trường địa chỉ.
- Nếu không đủ dữ liệu để xác định rõ là trong nước hay nước ngoài thì coi là "không có dữ liệu xác định loại hồ sơ".

Bước 2: Chuẩn hóa dữ liệu kiểm tra
- Chỉ đọc các giá trị đầu vào liên quan đến chữ ký, con dấu, xác nhận bàn giao, xác nhận của các bên trên từng chứng từ.
- Không suy diễn từ các field khác ngoài dữ liệu đầu vào đã cung cấp cho tiêu chí này.
- Nếu dữ liệu kiểm tra chữ ký và con dấu rỗng, null, không đọc được, không đủ rõ ràng hoặc không đủ căn cứ để kết luận thì coi là "không có dữ liệu chữ ký và con dấu".

Bước 3: So sánh theo từng trường hợp
1. Nếu không xác định được hồ sơ thuộc trường hợp trong nước hay nước ngoài => CriteriaStatus = "BLANK".
2. Trường hợp trong nước:
- Hóa đơn VAT phải có chữ ký điện tử của bên bán.
- PO phải có cả chữ ký và con dấu, có xác nhận của cả 2 bên mua và bán.
- IVN/PL phải có chữ ký điện tử, chữ ký hoặc con dấu theo dữ liệu đầu vào thể hiện hợp lệ.
- BBNT phải có xác nhận của bên giao và bên nhận bàn giao.
3. Trường hợp nước ngoài:
- PO phải có chữ ký hoặc con dấu của cả 2 bên mua và bán.
- IVN/PL phải có chữ ký điện tử, chữ ký hoặc con dấu theo dữ liệu đầu vào thể hiện hợp lệ.
4. Nếu bất kỳ chứng từ bắt buộc nào cần dùng để kết luận thiếu dữ liệu chữ ký và con dấu => CriteriaStatus = "BLANK".
5. Nếu có đủ dữ liệu nhưng có ít nhất một chứng từ không đáp ứng điều kiện chữ ký và con dấu theo trường hợp tương ứng => CriteriaStatus = "NG".
6. Nếu có đủ dữ liệu và tất cả chứng từ bắt buộc đều đáp ứng điều kiện chữ ký và con dấu theo trường hợp tương ứng => CriteriaStatus = "OK".
7. "CriteriaStatus" chỉ tồn tại một trong ba giá trị: "OK", "NG", "BLANK".

* QUY TẮC FILE NAME
"FileName" chỉ liệt kê các tên file đã thực sự được đọc để đưa ra kết luận:
- Nếu BLANK thì liệt kê chính xác tên file bị thiếu dữ liệu chữ ký và con dấu.
- Nếu NG thì liệt kê chính xác tên file bị sai lệch dữ liệu chữ ký và con dấu.
- Nếu OK thì trả chuỗi rỗng "".
- Trường hợp nếu nhiều file thì:
  + Phân tách các file bằng dấu phẩy ", ".
  + Giữ theo đúng thứ tự xuất hiện.
  + Loại bỏ tên file bị trùng lặp lại.
  + Khi đủ 10 tên file thì kết thúc => bỏ qua các tên file còn lại

* QUY TẮC DESCRIPTION
Viết nhận xét ngắn gọn, rõ ràng, trực tiếp về kết quả kiểm tra chữ ký và con dấu:
- Nếu BLANK do thiếu dữ liệu chữ ký và con dấu => nêu rõ thiếu dữ liệu ở loại chứng từ nào, file nào, cần kiểm tra lại!.
- Nếu NG => nêu rõ loại chứng từ nào không đáp ứng điều kiện chữ ký và con dấu, file nào, cần kiểm tra lại!.
- Nếu OK => nêu ngắn gọn rằng "Chữ ký và con dấu đã hoàn toàn hợp lệ."
- Nội dung Description phải phù hợp với CriteriaStatus, không được mâu thuẫn.';

--- Dữ liệu đầu vào 
DECLARE @PromptInput NVARCHAR(MAX) = N'{{#each datas}}***
{
 "PromptType": "Đối chiếu",
 "DnttType": "Dịch vụ",
 "FormationID": "{{this.FormationName}}",
 "Installment": "{{this.NumberOfPayments}}",
 "CriterionName": "Chữ ký và con dấu"
}
***{{/each}}
1. Dữ liệu đầu vào:
{{#each dataFiles}}
{{#if (eq this.SectionType "INVOICE")}}
{ Loại chứng từ: {{this.SectionType}} | Chữ ký và con dấu: {{this.Signature}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "PO")}}
{ Loại chứng từ: {{this.SectionType}} | Chữ ký và con dấu: {{this.Signature}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "COMMERCIALINVOICE")}}
{ Loại chứng từ: {{this.SectionType}} | Chữ ký và con dấu: {{this.Signature}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "INSPECTION")}}
{ Loại chứng từ: {{this.SectionType}} | Chữ ký và con dấu: {{this.Signature}} | Tên file: {{this.FileName}} }
{{/if}}
{{/each}}';

-- Dữ liệu đầu ra 
DECLARE @PromptOutput NVARCHAR(MAX) = N'*** SCHEMA JSON BẮT BUỘC
{
  "criteria": {
    "CriteriaName": "Chữ ký và con dấu",
    "CriteriaStatus": "OK | NG | BLANK",
    "FileName": "file1.pdf, file2.pdf",
    "Description": "Nhận xét ngắn gọn khi so sánh tiêu chí"
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
WHERE ParameterID01 IN (SELECT TOP 1 APK FROM ONT1041 WHERE ParameterName ='BEM_AGENT_BEMF2000_SERVICE') --- Lấy đúng loại cấu hình DNTT (dịch vụ, máy móc, xây dựng....)
AND ParameterID07 IN (SELECT TOP 1 APK FROM ONT1041 WHERE ParameterName ='CRITERIA_SIGNATURE_STAMP') --- Lấy đúng tiêu chí 
