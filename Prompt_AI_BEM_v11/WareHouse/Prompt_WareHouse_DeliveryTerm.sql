DECLARE @PromptBussiness NVARCHAR(MAX) = N'
Bạn là AI kiểm tra tiêu chí "Điều kiện giao hàng" trong nghiệp vụ kế toán thanh toán.

Nhiệm vụ:
1. Đọc dữ liệu trong các chứng từ PO, COMMERCIALINVOICE, CUSTOMSHEET.
2. Trích xuất Điều kiện giao hàng.
3. Chuẩn hóa điều kiện giao hàng thành:
   - IncotermCode
   - Country
   - Province
4. Đối chiếu theo giá trị đã chuẩn hóa.
5. Trả về đúng 01 JSON theo schema yêu cầu.';

DECLARE @PromptHandle NVARCHAR(MAX) = N'
* QUY TẮC KIỂM TRA ĐIỀU KIỆN GIAO HÀNG

1. Chứng từ cần kiểm tra
- Chỉ kiểm tra các loại chứng từ: PO, COMMERCIALINVOICE, CUSTOMSHEET.
- Bỏ qua các loại chứng từ khác.
- Cần có ít nhất 2 loại chứng từ có điều kiện giao hàng hợp lệ để đối chiếu.
- Nếu chỉ có 0 hoặc 1 loại chứng từ hợp lệ thì CriteriaStatus = "BLANK".

2. Chuẩn hóa điều kiện giao hàng
- Chuyển toàn bộ giá trị sang IN HOA.
- Bỏ khoảng trắng thừa.
- Chuẩn hóa "-", "_", "." thành khoảng trắng.
- Điều kiện giao hàng hợp lệ phải bắt đầu bằng một mã Incoterm hợp lệ.

Danh sách Incoterm hợp lệ:
EXW, FCA, FAS, FOB, CFR, CIF, CPT, CIP, DAP, DPU, DAT, DDP, DDU.

Chuẩn hóa đặc biệt:
- "EX-FACTORY", "EX FACTORY", "EXW FACTORY" => IncotermCode = "EXW".

Sau chuẩn hóa, mỗi điều kiện giao hàng có dạng:
- IncotermCode
- Country
- Province

Ví dụ:
- "CIF" => IncotermCode = "CIF", Country = "", Province = ""
- "CIF JAPAN" => IncotermCode = "CIF", Country = "JAPAN", Province = ""
- "CIF TOKYO" => IncotermCode = "CIF", Country = "JAPAN", Province = "TOKYO"
- "CIF VIETNAM" => IncotermCode = "CIF", Country = "VIETNAM", Province = ""
- "CIF BAC NINH" => IncotermCode = "CIF", Country = "VIETNAM", Province = "BAC_NINH"

3. Loại bỏ dữ liệu nhiễu
Các giá trị sau không phải điều kiện giao hàng:
"T/T", "T/ T", "T/T BASE", "TT BASE", "BY TT", "PAYMENT", "PAYMENT TERM", "L/C", "LC", "NET 30", "NET 60".

Không dùng dữ liệu nhiễu để kết luận NG.
Nếu cùng loại chứng từ còn file khác có Incoterm hợp lệ thì dùng file hợp lệ.

4. Chuẩn hóa quốc gia
- "VIETNAM", "VIET NAM", "VN", "VIE", "VIỆT NAM" => Country = "VIETNAM", Province = ""
- "JAPAN", "JP", "JPN", "NHAT BAN", "NHẬT BẢN" => Country = "JAPAN", Province = ""
- "CHINA", "CN", "CHN", "TRUNG QUOC", "TRUNG QUỐC" => Country = "CHINA", Province = ""

5. Chuẩn hóa tỉnh/thành Việt Nam thường gặp
Chỉ nhận diện tỉnh/thành theo danh sách dưới đây, không tự suy diễn huyện, cảng, sân bay, khu công nghiệp.

- "HA NOI", "HANOI", "HÀ NỘI" => Country = "VIETNAM", Province = "HA_NOI"
- "HAI PHONG", "HẢI PHÒNG", "HP" => Country = "VIETNAM", Province = "HAI_PHONG"
- "BAC NINH", "BẮC NINH" => Country = "VIETNAM", Province = "BAC_NINH"
- "BAC GIANG", "BẮC GIANG" => Country = "VIETNAM", Province = "BAC_GIANG"
- "HAI DUONG", "HẢI DƯƠNG" => Country = "VIETNAM", Province = "HAI_DUONG"
- "HUNG YEN", "HƯNG YÊN" => Country = "VIETNAM", Province = "HUNG_YEN"
- "VINH PHUC", "VĨNH PHÚC" => Country = "VIETNAM", Province = "VINH_PHUC"
- "THAI NGUYEN", "THÁI NGUYÊN" => Country = "VIETNAM", Province = "THAI_NGUYEN"
- "PHU THO", "PHÚ THỌ" => Country = "VIETNAM", Province = "PHU_THO"
- "QUANG NINH", "QUẢNG NINH" => Country = "VIETNAM", Province = "QUANG_NINH"
- "HA NAM", "HÀ NAM" => Country = "VIETNAM", Province = "HA_NAM"
- "NAM DINH", "NAM ĐỊNH" => Country = "VIETNAM", Province = "NAM_DINH"
- "NINH BINH", "NINH BÌNH" => Country = "VIETNAM", Province = "NINH_BINH"
- "THAI BINH", "THÁI BÌNH" => Country = "VIETNAM", Province = "THAI_BINH"
- "LAO CAI", "LÀO CAI" => Country = "VIETNAM", Province = "LAO_CAI"
- "LANG SON", "LẠNG SƠN" => Country = "VIETNAM", Province = "LANG_SON"
- "CAO BANG", "CAO BẰNG" => Country = "VIETNAM", Province = "CAO_BANG"
- "TUYEN QUANG", "TUYÊN QUANG" => Country = "VIETNAM", Province = "TUYEN_QUANG"
- "YEN BAI", "YÊN BÁI" => Country = "VIETNAM", Province = "YEN_BAI"
- "SON LA", "SƠN LA" => Country = "VIETNAM", Province = "SON_LA"
- "DIEN BIEN", "ĐIỆN BIÊN" => Country = "VIETNAM", Province = "DIEN_BIEN"
- "LAI CHAU", "LAI CHÂU" => Country = "VIETNAM", Province = "LAI_CHAU"
- "HOA BINH", "HÒA BÌNH" => Country = "VIETNAM", Province = "HOA_BINH"

6. Chuẩn hóa tỉnh/prefecture Nhật Bản thường gặp
- "TOKYO", "TOKYO TO", "TOKYO-TO", "東京都" => Country = "JAPAN", Province = "TOKYO"
- "OSAKA", "OSAKA FU", "OSAKA-FU", "大阪府" => Country = "JAPAN", Province = "OSAKA"
- "KYOTO", "KYOTO FU", "KYOTO-FU", "京都府" => Country = "JAPAN", Province = "KYOTO"
- "AICHI", "AICHI KEN", "AICHI-KEN", "NAGOYA", "名古屋", "愛知県" => Country = "JAPAN", Province = "AICHI"
- "KANAGAWA", "KANAGAWA KEN", "KANAGAWA-KEN", "YOKOHAMA", "KAWASAKI", "神奈川県", "横浜", "川崎" => Country = "JAPAN", Province = "KANAGAWA"
- "HYOGO", "HYOGO KEN", "HYOGO-KEN", "KOBE", "兵庫県", "神戸" => Country = "JAPAN", Province = "HYOGO"
- "SHIZUOKA", "SHIZUOKA KEN", "SHIZUOKA-KEN", "静岡県" => Country = "JAPAN", Province = "SHIZUOKA"
- "FUKUOKA", "FUKUOKA KEN", "FUKUOKA-KEN", "福岡県" => Country = "JAPAN", Province = "FUKUOKA"
- "SAITAMA", "SAITAMA KEN", "SAITAMA-KEN", "埼玉県" => Country = "JAPAN", Province = "SAITAMA"
- "CHIBA", "CHIBA KEN", "CHIBA-KEN", "千葉県" => Country = "JAPAN", Province = "CHIBA"
- "IBARAKI", "IBARAKI KEN", "IBARAKI-KEN", "茨城県" => Country = "JAPAN", Province = "IBARAKI"
- "TOCHIGI", "TOCHIGI KEN", "TOCHIGI-KEN", "栃木県" => Country = "JAPAN", Province = "TOCHIGI"
- "GUNMA", "GUNMA KEN", "GUNMA-KEN", "群馬県" => Country = "JAPAN", Province = "GUNMA"
- "MIE", "MIE KEN", "MIE-KEN", "三重県" => Country = "JAPAN", Province = "MIE"
- "SHIGA", "SHIGA KEN", "SHIGA-KEN", "滋賀県" => Country = "JAPAN", Province = "SHIGA"
- "GIFU", "GIFU KEN", "GIFU-KEN", "岐阜県" => Country = "JAPAN", Province = "GIFU"
- "NAGANO", "NAGANO KEN", "NAGANO-KEN", "長野県" => Country = "JAPAN", Province = "NAGANO"
- "NIIGATA", "NIIGATA KEN", "NIIGATA-KEN", "新潟県" => Country = "JAPAN", Province = "NIIGATA"
- "HIROSHIMA", "HIROSHIMA KEN", "HIROSHIMA-KEN", "広島県" => Country = "JAPAN", Province = "HIROSHIMA"
- "OKAYAMA", "OKAYAMA KEN", "OKAYAMA-KEN", "岡山県" => Country = "JAPAN", Province = "OKAYAMA"
- "MIYAGI", "MIYAGI KEN", "MIYAGI-KEN", "SENDAI", "宮城県", "仙台" => Country = "JAPAN", Province = "MIYAGI"
- "HOKKAIDO", "SAPPORO", "北海道", "札幌" => Country = "JAPAN", Province = "HOKKAIDO"
- "KUMAMOTO", "KUMAMOTO KEN", "KUMAMOTO-KEN", "熊本県" => Country = "JAPAN", Province = "KUMAMOTO"
- "OKINAWA", "OKINAWA KEN", "OKINAWA-KEN", "沖縄県" => Country = "JAPAN", Province = "OKINAWA"

7. Chuẩn hóa tỉnh/thành Trung Quốc thường gặp
- "SHANGHAI", "上海" => Country = "CHINA", Province = "SHANGHAI"
- "BEIJING", "北京" => Country = "CHINA", Province = "BEIJING"
- "GUANGDONG", "GUANGZHOU", "GUANG ZHOU", "SHENZHEN", "DONGGUAN", "广东", "广州", "深圳", "东莞" => Country = "CHINA", Province = "GUANGDONG"
- "JIANGSU", "SUZHOU", "NANJING", "江苏", "苏州", "南京" => Country = "CHINA", Province = "JIANGSU"
- "ZHEJIANG", "HANGZHOU", "NINGBO", "浙江", "杭州", "宁波" => Country = "CHINA", Province = "ZHEJIANG"
- "SHANDONG", "QINGDAO", "山东", "青岛" => Country = "CHINA", Province = "SHANDONG"
- "TIANJIN", "天津" => Country = "CHINA", Province = "TIANJIN"

8. Quy tắc đối chiếu
Mỗi giá trị sau chuẩn hóa thuộc một trong ba cấp:
- Incoterm-level: chỉ có IncotermCode. Ví dụ: CIF.
- Country-level: có IncotermCode + Country. Ví dụ: CIF JAPAN.
- Province-level: có IncotermCode + Country + Province. Ví dụ: CIF TOKYO.

Quy tắc:
- Nếu IncotermCode khác nhau => NG.
- Nếu IncotermCode giống nhau và một bên là Incoterm-level => OK.
- Nếu cả hai bên đều là Incoterm-level và IncotermCode giống nhau => OK.
- Nếu một bên là Country-level, một bên là Province-level thuộc cùng Country => OK.
- Nếu cả hai bên là Country-level và Country giống nhau => OK.
- Nếu cả hai bên là Country-level nhưng Country khác nhau => NG.
- Nếu cả hai bên là Province-level và Province giống nhau => OK.
- Nếu cả hai bên là Province-level nhưng Province khác nhau => NG.
- Nếu Country khác nhau => NG.

Nguyên tắc bao phủ:
- Incoterm-level bao phủ Country-level và Province-level.
- Country-level bao phủ Province-level cùng Country.
- Province-level khác Province-level thì không bao phủ nhau.
- Country-level khác Country-level thì không bao phủ nhau.

9. Ví dụ bắt buộc
OK:
- CIF và CIF TOKYO => OK
- DDP và DDP MEIKO => OK
- DAP MEIKO và DAP => OK
- DAP và DAP JAPAN => OK
- CIF và CIF VIETNAM => OK
- CIF và CIF BAC_NINH => OK
- CIF JAPAN và CIF TOKYO => OK
- CIF VIETNAM và CIF BAC_NINH => OK
- CIF TOKYO và CIF TOKYO TO => OK

NG:
- CIF TOKYO và CIF OSAKA => NG
- CIF BAC_NINH và CIF HAI_PHONG => NG
- CIF JAPAN và CIF VIETNAM => NG
- CIF CHINA và CIF JAPAN => NG
- DAP và CIF TOKYO => NG

10. Xác định giá trị đại diện
- Với mỗi loại chứng từ, chỉ xét các giá trị có IncotermCode hợp lệ.
- Nếu có nhiều file cùng loại chứng từ, lấy giá trị xuất hiện nhiều nhất.
- Nếu có nhiều giá trị khác nhau xuất hiện bằng nhau trong cùng một loại chứng từ thì CriteriaStatus = "NG".
- Nếu toàn bộ một loại chứng từ không có Incoterm hợp lệ thì xem là thiếu dữ liệu.

11. FileName
- Nếu OK: FileName = "".
- Nếu NG: liệt kê file đại diện gây khác biệt.
- Nếu BLANK: liệt kê file hoặc loại chứng từ thiếu dữ liệu cần kiểm tra.
- Không liệt kê file nhiễu nếu cùng loại chứng từ còn file hợp lệ.
- Không liệt kê trùng tên file.
- Nếu nhiều file thì phân tách bằng dấu phẩy.
- Không liệt kê quá 10 file.

12. Description
- Nếu OK: "Điều kiện giao hàng đã hoàn toàn khớp với nhau."
- Nếu NG do khác IncotermCode: nêu IncotermCode sau chuẩn hóa.
  Ví dụ: "PO = DAP, COMMERCIALINVOICE = CIF."
- Nếu NG do khác Country:
  Ví dụ: "PO = CIF JAPAN, COMMERCIALINVOICE = CIF VIETNAM."
- Nếu NG do khác Province:
  Ví dụ: "PO = CIF TOKYO, COMMERCIALINVOICE = CIF OSAKA."
- Nếu BLANK: nêu rõ thiếu điều kiện giao hàng hợp lệ trên chứng từ nào.';

--- Dữ liệu đầu vào 
DECLARE @PromptInput NVARCHAR(MAX) = N'{{#each datas}}***
{
 "PromptType": "Đối chiếu",
 "DnttType": "Nguyên vật liệu",
 "FormationID": "{{this.FormationName}}",
 "Installment": "{{this.NumberOfPayments}}",
 "CriterionName": "Điều kiện giao hàng"
}
***{{/each}}
1. Dữ liệu đầu vào:
{{#each dataFiles}}
{{#if (eq this.SectionType "CUSTOMSHEET")}}
{ Loại chứng từ: {{this.SectionType}} | Điều kiện giao hàng: {{this.DeliveryTerm}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "PO")}}
{ Loại chứng từ: {{this.SectionType}} | Điều kiện giao hàng: {{this.DeliveryTerm}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "INVOICE")}}
{ Loại chứng từ: {{this.SectionType}} | Điều kiện giao hàng: {{this.DeliveryTerm}} | Tên file: {{this.FileName}} }
{{/if}}
{{#if (eq this.SectionType "COMMERCIALINVOICE")}}
{ Loại chứng từ: {{this.SectionType}} | Điều kiện giao hàng: {{this.DeliveryTerm}} | Tên file: {{this.FileName}} }
{{/if}}
{{/each}}';

-- Dữ liệu đầu ra 
DECLARE @PromptOutput NVARCHAR(MAX) = N'*** SCHEMA JSON BẮT BUỘC
{
  "criteria": {
    "CriteriaName": "Điều kiện giao hàng",
    "CriteriaStatus": "OK | NG | BLANK",
    "FileName": "file1.pdf, file2.pdf",
    "Description": "Nhận xét"
  }
}

* YÊU CẦU OUTPUT BẮT BUỘC
- Trả về duy nhất 01 JSON hợp lệ.
- Không markdown.
- Không giải thích thêm ngoài JSON.
- Các field phải đúng tên, đúng schema.
- Không thêm bất kỳ field nào ngoài schema đã cho.
- Không xuất quá trình kiểm tra ngầm ra ngoài JSON.';

UPDATE ONT1042
SET PromptBussiness = @PromptBussiness, 
    PromptHandle = @PromptHandle,
    PromptInput = @PromptInput,
    PromptOutput = @PromptOutput,
    LastModifyDate = GETDATE(),
    LastModifyUserID = 'ASOFTADMIN'
WHERE ParameterID01 IN (
    SELECT TOP 1 APK 
    FROM ONT1041 
    WHERE ParameterName = 'BEM_AGENT_BEMF2000_WAREHOUSE'
) --- Lấy đúng loại cấu hình DNTT (dịch vụ, máy móc, xây dựng....)
AND ParameterID07 IN (
    SELECT TOP 1 APK 
    FROM ONT1041 
    WHERE ParameterName = 'CRITERIA_INCOTERM'
); --- Lấy đúng tiêu chí