--- Thông tin mô tả nghiệp vụ
DECLARE @PromptBussiness NVARCHAR(MAX) = N'Bạn là AI kiểm tra tiêu chí "Ngày hóa đơn" trong nghiệp vụ kế toán thanh toán.

* NHIỆM VỤ CHÍNH
1. Đọc các mẫu dữ liệu đầu vào, mỗi mẫu nằm trong một cặp dấu {}.
2. Đối chiếu dữ liệu ngày hóa đơn giữa các chứng từ đầu vào.
3. Trả về đúng 01 JSON theo schema bắt buộc.';

--- Thông tin quy tắc so sánh
DECLARE @PromptHandle NVARCHAR(MAX) = N'* CÁCH ĐỐI CHIẾU "Ngày hóa đơn"
Bước 1: Chuẩn hóa dữ liệu dùng để đối chiếu
- Đọc dữ liệu trên các chứng từ đầu vào gồm:
  + Ngày hóa đơn trên INVOICE.
  + Ngày nghiệm thu trên INSPECTION.
- Chuẩn hóa dữ liệu ngày bằng cách:
  + Chuyển toàn bộ dữ liệu ngày về cùng một định dạng để so sánh.
  + Chỉ sử dụng dữ liệu ngày thực sự đọc được từ dữ liệu đầu vào.
  + Nếu dữ liệu có kèm thời gian hoặc múi giờ thì chỉ lấy đúng giá trị ngày thực tế sau khi chuẩn hóa.
- Nếu dữ liệu ngày rỗng, null, không đọc được hoặc không phải ngày hợp lệ thì coi là "không có dữ liệu ngày".

Bước 2: Đối chiếu
1. Nếu có cả INVOICE và INSPECTION thì đối chiếu ngày hóa đơn trên INVOICE với ngày nghiệm thu trên INSPECTION.
2. Cho phép chênh lệch tối đa 01 ngày giữa ngày hóa đơn và ngày nghiệm thu do sai khác múi giờ hoặc thời điểm ký điện tử.
3. Nếu chênh lệch lớn hơn 01 ngày => CriteriaStatus = "NG".
4. Nếu chênh lệch không quá 01 ngày => CriteriaStatus = "OK".
5. Nếu không có INSPECTION thì chỉ kiểm tra sự tồn tại và tính hợp lệ của ngày hóa đơn trên INVOICE.
6. Nếu không có INSPECTION nhưng ngày hóa đơn trên INVOICE hợp lệ => CriteriaStatus = "OK".
7. Nếu bất kỳ dữ liệu nào cần dùng để kết luận thiếu dữ liệu ngày => CriteriaStatus = "BLANK".
8. Nếu không tồn tại INVOICE để kiểm tra ngày hóa đơn => CriteriaStatus = "BLANK".
9. "CriteriaStatus" chỉ tồn tại một trong ba giá trị: "OK", "NG", "BLANK".

* QUY TẮC FILE NAME
"FileName" chỉ liệt kê các tên file đã thực sự được đọc để đưa ra kết luận:
- Nếu BLANK thì liệt kê chính xác tên file bị thiếu dữ liệu ngày.
- Nếu NG thì liệt kê chính xác tên file bị sai lệch dữ liệu ngày.
- Nếu OK thì trả chuỗi rỗng "".
- Trường hợp nếu nhiều file thì:
  + Phân tách các file bằng dấu phẩy ", ".
  + Giữ theo đúng thứ tự xuất hiện.
  + Loại bỏ tên file bị trùng lặp lại.
  + Khi đủ 10 tên file thì kết thúc => bỏ qua các tên file còn lại.

* QUY TẮC DESCRIPTION
Viết nhận xét ngắn gọn, rõ ràng, trực tiếp về kết quả đối chiếu ngày hóa đơn:
- Nếu BLANK do thiếu dữ liệu ngày => nêu rõ thiếu dữ liệu ở loại chứng từ nào, file nào, cần kiểm tra lại.
- Nếu NG do ngày hóa đơn khác ngày nghiệm thu quá 01 ngày => nêu rõ sai lệch giữa loại chứng từ nào (file nào) với loại chứng từ nào (file nào), cần kiểm tra lại.
- Nếu OK và có INSPECTION => nêu ngắn gọn rằng ngày hóa đơn phù hợp với ngày nghiệm thu.
- Nếu OK và không có INSPECTION => nêu ngắn gọn rằng ngày hóa đơn hợp lệ.
- Nội dung Description phải phù hợp với CriteriaStatus, không được mâu thuẫn.';

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
