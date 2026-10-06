from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

OUT = Path(r"E:\Asoft\AI_BEM\AI_BEM_Check_T08_09")
TMP = Path(r"E:\Asoft\AI_BEM\BEM_AI_PROJECT\.codex_tmp\code_flow_report_20261001")
IMG = TMP / "images"
IMG.mkdir(parents=True, exist_ok=True)
MD = OUT / "Noi_dung_co_che_code_doi_chieu_AI_BEM_01102026.md"
DOCX = OUT / "Bao_cao_co_che_code_doi_chieu_AI_BEM_01102026.docx"
FONT = r"C:\Windows\Fonts\times.ttf"
FONT_B = r"C:\Windows\Fonts\timesbd.ttf"

NAVY = "17365D"; BLUE = "2F75B5"; TEAL = "168A8A"; GREEN = "70AD47"; GOLD = "D6A300"; ORANGE = "ED7D31"; LIGHT = "F3F7FB"; GRAY = "5B6573"; LINE = "8095A8"
W,H=1800,950

def font(size, bold=False): return ImageFont.truetype(FONT_B if bold else FONT, size)

def draw_center(draw, xy, text, fnt, fill="#1F2933", leading=8):
    x1,y1,x2,y2=xy; maxw=x2-x1
    raw_lines = str(text).split("\n")
    lines=[]
    for raw in raw_lines:
        words=raw.split(); line=""
        if not words:
            lines.append(""); continue
        for word in words:
            test=(line+" "+word).strip()
            if draw.textbbox((0,0),test,font=fnt)[2] <= maxw:
                line=test
            else:
                if line: lines.append(line)
                line=word
        if line: lines.append(line)
    heights=[]
    for l in lines:
        b=draw.textbbox((0,0),l,font=fnt); heights.append(max(1,b[3]-b[1]))
    total=sum(heights)+leading*(len(lines)-1)
    y=y1+(y2-y1-total)/2
    for l,h in zip(lines,heights):
        b=draw.textbbox((0,0),l,font=fnt); tw=b[2]-b[0]
        draw.text((x1+(maxw-tw)/2,y),l,font=fnt,fill=fill)
        y+=h+leading

def text_box(draw, xy, text, fill=LIGHT, outline=BLUE, title=None, title_fill=None, size=30, radius=26):
    # Accept both title/color/size and title/size call forms used by the diagram definitions.
    if isinstance(title_fill, int):
        size = title_fill
        title_fill = None
    x1,y1,x2,y2=xy
    draw.rounded_rectangle(xy, radius=radius, fill="#"+fill, outline="#"+outline, width=4)
    top=y1+18
    if title:
        draw.rounded_rectangle((x1,y1,x2,y1+62), radius=radius, fill="#"+(title_fill or outline), outline="#"+(title_fill or outline))
        draw.rectangle((x1,y1+34,x2,y1+62), fill="#"+(title_fill or outline))
        draw_center(draw,(x1+14,y1+7,x2-14,y1+55), title, font(27,True), "white")
        top=y1+78
    draw_center(draw,(x1+20,top,x2-20,y2-16), text, font(size), "#1F2933")

def arrow(draw, a, b, color=LINE, width=8, head=24):
    import math
    x1,y1=a; x2,y2=b
    draw.line((x1,y1,x2,y2), fill="#"+color, width=width)
    ang=math.atan2(y2-y1,x2-x1)
    p1=(x2-head*math.cos(ang-0.50), y2-head*math.sin(ang-0.50))
    p2=(x2-head*math.cos(ang+0.50), y2-head*math.sin(ang+0.50))
    draw.polygon([(x2,y2),p1,p2],fill="#"+color)

def make_canvas(title, subtitle):
    im=Image.new("RGB",(W,H),"white"); d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,110),fill="#"+NAVY)
    d.text((58,20),title,font=font(42,True),fill="white")
    d.text((60,72),subtitle,font=font(23),fill="#DCE6F1")
    return im,d

def save(im,name):
    path=IMG/name; im.save(path, quality=95); return path

# 01
im,d=make_canvas("Bức tranh tổng thể", "Bốn khu vực cùng phối hợp để đưa kết quả đối chiếu lên ERP9")
boxes=[(80,280,430,600,"WEB ERP9","Người dùng bấm đối chiếu hoặc xem kết quả",BLUE),(510,280,860,600,"API ERP","Nhận yêu cầu từ WEB và chuyển hồ sơ sang API AI",TEAL),(940,280,1290,600,"API AI","Tạo lượt chạy, xếp hàng đợi và điều phối OCR/AI",GOLD),(1370,280,1720,600,"AI BEM","Đọc file, trích xuất và đối chiếu theo Rules",GREEN)]
for x1,y1,x2,y2,title,body,col in boxes: text_box(d,(x1,y1,x2,y2),body,"F8FBFD",col,title,col,34)
for a,b in [((430,440),(510,440)),((860,440),(940,440)),((1290,440),(1370,440))]: arrow(d,a,b,LINE,9,30)
draw_center(d,(220,690,1580,790),"Kết quả được lưu vào cơ sở dữ liệu để ERP9 hiển thị: trạng thái chạy, dữ liệu đọc được, kết quả từng tiêu chí và kết quả tổng.",font(31),"#1F2933")
save(im,"01_tong_quan_4_khu_vuc.png")

# 02
im,d=make_canvas("Luồng đối chiếu thủ công", "Một người dùng chủ động yêu cầu đối chiếu cho một phiếu ĐNTT")
steps=[("1. ERP9","Người dùng mở phiếu và bấm Đối chiếu AI",BLUE), ("2. Kiểm tra","Nếu đã có kết quả cũ, ERP9 yêu cầu xác nhận trước khi chạy lại",TEAL), ("3. Gửi hồ sơ","ERP lấy thông tin phiếu và file đính kèm, gửi sang API AI",GOLD), ("4. Xử lý nền","API AI tạo lượt chạy và đưa phiếu vào hàng đợi",ORANGE), ("5. Trả kết quả","Kết quả hoàn tất được lưu và ERP9 hiển thị lại cho người dùng",GREEN)]
x=55
for idx,(t,b,c) in enumerate(steps):
    text_box(d,(x,270,x+300,650),b,"F8FBFD",c,t,c,29)
    if idx<len(steps)-1: arrow(d,(x+300,460),(x+345,460),LINE,7,25)
    x+=345
draw_center(d,(150,755,1650,840),"Người dùng không phải chờ AI xử lý ngay trên màn hình: yêu cầu được chuyển sang xử lý nền; khi hoàn tất, kết quả được lưu để mở lại.",font(30),"#1F2933")
save(im,"02_luong_doi_chieu_thu_cong.png")

# 03
im,d=make_canvas("Luồng đối chiếu tự động", "Sau khi lịch tự động đã chọn phiếu và gửi yêu cầu, các phiếu được xếp hàng chờ xử lý")
text_box(d,(70,270,370,600),"Lịch tự động chọn danh sách phiếu đủ điều kiện", "F8FBFD",BLUE,"Lịch tự động",BLUE,31)
arrow(d,(370,435),(470,435),LINE,8,28)
text_box(d,(470,215,790,655),"Phiếu 1\nPhiếu 2\nPhiếu 3\n…", "FFF8E7",GOLD,"Hàng đợi tối đa 200 job",GOLD,34)
arrow(d,(790,435),(900,435),LINE,8,28)
text_box(d,(900,270,1210,600),"Worker lấy lần lượt job từ hàng đợi để xử lý OCR và AI", "F8FBFD",ORANGE,"Xử lý nền",ORANGE,31)
arrow(d,(1210,435),(1320,435),LINE,8,28)
text_box(d,(1320,270,1730,600),"Lưu trạng thái/kết quả từng phiếu, sau đó ERP9 hiển thị khi người dùng mở phiếu", "F8FBFD",GREEN,"DB và ERP9",GREEN,31)
draw_center(d,(130,750,1670,850),"Lưu ý: source đã xác nhận hàng đợi 200 job. Phần tiêu chí chọn phiếu, giờ chạy cụ thể và số phiếu gửi mỗi đợt cần xác nhận bằng cấu hình/job vận hành.",font(28),"#8A3E00")
save(im,"03_luong_doi_chieu_tu_dong.png")

#04
im,d=make_canvas("API AI điều phối một lượt chạy", "Đây là nơi biến yêu cầu từ ERP9 thành một lượt xử lý có thể theo dõi")
steps=[("Nhận yêu cầu","Kiểm tra dữ liệu đầu vào và file đính kèm",BLUE),("Tạo lượt chạy","Tạo bản ghi trạng thái Đang xử lý",TEAL),("Xếp hàng","Đưa phiếu vào Queue để Worker xử lý nền",GOLD),("OCR","Gửi từng file sang AI-BEM để lấy nội dung chữ",ORANGE),("AI và Rules","Nhận dữ liệu trích xuất, đối chiếu và lưu kết quả",GREEN)]
x=50
for idx,(t,b,c) in enumerate(steps):
    text_box(d,(x,245,x+310,635),b,"F8FBFD",c,t,c,30)
    if idx<4: arrow(d,(x+310,440),(x+345,440),LINE,7,25)
    x+=345
draw_center(d,(160,740,1640,840),"Nếu một file OCR lỗi, lượt xử lý cần được nhận diện là hồ sơ thiếu chứng từ; không nên coi phần file còn lại là một bộ hồ sơ đầy đủ.",font(30),"#8A3E00")
save(im,"04_api_ai_dieu_phoi.png")

#05
im,d=make_canvas("AI BEM đọc và đối chiếu hồ sơ", "AI-BEM không chỉ đọc chữ; nó còn trích thông tin và kiểm tra theo Rules")
steps=[("File chứng từ","PDF, ảnh, Excel hoặc file đính kèm",BLUE),("OCR","Đọc file thành văn bản có thể xử lý",TEAL),("LLM trích xuất","Lấy các trường như NCC, Invoice, số tiền, ngày…",GOLD),("Rules + LLM","Đối chiếu theo từng tiêu chí của loại ĐNTT",ORANGE),("Kết quả","OK/NG, % và giải thích từng tiêu chí",GREEN)]
x=50
for idx,(t,b,c) in enumerate(steps):
    text_box(d,(x,230,x+310,650),b,"F8FBFD",c,t,c,29)
    if idx<4: arrow(d,(x+310,440),(x+345,440),LINE,7,25)
    x+=345
draw_center(d,(135,760,1665,850),"Rules là quy định nghiệp vụ dùng để kết luận đúng/sai. LLM hỗ trợ đọc hiểu chứng từ và xử lý cách diễn đạt khác nhau trên file.",font(30),"#1F2933")
save(im,"05_ai_bem_doc_va_doi_chieu.png")

#06
im,d=make_canvas("Dữ liệu được lưu sau mỗi lượt chạy", "Mỗi lượt chạy cần được nhận diện riêng để không lẫn kết quả cũ và kết quả mới")
items=[("BEMT2003","Lượt chạy, trạng thái và kết quả tổng",BLUE),("BEMT2002","Nội dung OCR / dữ liệu đọc từ file",TEAL),("BEMT2005–2006","Thông tin được trích xuất từ chứng từ",GOLD),("BEMT2004","Kết quả từng tiêu chí đối chiếu",ORANGE)]
coords=[(120,260,800,430),(1000,260,1680,430),(120,570,800,740),(1000,570,1680,740)]
for (t,b,c),xy in zip(items,coords): text_box(d,xy,b,"F8FBFD",c,t,c,31)
arrow(d,(800,345),(1000,345),LINE,8,28); arrow(d,(800,655),(1000,655),LINE,8,28); arrow(d,(460,430),(460,570),LINE,8,28); arrow(d,(1340,430),(1340,570),LINE,8,28)
save(im,"06_du_lieu_luu_tru.png")

#07
im,d=make_canvas("So sánh hai cách khởi động", "Khác nhau ở cách gửi yêu cầu; sau khi vào API AI, các bước xử lý cốt lõi là như nhau")
text_box(d,(95,225,770,560),"• Một phiếu tại một thời điểm\n• Người dùng chủ động bấm\n• Phù hợp khi cần xem ngay một phiếu\n• Nếu chạy lại, cần xác nhận để tránh ghi đè kết quả cũ", "F8FBFD",BLUE,"Đối chiếu thủ công",BLUE,31)
text_box(d,(1030,225,1705,560),"• Nhiều phiếu trong một đợt\n• Lịch tự động gửi yêu cầu\n• Phù hợp xử lý khối lượng lớn\n• Cần kiểm soát điều kiện chọn phiếu và không gửi trùng", "F8FBFD",TEAL,"Đối chiếu tự động",TEAL,31)
text_box(d,(360,665,1440,815),"API AI → Queue/Worker → OCR → LLM trích xuất → Rules + LLM đối chiếu → lưu DB → ERP9 hiển thị", "F7FAFF",NAVY,"Luồng xử lý chung sau khi gửi yêu cầu",NAVY,28)
arrow(d,(430,560),(650,665),LINE,8,28)
arrow(d,(1370,560),(1150,665),LINE,8,28)
save(im,"07_so_sanh_thu_cong_tu_dong.png")
md = """# Cơ chế code đối chiếu AI BEM

Ngày cập nhật: 01/10/2026  
Phạm vi: WEB ERP9, API ERP Services, API AI và AI BEM.

## Kết luận ngắn

- Người dùng có thể bấm đối chiếu từng phiếu trên ERP9; ERP gửi hồ sơ sang API AI.
- API AI tạo một lượt chạy, lưu trạng thái ban đầu và đưa phiếu vào hàng đợi xử lý nền.
- AI BEM đọc file bằng OCR, dùng LLM trích xuất dữ liệu, rồi dùng Rules kết hợp LLM để đối chiếu.
- Kết quả tổng và kết quả từng tiêu chí được lưu vào cơ sở dữ liệu để ERP9 hiển thị.
- Source hiện có đã xác nhận cơ chế hàng đợi 200 job. Chưa xác nhận bằng source BEM cụ thể phần lịch tự động chọn phiếu, giờ chạy và số phiếu mỗi đợt; cần kiểm tra cấu hình/job vận hành.

## 1. Bản đồ bốn khu vực code

| Khu vực | Làm gì theo source đã rà soát |
|---|---|
| WEB ERP9 | Người dùng bấm đối chiếu, xác nhận chạy lại nếu có dữ liệu cũ, lấy thông tin phiếu và file đính kèm. |
| API ERP Services | Là lớp dịch vụ chung của ERP; source có cơ chế Quartz/Automation tổng quát. |
| API AI | Nhận yêu cầu, tạo lượt chạy, xếp job vào Queue, điều phối OCR/AI và lưu kết quả. |
| AI BEM | OCR đọc nội dung file, LLM trích xuất dữ liệu, Rules + LLM đối chiếu và trả kết quả. |

## 2. Luồng khi người dùng đối chiếu thủ công

1. Người dùng mở phiếu ĐNTT trên ERP9 và bấm **Đối chiếu AI**.
2. Nếu phiếu đã có dữ liệu đối chiếu, ERP9 yêu cầu xác nhận trước khi xóa/chạy lại.
3. WEB lấy thông tin phiếu, chi tiết và file đính kèm; gửi sang API AI.
4. API AI kiểm tra yêu cầu, tạo một lượt chạy có trạng thái **Đang xử lý**, sau đó đưa job vào Queue.
5. Worker xử lý nền lấy job từ Queue, gọi OCR và AI BEM.
6. Kết quả được lưu vào DB và ERP9 đọc kết quả mới nhất để hiển thị.

## 3. Luồng khi lịch tự động chạy nhiều phiếu

- Sau khi job tự động đã chọn và gửi danh sách phiếu, từng phiếu đi vào Queue của API AI giống luồng thủ công.
- Queue hiện được cấu hình sức chứa 200 job; Worker lấy job để xử lý nền.
- Khi nhiều phiếu được gửi cùng lúc, thứ tự vào Queue và năng lực OCR/LLM quyết định thời gian chờ.
- Cần xác nhận thêm tại môi trường vận hành: điều kiện chọn phiếu, giờ chạy, số phiếu gửi mỗi đợt và cách tránh gửi lại phiếu đang chạy.

## 4. Điều API AI làm trong một lượt chạy

- Kiểm tra request và file đính kèm.
- Xóa/khởi tạo dữ liệu kết quả theo lượt chạy, tạo trạng thái **PROCESSING**.
- Đưa `ReadFileJob` vào `ChannelJobQueue`.
- Worker lấy job, gọi OCR cho file; source cho phép OCR song song tối đa 7 file trong một phiếu và timeout 10 phút ở phía API AI.
- Nhận dữ liệu từ AI BEM, lưu dữ liệu trích xuất/kết quả đối chiếu; cập nhật trạng thái hoàn tất hoặc lỗi.

## 5. Điều AI BEM làm với hồ sơ

1. Nhận file từ API AI.
2. OCR chuyển file thành text.
3. LLM trích xuất dữ liệu cần dùng: NCC, Invoice, số tiền, ngày và các thông tin chứng từ khác.
4. Rules Engine kết hợp LLM đối chiếu theo từng tiêu chí của loại ĐNTT.
5. Trả kết quả OK/NG, phần trăm và chi tiết tiêu chí về API AI.

## 6. Dữ liệu lưu và cách ERP9 hiển thị

- `BEMT2003`: thông tin lượt chạy, trạng thái và kết quả tổng.
- `BEMT2002`: nội dung OCR/dữ liệu văn bản từ file.
- `BEMT2005`, `BEMT2006`: dữ liệu được trích xuất từ chứng từ.
- `BEMT2004`: kết quả đối chiếu theo từng tiêu chí.
- Khi mở kết quả, cần ưu tiên lượt chạy mới nhất của phiếu để không nhìn nhầm kết quả cũ.

## 7. So sánh thủ công và tự động

| Nội dung | Thủ công | Tự động |
|---|---|---|
| Ai khởi động | Người dùng bấm trên một phiếu | Lịch/job vận hành gửi nhiều phiếu |
| Sau khi gửi | Vào API AI và Queue | Vào API AI và Queue |
| Rủi ro cần kiểm soát | Chạy lại khi đã có kết quả | Gửi trùng, dồn nhiều phiếu cùng lúc |
| Cách theo dõi | Xem trạng thái/kết quả của phiếu | Theo dõi Queue, trạng thái từng lượt chạy và job lịch |

## 8. Điểm cần xác nhận trước khi kết luận lịch tự động

- Job nào chọn phiếu BEM để gửi tự động và lịch chạy thực tế là gì.
- Tiêu chí một phiếu được xem là đủ điều kiện để chạy.
- Khi phiếu đang chạy mà người dùng sửa dữ liệu hoặc đổi file đính kèm thì xử lý thế nào.
- Khi một file OCR lỗi thì phiếu có dừng và báo thiếu hồ sơ hay vẫn kết luận trên phần còn lại.
- Cơ chế tránh gửi trùng, chạy lại có kiểm soát và ưu tiên kết quả mới nhất.

## 9. Source kỹ thuật đã rà soát

- WEB: `01.ERP9/02.BEM/ASOFT.ERP.BEM/Scripts/JavaCustomize/BEMF2002.js`; `BEMF2000Controller.cs`.
- API AI: `ReadFileOrchestratorService.cs`; `ChannelJobQueue.cs`; `ReadFileWorker.cs`; `ReadFileBackgroundWorkflow.cs`; `OcrService.cs`; `AIHostingStartup.cs`; `FileDataHandlerController.cs`.
- AI BEM: `App/main_iis.py`; `App/Rules_AI_BEM_MEIKO.py`; các module trong `App/OCR_BE` và `App/LLMs_BE`.
- API ERP: `03.SERVICES/00.A00/ASOFT.A00.API/CoreStartup.cs` có cấu hình Quartz/Automation tổng quát.

## Phạm vi báo cáo

Tài liệu này là phân tích cơ chế code hiện có, không thay đổi code hay workflow vận hành. Những nội dung về lịch tự động chưa tìm thấy trong source BEM cụ thể được nêu là điểm cần xác nhận, không được xem là kết luận.
"""
MD.write_text(md,encoding="utf-8")

# DOCX helpers
def set_cell_shading(cell, fill):
    tcPr=cell._tc.get_or_add_tcPr(); shd=OxmlElement('w:shd'); shd.set(qn('w:fill'),fill); tcPr.append(shd)
def set_cell_border(cell, color="D9E2F3"):
    tcPr=cell._tc.get_or_add_tcPr(); borders=tcPr.first_child_found_in('w:tcBorders')
    if borders is None: borders=OxmlElement('w:tcBorders'); tcPr.append(borders)
    for edge in ('top','left','bottom','right'):
        tag='w:'+edge; el=borders.find(qn(tag))
        if el is None: el=OxmlElement(tag); borders.append(el)
        el.set(qn('w:val'),'single'); el.set(qn('w:sz'),'8'); el.set(qn('w:color'),color)
def apply_font(run, size=None, bold=None, color=None):
    run.font.name='Times New Roman'; run._element.rPr.rFonts.set(qn('w:ascii'),'Times New Roman'); run._element.rPr.rFonts.set(qn('w:hAnsi'),'Times New Roman'); run._element.rPr.rFonts.set(qn('w:eastAsia'),'Times New Roman')
    if size: run.font.size=Pt(size)
    if bold is not None: run.bold=bold
    if color: run.font.color.rgb=RGBColor.from_string(color)
def p_text(p,text,size=11,bold=False,color=None,align=None):
    if align is not None: p.alignment=align
    r=p.add_run(text); apply_font(r,size,bold,color); return r
def title(doc,text,level=1):
    p=doc.add_paragraph(); p.style='Heading %d'%level
    p.paragraph_format.space_before=Pt(14 if level==1 else 8); p.paragraph_format.space_after=Pt(6)
    r=p.add_run(text); apply_font(r,17 if level==1 else 14,True,NAVY)
    return p
def para(doc,text,bullet=False):
    p=doc.add_paragraph(style='List Bullet' if bullet else None)
    p.paragraph_format.space_after=Pt(3); p.paragraph_format.line_spacing=1.08
    p_text(p,text,11)
    return p
def image(doc,name,caption):
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    r=p.add_run(); r.add_picture(str(IMG/name),width=Inches(6.95))
    c=doc.add_paragraph(); c.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p_text(c,caption,9.5,False,GRAY)

doc=Document()
sec=doc.sections[0]; sec.top_margin=Inches(.55); sec.bottom_margin=Inches(.55); sec.left_margin=Inches(.65); sec.right_margin=Inches(.65)
styles=doc.styles
styles['Normal'].font.name='Times New Roman'; styles['Normal']._element.rPr.rFonts.set(qn('w:ascii'),'Times New Roman'); styles['Normal']._element.rPr.rFonts.set(qn('w:hAnsi'),'Times New Roman'); styles['Normal'].font.size=Pt(11)
for name in ['Heading 1','Heading 2','Title']:
    st=styles[name]; st.font.name='Times New Roman'; st._element.rPr.rFonts.set(qn('w:ascii'),'Times New Roman'); st._element.rPr.rFonts.set(qn('w:hAnsi'),'Times New Roman')
header=sec.header.paragraphs[0]; header.alignment=WD_ALIGN_PARAGRAPH.RIGHT; p_text(header,'AI BEM  |  Cơ chế code đối chiếu',9,False,GRAY)
footer=sec.footer.paragraphs[0]; footer.alignment=WD_ALIGN_PARAGRAPH.CENTER; p_text(footer,'Báo cáo phân tích code – 01/10/2026',9,False,GRAY)
p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_before=Pt(62); p.paragraph_format.space_after=Pt(18)
r=p.add_run('CƠ CHẾ CODE ĐỐI CHIẾU AI BEM'); apply_font(r,27,True,NAVY)
p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p_text(p,'Mô tả luồng xử lý từ ERP9 đến OCR, LLM và Rules',15,False,TEAL)
p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_before=Pt(30); p_text(p,'Ngày cập nhật: 01/10/2026',11,False,GRAY)
image(doc,'01_tong_quan_4_khu_vuc.png','Hình 1. Bốn khu vực phối hợp trong một lần đối chiếu AI')

title(doc,'Kết luận ngắn')
for s in ['Người dùng bấm đối chiếu tại ERP9; hồ sơ được gửi sang API AI để xử lý nền.', 'API AI tạo một lượt chạy, xếp phiếu vào Queue và điều phối các bước OCR, LLM và Rules.', 'AI BEM đọc file, trích xuất dữ liệu rồi đối chiếu; kết quả được lưu DB để ERP9 hiển thị.', 'Queue có sức chứa cấu hình 200 job. Phần lịch tự động chọn phiếu/giờ chạy cần xác nhận bằng cấu hình hoặc job vận hành.']:
    para(doc,s,True)

title(doc,'1. Bốn khu vực code làm gì')
image(doc,'01_tong_quan_4_khu_vuc.png','Hình 2. Vai trò của WEB ERP9, API ERP, API AI và AI BEM')
t=doc.add_table(rows=1,cols=2); t.alignment=WD_TABLE_ALIGNMENT.CENTER; t.style='Table Grid'; t.columns[0].width=Inches(1.55); t.columns[1].width=Inches(5.3)
for cell,txt in zip(t.rows[0].cells,['Khu vực','Vai trò dễ hiểu']):
    set_cell_shading(cell,NAVY); cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER; p=cell.paragraphs[0]; p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p_text(p,txt,11,True,'FFFFFF')
for a,b in [('WEB ERP9','Người dùng bấm đối chiếu, xác nhận chạy lại và xem kết quả.'),('API ERP Services','Lớp dịch vụ ERP; source có Quartz/Automation tổng quát.'),('API AI','Tạo lượt chạy, xếp hàng, gọi OCR/AI và lưu kết quả.'),('AI BEM','Đọc file, trích xuất thông tin và đối chiếu theo Rules.')]:
    cells=t.add_row().cells
    for i,(cell,txt) in enumerate(zip(cells,[a,b])):
        set_cell_border(cell); cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER; p=cell.paragraphs[0]; p.alignment=WD_ALIGN_PARAGRAPH.LEFT; p_text(p,txt,10.5,i==0)

title(doc,'2. Khi người dùng bấm đối chiếu thủ công')
image(doc,'02_luong_doi_chieu_thu_cong.png','Hình 3. Luồng một phiếu do người dùng chủ động yêu cầu')
for s in ['ERP9 kiểm tra phiếu; nếu có dữ liệu cũ, người dùng xác nhận trước khi chạy lại.', 'ERP lấy thông tin phiếu và file đính kèm, sau đó gửi sang API AI.', 'API AI tạo lượt chạy và đưa phiếu vào hàng đợi; xử lý tiếp diễn ở nền.', 'Khi hoàn tất, kết quả được lưu để ERP9 hiển thị lần mở sau.']:
    para(doc,s,True)

title(doc,'3. Khi lịch tự động gửi nhiều phiếu')
image(doc,'03_luong_doi_chieu_tu_dong.png','Hình 4. Nhiều phiếu chờ trong Queue trước khi Worker xử lý')
para(doc,'Sau khi lịch tự động đã chọn và gửi phiếu, luồng xử lý phía API AI giống luồng thủ công. Khác biệt là tự động có nhiều phiếu đi vào Queue cùng lúc.',True)
para(doc,'Cần xác nhận riêng: job nào chọn phiếu BEM, điều kiện chọn, giờ chạy thực tế, số phiếu mỗi đợt và cách ngăn gửi trùng.',True)

title(doc,'4. API AI xử lý một lượt chạy')
image(doc,'04_api_ai_dieu_phoi.png','Hình 5. API AI tạo lượt chạy và điều phối xử lý nền')
for s in ['Tạo trạng thái Đang xử lý để biết một phiếu đang được xử lý.', 'Queue bounded đang cấu hình 200 job; Worker lấy job xử lý nền.', 'OCR có xử lý song song tối đa 7 file trong một phiếu; timeout OCR tại API AI là 10 phút.', 'Một file OCR lỗi cần được nhận diện là hồ sơ thiếu chứng từ, không kết luận dựa trên bộ file còn lại.']:
    para(doc,s,True)

title(doc,'5. AI BEM đọc file và đối chiếu')
image(doc,'05_ai_bem_doc_va_doi_chieu.png','Hình 6. Chuỗi xử lý từ file chứng từ đến kết quả AI')
para(doc,'OCR biến file thành text. LLM dùng text để trích thông tin. Rules là quy định nghiệp vụ dùng để kết luận từng tiêu chí; LLM hỗ trợ đọc hiểu nội dung chứng từ.',True)

title(doc,'6. Kết quả được lưu để ERP9 hiển thị')
image(doc,'06_du_lieu_luu_tru.png','Hình 7. Nhóm dữ liệu lưu lại sau một lượt chạy')
for s in ['BEMT2003: lượt chạy, trạng thái và kết quả tổng.', 'BEMT2002: text OCR/dữ liệu đọc từ file.', 'BEMT2005–BEMT2006: dữ liệu được trích xuất từ chứng từ.', 'BEMT2004: kết quả từng tiêu chí đối chiếu.', 'Khi mở phiếu, nên ưu tiên lượt chạy mới nhất để không xem nhầm kết quả cũ.']:
    para(doc,s,True)

title(doc,'7. Thủ công và tự động khác nhau thế nào')
image(doc,'07_so_sanh_thu_cong_tu_dong.png','Hình 8. Khác biệt ở cách gửi yêu cầu, các bước xử lý cốt lõi giống nhau')

title(doc,'8. Nội dung cần xác nhận về lịch tự động')
for s in ['Phiếu BEM đủ điều kiện chạy tự động là phiếu nào và do job nào chọn.', 'Giờ chạy, số phiếu mỗi đợt và cơ chế ưu tiên khi có nhiều phiếu.', 'Cách xử lý khi người dùng sửa phiếu hoặc đổi/thêm/xóa file lúc phiếu đang chạy.', 'Cách ngăn gửi trùng và cách chạy lại có kiểm soát.', 'Cách báo lỗi một file OCR để không kết luận hồ sơ là đầy đủ.']:
    para(doc,s,True)

title(doc,'9. Source đã rà soát')
for s in [r'WEB: E:\ASOFT ERP9.9.1\40.PROJECTS\MEIKO\01.ERP9\02.BEM\ASOFT.ERP.BEM\Scripts\JavaCustomize\BEMF2002.js và BEMF2000Controller.cs.', r'API AI: ReadFileOrchestratorService.cs, ChannelJobQueue.cs, ReadFileWorker.cs, ReadFileBackgroundWorkflow.cs, OcrService.cs, AIHostingStartup.cs.', r'AI BEM: E:\Asoft\AI_BEM\BEM_AI_PROJECT\App\main_iis.py, Rules_AI_BEM_MEIKO.py, OCR_BE và LLMs_BE.', r'API ERP: CoreStartup.cs có Quartz/Automation tổng quát; chưa đủ căn cứ để kết luận cơ chế chọn phiếu BEM theo lịch.']:
    para(doc,s,True)

title(doc,'Phạm vi báo cáo')
para(doc,'Tài liệu này chỉ phân tích cơ chế code hiện có, chưa thay đổi code hoặc workflow vận hành. Nội dung chưa thấy trong source BEM cụ thể được ghi là cần xác nhận, không xem là kết luận.',True)
doc.save(DOCX)
print(MD)
print(DOCX)



