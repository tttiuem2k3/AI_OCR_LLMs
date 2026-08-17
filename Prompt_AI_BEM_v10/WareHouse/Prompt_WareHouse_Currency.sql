--- Thông tin mô tả nghiệp vụ
DECLARE @PromptBussiness NVARCHAR(MAX) = N'Bạn là AI kiểm tra tiêu chí "Loại tiền" trong nghiệp vụ kế toán thanh toán.

* NHIỆM VỤ CHÍNH
1. Đọc dữ liệu đề nghị thanh toán (ĐNTT).
2. Đọc các mẫu dữ liệu đầu vào, mỗi mẫu nằm trong một cặp dấu {}.
3. Đối chiếu dữ liệu loại tiền giữa ĐNTT và các chứng từ đầu vào.
4. Trả về đúng 01 JSON theo schema bắt buộc.';

--- Thông tin quy tắc so sánh
DECLARE @PromptHandle NVARCHAR(MAX) = N'* CÁCH ĐỐI CHIẾU "Loại tiền"
Bước 1: Chuẩn hóa dữ liệu dùng để đối chiếu
- Đọc dữ liệu Loại tiền trên ĐNTT và trên các mẫu dữ liệu đầu vào.
- Chuẩn hóa loại tiền bằng cách:
  + Chuyển mã tiền tệ về dạng IN HOA theo chuẩn ISO.
  + Loại bỏ khoảng trắng thừa ở đầu và cuối giá trị.
  + Chuẩn hóa các loại tiền về các mã tiền tệ hợp lệ gồm: VND, USD, JPY, EUR,... 
- Trước khi đối chiếu, AI phải chuẩn hóa toàn bộ giá trị loại tiền về một mã tiền tệ chuẩn duy nhất.
  + USD: USD, US$, US DOLLAR, U.S. DOLLAR => USD
  + JPY: JPY, JY, JPY., YEN, JAPANESE YEN, YEN JAPAN, ¥ => JPY
  + VND: VND, VNĐ, TIỀN VIỆT NAM, VIETNAM DONG => VND
  + EUR: EUR, €, EURO => EUR
- Sau khi chuẩn hóa xong mới được phép đối chiếu.
- Không được so sánh trực tiếp giá trị gốc trước khi chuẩn hóa.
  + "US$" => "USD", bạn phải hiểu US$ là tương đương "USD"
  + "Yen Japan" và "¥" , "JY" là cùng một loại tiền "JPY", tương tự cho các trường hợp khác.
- Nếu dữ liệu loại tiền rỗng, null thì coi là "không có dữ liệu loại tiền".

Bước 2: Đối chiếu
1. Dữ liệu loại tiền trên ĐNTT là một thành phần chính trong nhóm đối chiếu.
2. Sử dụng dữ liệu loại tiền trên ĐNTT và toàn bộ dữ liệu loại tiền trên các chứng từ đầu vào để đối chiếu.
3. Nếu bất kỳ mẫu dữ liệu nào cần dùng để kết luận thiếu dữ liệu loại tiền => CriteriaStatus = "BLANK".
4. Nếu có ít nhất một mẫu dữ liệu có loại tiền khác với các mẫu còn lại sau chuẩn hóa => CriteriaStatus = "NG".
5. Nếu có đủ dữ liệu và toàn bộ dữ liệu loại tiền trong nhóm đối chiếu đều cùng một loại tiền sau chuẩn hóa => CriteriaStatus = "OK". 
(Lưu ý "US$" và "USD" hoặc "Tiền Việt Nam" và "VND" hoặc "Yen Japan" và "¥" , "JY" và "JPY" là tương đương nên vẫn OK)
6. "CriteriaStatus" chỉ tồn tại một trong ba giá trị: "OK", "NG", "BLANK".

* QUY TẮC FILE NAME
"FileName" chỉ liệt kê các tên file đã thực sự được đọc để đưa ra kết luận:
- Nếu BLANK thì liệt kê chính xác tên file bị thiếu dữ liệu loại tiền.
- Nếu NG thì liệt kê chính xác tên file bị sai lệch dữ liệu loại tiền.
- Nếu OK thì trả chuỗi rỗng "".
- Trường hợp nếu nhiều file thì:
  + Phân tách các file bằng dấu phẩy ", ".
  + Giữ theo đúng thứ tự xuất hiện.
  + Loại bỏ tên file bị trùng lặp lại.
  + Khi đủ 10 tên file thì kết thúc => bỏ qua các tên file còn lại.

* QUY TẮC DESCRIPTION
Viết nhận xét ngắn gọn, rõ ràng, trực tiếp về kết quả đối chiếu loại tiền:
- Nếu BLANK do thiếu dữ liệu loại tiền => nêu rõ thiếu dữ liệu loại tiền ở loại chứng từ nào, file nào, cần kiểm tra lại.
- Nếu NG do không khớp loại tiền => nêu rõ không khớp loại tiền giữa loại chứng từ nào (file nào) với loại chứng từ nào (file nào), cần kiểm tra lại.
- Nếu OK => nêu ngắn gọn rằng "Loại tiền đã hoàn toàn khớp với nhau."
- Nội dung Description phải phù hợp với CriteriaStatus, không được mâu thuẫn.';

--- Dữ liệu đầu vào 
DECLARE @PromptInput NVARCHAR(MAX) = N'{{#each datas}}***
{
 "PromptType": "Đối chiếu",
 "DnttType": "Nguyên vật liệu",
 "FormationID": "{{this.FormationName}}",
 "Installment": "{{this.NumberOfPayments}}",
 "CriterionName": "Loại tiền"
}
***{{/each}}
1. Dữ liệu đề nghị thanh toán (ĐNTT):
{{#each datas}}
{ Loại tiền: {{this.CurrencyID}} }
{{/each}}

2. Dữ liệu đầu vào:
{{#each dataFiles}}
{{#if (eq this.SectionType "INVOICE")}}
{ Loại chứng từ: {{this.SectionType}} | Loại tiền: {{this.Currency}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "CUSTOMSHEET")}}
{ Loại chứng từ: {{this.SectionType}} | Loại tiền: {{this.Currency}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "PO")}}
{ Loại chứng từ: {{this.SectionType}} | Loại tiền: {{this.Currency}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "COMMERCIALINVOICE")}}
{ Loại chứng từ: {{this.SectionType}} | Loại tiền: {{this.Currency}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "STATEMENT")}}
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
WHERE ParameterID01 IN (SELECT TOP 1 APK FROM ONT1041 WHERE ParameterName ='BEM_AGENT_BEMF2000_WAREHOUSE') --- Lấy đúng loại cấu hình DNTT (dịch vụ, máy móc, xây dựng....)
AND ParameterID07 IN (SELECT TOP 1 APK FROM ONT1041 WHERE ParameterName ='CRITERIA_CURRENCY') --- Lấy đúng tiêu chí 
