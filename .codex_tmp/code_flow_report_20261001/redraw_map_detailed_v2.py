from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT=Path(r"E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\Temp\code_flow_simplified_20261001\01_ban_do_van_hanh.png")
FONT=r'C:\Windows\Fonts\times.ttf'; FONT_B=r'C:\Windows\Fonts\timesbd.ttf'
NAVY='#17365D'; BLUE='#2F75B5'; TEAL='#168A8A'; GOLD='#D6A300'; ORANGE='#ED7D31'; PURPLE='#7030A0'; LINE='#6B8299'; DARK='#1F2933'; DB_BG='#F6F0FA'
W,H=2200,1250

def f(n,b=False): return ImageFont.truetype(FONT_B if b else FONT,n)
def center(d,xy,text,font,fill=DARK,leading=5):
    x1,y1,x2,y2=xy; lines=[]
    for raw in str(text).split('\n'):
        words=raw.split(); line=''
        if not words: lines.append(''); continue
        for word in words:
            t=(line+' '+word).strip()
            if d.textbbox((0,0),t,font=font)[2] <= x2-x1: line=t
            else:
                if line: lines.append(line)
                line=word
        if line: lines.append(line)
    hs=[max(1,d.textbbox((0,0),s,font=font)[3]-d.textbbox((0,0),s,font=font)[1]) for s in lines]
    y=y1+((y2-y1)-(sum(hs)+leading*(len(lines)-1)))/2
    for s,h in zip(lines,hs):
        b=d.textbbox((0,0),s,font=font)
        d.text((x1+(x2-x1-(b[2]-b[0]))/2,y),s,font=font,fill=fill)
        y += h+leading

def box(d,xy,title,body,color,sz=22,fill='white'):
    x1,y1,x2,y2=xy
    d.rounded_rectangle(xy,20,fill=fill,outline=color,width=4)
    d.rounded_rectangle((x1,y1,x2,y1+52),20,fill=color,outline=color)
    d.rectangle((x1,y1+28,x2,y1+52),fill=color)
    center(d,(x1+8,y1+5,x2-8,y1+47),title,f(23,True),'white')
    center(d,(x1+12,y1+62,x2-12,y2-10),body,f(sz),DARK)

def small(d,xy,text,color='#5B6573'):
    d.rounded_rectangle(xy,8,fill='white',outline='#D8E1EA',width=2)
    center(d,(xy[0]+5,xy[1]+2,xy[2]-5,xy[3]-2),text,f(17,True),color)

def arrow(d,a,b,color=LINE,w=7,head=22,dashed=False):
    import math
    x1,y1=a; x2,y2=b
    if dashed:
        n=10
        for i in range(n):
            if i%2==0:
                t=i/n; u=(i+1)/n
                d.line((x1+(x2-x1)*t,y1+(y2-y1)*t,x1+(x2-x1)*u,y1+(y2-y1)*u),fill=color,width=w)
    else:
        d.line((x1,y1,x2,y2),fill=color,width=w)
    ang=math.atan2(y2-y1,x2-x1)
    p1=(x2-head*math.cos(ang-.52),y2-head*math.sin(ang-.52)); p2=(x2-head*math.cos(ang+.52),y2-head*math.sin(ang+.52))
    d.polygon([(x2,y2),p1,p2],fill=color)

def elbow(d,pts,color=LINE,w=7,head=22,dashed=False):
    for i in range(len(pts)-2):
        arrowless_line(d,pts[i],pts[i+1],color,w,dashed)
    arrow(d,pts[-2],pts[-1],color,w,head,dashed)

def arrowless_line(d,a,b,color,w,dashed=False):
    x1,y1=a; x2,y2=b
    if dashed:
        n=10
        for i in range(n):
            if i%2==0:
                t=i/n; u=(i+1)/n
                d.line((x1+(x2-x1)*t,y1+(y2-y1)*t,x1+(x2-x1)*u,y1+(y2-y1)*u),fill=color,width=w)
    else:
        d.line((x1,y1,x2,y2),fill=color,width=w)

im=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(im)
d.rectangle((0,0,W,105),fill=NAVY)
d.text((45,17),'Bản đồ vận hành AI BEM',font=f(42,True),fill='white')
d.text((47,69),'Nhìn theo 2 lớp: hệ thống nào xử lý ở trên, DB lưu gì ở dưới',font=f(22),fill='#DCE6F1')

# Section labels
d.rounded_rectangle((35,125,2165,745),22,fill='#F8FBFD',outline='#D9E2F3',width=2)
d.rounded_rectangle((35,790,2165,1185),22,fill='#FBF8FF',outline=PURPLE,width=3)
center(d,(45,135,245,170),'Lớp xử lý',f(25,True),NAVY)
center(d,(45,800,245,835),'Lớp DB',f(25,True),PURPLE)

# Top flow boxes
web=(70,235,360,430); api=(70,495,360,665); quartz=(445,495,735,665); run=(820,260,1110,430); queue=(820,505,1110,665); worker=(820,690,1110,735); ocr=(1225,235,1515,405); llm=(1225,465,1515,635); rules=(1225,695,1515,745); display=(1650,320,2075,520)
box(d,web,'WEB ERP9','Người dùng bấm\nĐối chiếu thủ công',BLUE,23)
box(d,api,'ERP Controller','Lấy phiếu + chi tiết\nLấy file đính kèm\nGửi request sang API-AI',BLUE,21)
box(d,quartz,'API ERP','Quartz/lịch chung\nChưa xác nhận\njob BEM cụ thể',TEAL,21)
box(d,run,'API-AI Run','Nhận request\nTạo lượt chạy\nBEMT2003 = PROCESSING',GOLD,21)
box(d,queue,'Queue RAM','ChannelJobQueue\nTối đa 200 job\nKhông nằm trong DB',GOLD,21)
box(d,worker,'Worker','Lấy job và gọi AI',GOLD,19)
box(d,ocr,'AI Python OCR','Route /ocr\nFile → text',ORANGE,22)
box(d,llm,'AI Python LLM','Trích xuất dữ liệu\ntừ text OCR',ORANGE,22)
box(d,rules,'Rules + LLM','Đối chiếu tiêu chí\nOK/NG + giải thích',ORANGE,21)
box(d,display,'ERP9 hiển thị','Đọc kết quả từ DB\ncho người dùng xem',BLUE,23)

# Top flow arrows no crossing
arrow(d,(215,430),(215,495))
elbow(d,[(360,580),(590,580),(590,345),(820,345)])
arrow(d,(735,580),(820,580),dashed=True)
small(d,(430,420,755,462),'Thủ công: WEB/ERP Controller gọi API-AI')
small(d,(430,680,760,722),'Tự động: API ERP gọi API-AI khi có job BEM', '#8A3E00')
arrow(d,(965,430),(965,505))
arrow(d,(965,665),(965,690))
elbow(d,[(1110,715),(1170,715),(1170,320),(1225,320)])
arrow(d,(1370,405),(1370,465))
arrow(d,(1370,635),(1370,695))
elbow(d,[(1515,720),(1580,720),(1580,420),(1650,420)])

# DB boxes aligned under source stages
db1=(555,890,845,1045); db2=(930,890,1220,1045); db3=(1305,890,1595,1045); db4=(1680,890,1970,1045); db5=(760,1080,1760,1160)
box(d,db1,'BEMT2003','Lượt chạy\nPROCESSING',PURPLE,22,fill='white')
box(d,db2,'BEMT2002','Text OCR\nđọc từ file',PURPLE,22,fill='white')
box(d,db3,'BEMT2005 / 2006','Dữ liệu trích xuất\ntừ chứng từ',PURPLE,21,fill='white')
box(d,db4,'BEMT2004','Kết quả từng tiêu chí\nOK/NG + giải thích',PURPLE,21,fill='white')
box(d,db5,'BEMT2003 cập nhật','COMPLETED hoặc FAILED • Kết quả tổng OK/NG • %',PURPLE,22,fill='white')
# Down arrows straight from corresponding steps
elbow(d,[(965,430),(965,815),(700,815),(700,890)],color=PURPLE,w=5)
elbow(d,[(1370,405),(1370,815),(1075,815),(1075,890)],color=PURPLE,w=5)
elbow(d,[(1370,635),(1370,850),(1450,850),(1450,890)],color=PURPLE,w=5)
elbow(d,[(1515,720),(1825,720),(1825,890)],color=PURPLE,w=5)
arrow(d,(1825,1045),(1490,1080),color=PURPLE,w=5)
arrow(d,(700,1045),(1030,1080),color=PURPLE,w=5)

# Bottom notes
center(d,(75,1188,2125,1238),'Cần nhớ: Queue ở API-AI/RAM. OCR, LLM và Rules ở AI Python. DB chỉ lưu trạng thái/kết quả để ERP9 đọc lại và hiển thị.',f(24,True),'#8A3E00')

im.save(OUT)
print(OUT)
