import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";
const inputPath = "E:/Asoft/AI_BEM/AI_BEM_Check_T08_09/DATA_BEM AI_MEIKO_25092026.xlsx";
const outputPath = "E:/Asoft/AI_BEM/AI_BEM_Check_T08_09/DATA_BEM AI_MEIKO_25092026.artifact-tmp.xlsx";
const updates = [
  ["- Tình huống: Tên NCC trên các chứng từ viết khác nhau, nhưng thực tế là cùng một NCC. Ví dụ: “ABC CO., LTD” và “ABC Company Limited”.\n- Cách xử lý: Nếu cùng mã NCC hoặc cùng địa chỉ thì xem là cùng NCC và kết quả OK. Nếu không có căn cứ xác định là cùng NCC thì NG.\n- Cần xác nhận: Khi có mã NCC nội bộ, có ưu tiên kiểm tra theo mã NCC không?"],
  ["- Tình huống: Một tờ khai hoặc bảng kê có nhiều Invoice, nhưng ĐNTT chỉ thanh toán một số Invoice.\n- Cách xử lý: Chỉ kiểm tra đúng Invoice ghi trên ĐNTT; không tính các Invoice khác trong cùng hồ sơ.\n- Ví dụ: NVL/09/2026/0003 chỉ thanh toán 2 Invoice tổng 22.846 USD.\n- Cần xác nhận: Hàng nội địa có ĐNTT, VAT và PO khớp thì có được OK khi không có tờ khai không?"],
  ["- Tình huống: Một tờ khai hoặc bảng kê có nhiều Invoice với các ngày khác nhau.\n- Cách xử lý: Chỉ lấy ngày của Invoice đang thanh toán trên ĐNTT.\n- Ví dụ: NVL/09/2026/0001 thanh toán Invoice ngày 06/07/2026; tờ khai cũng ghi Invoice này ngày 06/07/2026 thì OK.\n- Cần xác nhận: Nếu có hóa đơn điều chỉnh hoặc thay thế thì dùng ngày của hóa đơn nào?"],
  ["- Tình huống: Ringi, PO, hợp đồng hoặc tờ khai có tổng tiền lớn, nhưng ĐNTT chỉ thanh toán một phần.\n- Cách xử lý: Chỉ lấy số tiền của đúng NCC, Invoice và lần thanh toán trên ĐNTT; không cộng trùng tiền trên nhiều chứng từ.\n- Ví dụ: Ringi 100.000 USD, thanh toán lần 1 là 40.000 USD và lần 2 là 60.000 USD; từng phiếu vẫn OK nếu tổng không vượt 100.000 USD.\n- Cần xác nhận: Có kiểm tra tổng số tiền đã thanh toán theo Ringi, PO hoặc hợp đồng không?"],
  ["- Tình huống: Invoice có cả số tiền USD và số tiền quy đổi VND.\n- Cách xử lý: Kiểm tra theo loại tiền thanh toán trên ĐNTT; không dùng số tiền quy đổi hoặc tiền thuế để đối chiếu.\n- Ví dụ: ĐNTT thanh toán USD thì so với số tiền USD trên Invoice.\n- Cần xác nhận: Nếu một ĐNTT có nhiều Invoice khác loại tiền thì có kiểm tra riêng từng Invoice không?"],
  ["- Tình huống: Điều kiện giao hàng giống nhau nhưng địa điểm ghi khác nhau, ví dụ “FCA NARITA” và “FCA JAPAN”.\n- Cách xử lý: Nếu cùng điều kiện chính FCA thì OK. Nếu điều kiện chính khác nhau, ví dụ CIF và DDP, thì NG.\n- Cần xác nhận: Có bắt buộc địa điểm đi kèm điều kiện giao hàng phải giống nhau không?"],
  ["- Tình huống: PO ghi điều khoản thanh toán AMS30, AMS60 hoặc AMS90.\n- Cách xử lý: Lấy ngày hàng đến hoặc ngày hoàn thành kiểm tra, cộng số ngày quy định, sau đó lấy ngày cuối tháng làm hạn thanh toán.\n- Ví dụ: Hàng đến ngày 13/09, AMS30 thì hạn thanh toán là 31/10.\n- Cần xác nhận: Nếu điều khoản là “90 after B/L” nhưng thiếu B/L thì dùng ngày nào để tính hạn? Phiếu đặt cọc có cần Invoice và tờ khai không?"],
  ["- Tình huống: PO ghi AMS90 nhưng tờ khai không có ngày hàng đến hoặc ngày hoàn thành kiểm tra.\n- Cách xử lý: Hàng nhập khẩu thiếu ngày này thì chuyển kiểm tra thủ công. Hàng nội địa không có tờ khai thì bỏ qua tiêu chí này.\n- Cần xác nhận: Khi tờ khai có cả ngày hàng đến và ngày hoàn thành kiểm tra thì dùng ngày nào để tính hạn thanh toán?"],
  ["- Tình huống: VAT điện tử có chữ ký số nhưng không có dấu đỏ.\n- Cách xử lý: Chấp nhận VAT có chữ ký số hợp lệ. Nếu chữ ký hoặc con dấu không nhìn rõ thì chuyển kiểm tra thủ công.\n- Cần xác nhận: PO, hợp đồng, Invoice và các chứng từ trong nước/nước ngoài bắt buộc phải có chữ ký hoặc con dấu nào?"],
];
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheet = workbook.worksheets.getItem("Rules_Nguyên vật liệu");
sheet.getRange("O4:O12").values = updates;
sheet.getRange("O4:O12").format.wrapText = true;
sheet.getRange("O4:O12").format.verticalAlignment = "top";
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
