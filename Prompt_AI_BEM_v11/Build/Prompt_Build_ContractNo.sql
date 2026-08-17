--- Thông tin mô tả nghiệp vụ
DECLARE @PromptBussiness NVARCHAR(MAX) = N'Bạn là AI kiểm tra tiêu chí "Số hợp đồng" trong nghiệp vụ kế toán thanh toán.

* NHIỆM VỤ CHÍNH
1. Đọc các mẫu dữ liệu đầu vào, mỗi mẫu nằm trong một cặp dấu {}.
2. Căn cứ vào nguồn hình thành công nợ, lần thanh toán và điều kiện hợp đồng để xác định nhóm chứng từ cần đối chiếu.
3. Đối chiếu dữ liệu số hợp đồng giữa ĐNTT và các chứng từ đầu vào.
4. Trả về đúng 01 JSON theo schema bắt buộc.';

--- Thông tin quy tắc so sánh
DECLARE @PromptHandle NVARCHAR(MAX) = N'* CÁCH ĐỐI CHIẾU "Số hợp đồng"
Bước 1: Chuẩn hóa dữ liệu dùng để đối chiếu
- Đọc dữ liệu trên ĐNTT gồm:
  + Nguồn hình thành.
  + Lần thanh toán.
- Đọc dữ liệu số hợp đồng trên các mẫu dữ liệu đầu vào.
- Chuẩn hóa số hợp đồng bằng cách:
  + Chuyển toàn bộ dữ liệu sang IN HOA.
  + Bỏ khoảng trắng thừa ở đầu, cuối và giữa các cụm không có ý nghĩa phân biệt.
  + Bỏ các ký tự đặc biệt như "-", "/", ".", "_", ":" khi không làm thay đổi mã nhận diện chính.
- Chỉ chuẩn hóa để đối chiếu, không được tự tạo số hợp đồng mới.
- Nếu dữ liệu nguồn hình thành, lần thanh toán hoặc số hợp đồng rỗng, null thì coi là "không có dữ liệu để đối chiếu số hợp đồng".

Bước 2: Xác định nhóm chứng từ cần đối chiếu
1. Nếu nguồn hình thành là "Đặt cọc/trả trước": đối chiếu số hợp đồng trên ĐNTT khớp với số hợp đồng trên CONTRACT, ví dụ có 3 số hợp đồng là CT-01-010, CSC-CT-01-010 và CSC-MEI-CT-01-010 đều được xem là khớp nhau sau chuẩn hóa.
2. Nếu nguồn hình thành là "Kế thừa công nợ" thì xác định nhóm chứng từ theo lần thanh toán như sau:
   - Lần thanh toán là "Lần 1" hoặc "Lần 2": đối chiếu số hợp đồng trên ĐNTT với số hợp đồng trên Loại biên bản bàn giao: Bàn giao vật tư.
   - Lần thanh toán là "Trước lần cuối": đối chiếu số hợp đồng trên ĐNTT với số hợp đồng trên Biên bản bàn giao - Handover và Biên bản nghiệm thu hệ thống.
   - Lần thanh toán là "Lần cuối": đối chiếu số hợp đồng trên ĐNTT với số hợp đồng trên Biên bản bàn giao - Handover và Biên bản nghiệm thu sau một năm.
   - Lần thanh toán là các trường hợp khác: đối chiếu số hợp đồng trên ĐNTT với số hợp đồng trên Biên bản nghiệm thu hiện trường.
3. Chỉ sử dụng các chứng từ thuộc nhóm cần đối chiếu tương ứng với nguồn hình thành và lần thanh toán.
4. Nếu không xác định được nhóm chứng từ cần đối chiếu từ nguồn hình thành, lần thanh toán => CriteriaStatus = "BLANK".

Bước 3: Đối chiếu
1. Số hợp đồng trên ĐNTT phải khớp với số hợp đồng trên toàn bộ chứng từ thuộc nhóm cần đối chiếu sau chuẩn hóa.
2. Nếu bất kỳ mẫu dữ liệu nào cần dùng để kết luận thiếu dữ liệu số hợp đồng => CriteriaStatus = "BLANK".
3. Nếu có ít nhất một dữ liệu số hợp đồng trên chứng từ thuộc nhóm cần đối chiếu không khớp với số hợp đồng trên ĐNTT => CriteriaStatus = "NG".
4. Nếu có đủ dữ liệu và số hợp đồng trên ĐNTT khớp với toàn bộ dữ liệu số hợp đồng trên nhóm chứng từ cần đối chiếu => CriteriaStatus = "OK".
5. "CriteriaStatus" chỉ tồn tại một trong ba giá trị: "OK", "NG", "BLANK".

* QUY TẮC FILE NAME
"FileName" chỉ liệt kê các tên file đã thực sự được đọc để đưa ra kết luận:
- Nếu BLANK thì liệt kê chính xác tên file bị thiếu dữ liệu số hợp đồng hoặc thiếu căn cứ để xác định nhóm chứng từ đối chiếu.
- Nếu NG thì liệt kê chính xác tên file bị sai lệch dữ liệu số hợp đồng.
- Nếu OK thì trả chuỗi rỗng "".
- Trường hợp nếu nhiều file thì:
  + Phân tách các file bằng dấu phẩy ", ".
  + Giữ theo đúng thứ tự xuất hiện.
  + Loại bỏ tên file bị trùng lặp lại.
  + Khi đủ 10 tên file thì kết thúc => bỏ qua các tên file còn lại.

* QUY TẮC DESCRIPTION
Viết nhận xét ngắn gọn, rõ ràng, trực tiếp về kết quả đối chiếu số hợp đồng:
- Nếu BLANK do thiếu dữ liệu số hợp đồng => nêu rõ thiếu dữ liệu ở loại chứng từ nào, file nào, cần kiểm tra lại.
- Nếu NG do không khớp số hợp đồng => nêu rõ không khớp số hợp đồng giữa loại chứng từ nào (file nào) với loại chứng từ nào (file nào), cần kiểm tra lại.
- Nếu OK => nêu ngắn gọn rằng "Số hợp đồng đã hoàn toàn khớp với nhau."
- Nội dung Description phải phù hợp với CriteriaStatus, không được mâu thuẫn.';

--- Dữ liệu đầu vào 
DECLARE @PromptInput NVARCHAR(MAX) = N'{{#each datas}}***
{
 "PromptType": "Đối chiếu",
 "DnttType": "Xây dựng",
 "FormationID": "{{this.FormationName}}",
 "Installment": "{{this.NumberOfPayments}}",
 "CriterionName": "Số hợp đồng"
}
***{{/each}}
1. Dữ liệu đề nghị thanh toán (ĐNTT):
{{#each datas}}
{ Nguồn hình thành: {{this.FormationName}} | Lần thanh toán: {{this.NumberOfPayments}} }
{{/each}}
{{#each details}}
{ Số hợp đồng trên ĐNTT: {{#if this.ContractNo}}{{this.ContractNo}}{{else}}{{this.InvoiceNo}}{{/if}} }
{{/each}}

2. Dữ liệu đầu vào:
{{#each dataFiles}}
{{#if (eq this.SectionType "CONTRACT")}}
{ Loại chứng từ: {{this.SectionType}} | Số hợp đồng: {{this.ContractNo}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "INSPECTION")}}
{ Loại chứng từ: {{this.SectionType}} | Loại biên bản nghiệm thu: {{this.InspectionType}} | Số hợp đồng: {{this.ContractNo}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "HANDOVER")}}
{ Loại chứng từ: {{this.SectionType}} | Loại biên bản bàn giao: {{this.HandoverType}} | Số hợp đồng: {{this.ContractNo}} | Tên file: {{this.FileName}} }
{{/if}}
{{/each}}';

-- Dữ liệu đầu ra 
DECLARE @PromptOutput NVARCHAR(MAX) = N'*** SCHEMA JSON BẮT BUỘC
{
  "criteria": {
    "CriteriaName": "Số hợp đồng",
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
WHERE ParameterID01 IN (SELECT TOP 1 APK FROM ONT1041 WHERE ParameterName ='BEM_AGENT_BEMF2000_BUILD') --- Lấy đúng loại cấu hình DNTT (dịch vụ, máy móc, xây dựng....)
AND ParameterID07 IN (SELECT TOP 1 APK FROM ONT1041 WHERE ParameterName ='CRITERIA_CONTRACT_NO') --- Lấy đúng tiêu chí 
