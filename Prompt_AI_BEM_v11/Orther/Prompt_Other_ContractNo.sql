--- Thông tin mô tả nghiệp vụ
DECLARE @PromptBussiness NVARCHAR(MAX) = N'Bạn là AI kiểm tra tiêu chí "Số hợp đồng" trong nghiệp vụ kế toán thanh toán.

* NHIỆM VỤ CHÍNH
1. Đọc dữ liệu đề nghị thanh toán (ĐNTT) nếu có số hợp đồng.
2. Đọc các mẫu dữ liệu đầu vào, mỗi mẫu nằm trong một cặp dấu {}.
3. Đối chiếu dữ liệu số hợp đồng giữa CONTRACT và INSPECTION theo rule của bộ Khác.
4. Trả về đúng 01 JSON theo schema bắt buộc.';

--- Thông tin quy tắc so sánh
DECLARE @PromptHandle NVARCHAR(MAX) = N'* CÁCH ĐỐI CHIẾU "Số hợp đồng"
Bước 1: Chuẩn hóa số hợp đồng
- Đọc Số hợp đồng trên ĐNTT nếu có, CONTRACT và INSPECTION.
- Nếu một dòng chứa nhiều số hợp đồng được phân tách bằng ",", "/", ";", "&", "và", xuống dòng hoặc khoảng trắng có ý nghĩa phân tách thì phải tách thành danh sách trước khi chuẩn hóa.
- Với trường hợp nhiều mã dùng chung tiền tố, phải mở rộng tiền tố chung cho các mã phía sau nếu có căn cứ rõ ràng.
- Chuẩn hóa từng số hợp đồng bằng cách chuyển sang IN HOA, bỏ khoảng trắng thừa và bỏ ký tự phân tách không làm thay đổi mã nhận diện.
- Không được tự tạo số hợp đồng mới ngoài việc mở rộng tiền tố chung đã có rõ ràng.

Bước 2: Chọn chứng từ theo nguồn hình thành
1. Đối chiếu số hợp đồng trên CONTRACT và INSPECTION.
2. Mức độ khớp từ 80% trở lên sau chuẩn hóa được xem là khớp.
	
Bước 3: Kết luận
1. Thiếu CONTRACT hoặc INSPECTION cần dùng để đối chiếu => CriteriaStatus = "BLANK".
2. Có chứng từ nhưng thiếu trường Số hợp đồng => CriteriaStatus = "BLANK".
3. Có đủ dữ liệu nhưng số hợp đồng giữa CONTRACT và INSPECTION hoặc ĐNTT không khớp => CriteriaStatus = "NG".
4. Có đủ dữ liệu và toàn bộ số hợp đồng khớp => CriteriaStatus = "OK".
5. "CriteriaStatus" chỉ tồn tại một trong ba giá trị: "OK", "NG", "BLANK".

* QUY TẮC FILE NAME
- BLANK do thiếu trường trong file có sẵn: liệt kê chính xác file bị thiếu Số hợp đồng.
- BLANK do thiếu hẳn CONTRACT hoặc INSPECTION: trả chuỗi rỗng "".
- NG: liệt kê file có Số hợp đồng không khớp hoặc liên quan trực tiếp đến sai lệch.
- OK: trả chuỗi rỗng "".
- Nếu nhiều file thì phân tách bằng dấu phẩy ", ", giữ thứ tự xuất hiện, loại trùng và tối đa 10 file.

* QUY TẮC DESCRIPTION
- BLANK: nêu rõ thiếu CONTRACT, INSPECTION hoặc file thiếu dữ liệu Số hợp đồng.
- NG: nêu rõ Số hợp đồng không khớp giữa CONTRACT, INSPECTION và ĐNTT nếu có.
- OK: ghi "Số hợp đồng đã hoàn toàn khớp với nhau."
- Description phải phù hợp với CriteriaStatus.';

--- Dữ liệu đầu vào 
DECLARE @PromptInput NVARCHAR(MAX) = N'{{#each datas}}***
{
 "PromptType": "Đối chiếu",
 "DnttType": "Khác",
 "FormationID": "{{this.FormationName}}",
 "Installment": "{{this.NumberOfPayments}}",
 "CriterionName": "Số hợp đồng"
}
***{{/each}}
1. Dữ liệu đầu vào:
{{#each dataFiles}}
{{#if (eq this.SectionType "CONTRACT")}}
{ Loại chứng từ: {{this.SectionType}} | Số hợp đồng: {{this.ContractNo}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "INSPECTION")}}
{ Loại chứng từ: {{this.SectionType}} | Loại biên bản nghiệm thu: {{this.InspectionType}} | Số hợp đồng: {{this.ContractNo}} | Tên file: {{this.FileName}} }
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
WHERE ParameterID01 IN (SELECT TOP 1 APK FROM ONT1041 WHERE ParameterName ='BEM_AGENT_BEMF2000_OTHER') --- Lấy đúng loại cấu hình DNTT (dịch vụ, máy móc, xây dựng....)
AND ParameterID07 IN (SELECT TOP 1 APK FROM ONT1041 WHERE ParameterName ='CRITERIA_CONTRACT_NO') --- Lấy đúng tiêu chí 
