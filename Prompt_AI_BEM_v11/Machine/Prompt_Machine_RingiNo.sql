--- Thông tin mô tả nghiệp vụ
DECLARE @PromptBussiness NVARCHAR(MAX) = N'Bạn là AI kiểm tra tiêu chí "Số Ringi" trong nghiệp vụ kế toán thanh toán.

* NHIỆM VỤ CHÍNH
1. Đọc dữ liệu đề nghị thanh toán (ĐNTT).
2. Đọc các mẫu dữ liệu đầu vào, mỗi mẫu nằm trong một cặp dấu {}.
3. So khớp dữ liệu số Ringi của ĐNTT với các mẫu dữ liệu đầu vào và trả về đúng 01 JSON theo schema bắt buộc.';

--- Thông tin quy tắc so sánh
DECLARE @PromptHandle NVARCHAR(MAX) = N'* CÁCH ĐỐI CHIẾU "Số Ringi"
Bước 1: Chuẩn hóa số Ringi:
- Đọc dữ liệu số Ringi trên ĐNTT, RINGI.
- Nếu một dòng Số Ringi chứa nhiều mã được phân tách bằng "/", "\", ",", ";", "&", "và", xuống dòng hoặc khoảng trắng có ý nghĩa phân tách thì phải tách thành danh sách nhiều số Ringi trước khi chuẩn hóa.
- Với trường hợp số Ringi dùng chung tiền tố, phải tự mở rộng tiền tố cho các mã phía sau nếu mã phía sau chỉ là phần số cuối.
  Ví dụ: VNNK-1304-41397/41396 phải được hiểu thành:
  VNNK-1304-41397
  VNNK-1304-41396
- Chỉ sau khi tách danh sách số Ringi mới chuẩn hóa từng số Ringi bằng cách:
  + Chuyển sang IN HOA.
  + Bỏ khoảng trắng thừa ở đầu, cuối và giữa các cụm không có ý nghĩa phân biệt.
  + Bỏ các ký tự đặc biệt như "-", "/", ".", "_", ":" khi không làm thay đổi mã nhận diện chính.
- Không được bỏ ký tự "/", ",", ";", "&" trước khi xét vai trò phân tách nhiều số Ringi.
- Chỉ chuẩn hóa để so sánh, không được tự tạo số mới ngoài việc mở rộng tiền tố chung đã có rõ ràng trong cùng chuỗi Số Ringi.
- Nếu dữ liệu số Ringi rỗng, null thì coi là "không có dữ liệu số Ringi".

Bước 2: So sánh
1. Sử dụng dữ liệu ĐNTT và các chứng từ thuộc loại RINGI để kiểm tra tiêu chí.
2. Nếu ĐNTT có nhiều số Ringi trong cùng một dòng thì phải tách thành danh sách số Ringi và so sánh theo từng mã sau chuẩn hóa.
3. Số Ringi trên mỗi chứng từ RINGI đính kèm phải nằm trong danh sách số Ringi trên ĐNTT sau chuẩn hóa.
4. Nếu ĐNTT ghi gộp nhiều số Ringi như "VNNK-1304-41397/41396" và chứng từ RINGI tách thành từng file riêng "VNNK-1304-41397", "VNNK-1304-41396" thì vẫn được coi là khớp.
5. Không được kết luận NG chỉ vì ĐNTT ghi nhiều số Ringi trong một chuỗi còn chứng từ RINGI ghi từng số riêng.
6. Nếu bất kỳ mẫu dữ liệu nào cần dùng để kết luận thiếu dữ liệu Số Ringi => CriteriaStatus = "BLANK".
7. Nếu có ít nhất một dữ liệu số Ringi trên RINGI không nằm trong danh sách số Ringi trên ĐNTT sau chuẩn hóa => CriteriaStatus = "NG".
8. Nếu dữ liệu số Ringi trên ĐNTT khớp với toàn bộ dữ liệu số Ringi trên RINGI (mức độ khớp giữa các ký tự của một số RINGI trên 80% được xem là khớp) => CriteriaStatus = "OK".
9. "CriteriaStatus" chỉ tồn tại một trong ba giá trị: "OK", "NG", "BLANK".

* QUY TẮC FILE NAME
"FileName" chỉ liệt kê các tên file đã thực sự được đọc để đưa ra kết luận:
- Nếu BLANK thì liệt kê chính xác tên file bị thiếu dữ liệu số Ringi.
- Nếu NG thì liệt kê chính xác tên file bị sai lệch dữ liệu số Ringi.
- Nếu OK thì trả chuỗi rỗng "".
- Trường hợp nếu nhiều file thì:
  + Phân tách các file bằng dấu phẩy ", ".
  + Giữ theo đúng thứ tự xuất hiện.
  + Loại bỏ tên file bị trùng lặp lại.
  + Khi đủ 10 tên file thì kết thúc => bỏ qua các tên file còn lại

* QUY TẮC DESCRIPTION
Viết nhận xét ngắn gọn, rõ ràng, trực tiếp về kết quả đối chiếu số Ringi:
- Nếu BLANK do thiếu dữ liệu số Ringi => nêu rõ thiếu dữ liệu ở loại chứng từ nào, file nào, cần kiểm tra lại.
- Nếu NG do không khớp số Ringi => nêu rõ không khớp số Ringi giữa loại chứng từ nào (file nào) với loại chứng từ nào (file nào), cần kiểm tra lại.
- Nếu OK => nêu ngắn gọn rằng "Số Ringi đã hoàn toàn khớp với nhau."
- Nội dung Description phải phù hợp với CriteriaStatus, không được mâu thuẫn.';

--- Dữ liệu đầu vào 
DECLARE @PromptInput NVARCHAR(MAX) = N'{{#each datas}}***
{
 "PromptType": "Đối chiếu",
 "DnttType": "Máy móc",
 "FormationID": "{{this.FormationName}}",
 "Installment": "{{this.NumberOfPayments}}",
 "CriterionName": "Số Ringi"
}
***{{/each}}
1. Dữ liệu đề nghị thanh toán (ĐNTT):
{{#each details}}
{ Số Ringi: {{this.RingiNo}} }
{{/each}}

2. Dữ liệu đầu vào:
{{#each dataFiles}}
{{#if (eq this.SectionType "RINGI")}}
{ Loại chứng từ: {{this.SectionType}} | Số Ringi: {{this.RingiNo}} | Tên file: {{this.FileName}} }
{{/if}}
{{/each}}';

-- Dữ liệu đầu ra 
DECLARE @PromptOutput NVARCHAR(MAX) = N'*** SCHEMA JSON BẮT BUỘC
{
  "criteria": {
    "CriteriaName": "Số Ringi",
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
WHERE ParameterID01 IN (SELECT TOP 1 APK FROM ONT1041 WHERE ParameterName ='BEM_AGENT_BEMF2000_MACHINE') --- Lấy đúng loại cấu hình DNTT (dịch vụ, máy móc, xây dựng....)
AND ParameterID07 IN (SELECT TOP 1 APK FROM ONT1041 WHERE ParameterName ='CRITERIA_RINGI_NO') --- Lấy đúng tiêu chí 
