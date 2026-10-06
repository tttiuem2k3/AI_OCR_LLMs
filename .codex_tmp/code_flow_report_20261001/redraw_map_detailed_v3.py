from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
OUT=Path(r"E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\Temp\code_flow_simplified_20261001\01_ban_do_van_hanh.png")
FONT=r'C:\Windows\Fonts\times.ttf'; FONT_B=r'C:\Windows\Fonts\timesbd.ttf'
NAVY='#17365D'; BLUE='#2F75B5'; TEAL='#168A8A'; GOLD='#D6A300'; ORANGE='#ED7D31'; PURPLE='#7030A0'; LINE='#6B8299'; DARK='#1F2933'
W,H=2200,1320

def f(n,b=False): return ImageFont.truetype(FONT_B if b else FONT,n)
def center(d,xy,text,font,fill=DARK,leading=5):
 x1,y1,x2,y2=xy; lines=[]
 for raw in str(text).split('\n'):
  words=raw.split(); line=''
  if not words: lines.append(''); continue
  for word in words:
   test=(line+' '+word).strip()
   if d.textbbox((0,0),test,font=font)[2]<=x2-x1: line=test
   else:
    if line: lines.append(line)
    line=word
  if line: lines.append(line)
 hs=[max(1,d.textbbox((0,0),s,font=font)[3]-d.textbbox((0,0),s,font=font)[1]) for s in lines]
 y=y1+((y2-y1)-(sum(hs)+leading*(len(lines)-1)))/2
 for s,h in zip(lines,hs):
  b=d.textbbox((0,0),s,font=font); d.text((x1+(x2-x1-(b[2]-b[0]))/2,y),s,font=font,fill=fill); y+=h+leading

def band(d,xy,title,color):
 x1,y1,x2,y2=xy; d.rounded_rectangle(xy,18,fill='#F8FBFD' if color!=PURPLE else '#FBF8FF',outline=color,width=3); d.rounded_rectangle((x1,y1,x1+240,y1+50),15,fill=color,outline=color); d.rectangle((x1+15,y1+32,x1+240,y1+50),fill=color); center(d,(x1+8,y1+4,x1+235,y1+46),title,f(23,True),'white')
def box(d,xy,title,body,color,sz=21):
 x1,y1,x2,y2=xy; d.rounded_rectangle(xy,16,fill='white',outline=color,width=4); d.rounded_rectangle((x1,y1,x2,y1+48),16,fill=color,outline=color); d.rectangle((x1,y1+25,x2,y1+48),fill=color); center(d,(x1+7,y1+5,x2-7,y1+43),title,f(22,True),'white'); center(d,(x1+12,y1+58,x2-12,y2-10),body,f(sz),DARK)
def arrow(d,a,b,color=LINE,w=7,head=22,dashed=False):
 import math
 x1,y1=a; x2,y2=b
 if dashed:
  n=10
  for i in range(n):
   if i%2==0:
    t=i/n; u=(i+1)/n; d.line((x1+(x2-x1)*t,y1+(y2-y1)*t,x1+(x2-x1)*u,y1+(y2-y1)*u),fill=color,width=w)
 else: d.line((x1,y1,x2,y2),fill=color,width=w)
 ang=math.atan2(y2-y1,x2-x1); p1=(x2-head*math.cos(ang-.52),y2-head*math.sin(ang-.52)); p2=(x2-head*math.cos(ang+.52),y2-head*math.sin(ang+.52)); d.polygon([(x2,y2),p1,p2],fill=color)
def tag(d,xy,text,color='#5B6573'):
 d.rounded_rectangle(xy,8,fill='white',outline='#D8E1EA',width=2); center(d,(xy[0]+4,xy[1]+2,xy[2]-4,xy[3]-2),text,f(16,True),color)

a=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(a)
d.rectangle((0,0,W,105),fill=NAVY); d.text((45,18),'Bản đồ vận hành AI BEM',font=f(42,True),fill='white'); d.text((47,69),'Đọc từ trên xuống: ai khởi tạo → AI xử lý gì → DB lưu gì',font=f(22),fill='#DCE6F1')
# band 1
band(d,(35,135,2165,430),'1. KHỞI TẠO YÊU CẦU',NAVY)
box(d,(90,225,405,385),'WEB ERP9','Người dùng bấm\nĐối chiếu thủ công',BLUE,23)
box(d,(495,225,840,385),'ERP Controller','Lấy phiếu + chi tiết\nLấy file đính kèm\nGửi request',BLUE,21)
box(d,(930,245,1225,405),'API ERP','Quartz/lịch chung\n\nChưa xác nhận\njob BEM cụ thể',TEAL,20)
box(d,(1370,225,1730,385),'API-AI Run','Nhận request\nTạo lượt chạy\nBEMT2003 = PROCESSING',GOLD,21)
box(d,(1830,225,2110,385),'ERP9 hiển thị','Khi hoàn tất:\nđọc DB, hiển thị\nkết quả cho người dùng',BLUE,20)
arrow(d,(405,305),(495,305)); d.line([(840,305),(875,305),(875,190),(1325,190),(1325,305)],fill=LINE,width=7)
arrow(d,(1325,305),(1370,305))
tag(d,(900,152,1300,184),'Thủ công: ERP Controller gọi thẳng API-AI')
arrow(d,(1225,325),(1370,325),dashed=True)
center(d,(1225,335,1370,370),'Tự động',f(16,True),'#8A3E00')
# band 2
band(d,(35,475,2165,805),'2. API-AI VÀ AI PYTHON XỬ LÝ',GOLD)
box(d,(100,585,420,745),'API-AI Queue RAM','ChannelJobQueue\nTối đa 200 job\nKhông nằm trong DB',GOLD,21)
box(d,(510,585,805,745),'API-AI Worker','Lấy job từ Queue\nGọi chuỗi xử lý AI',GOLD,21)
box(d,(895,585,1195,745),'AI Python OCR','Route /ocr\nFile → text',ORANGE,23)
box(d,(1285,585,1585,745),'AI Python LLM','Đọc text OCR\nTrích xuất dữ liệu',ORANGE,23)
box(d,(1675,585,2070,745),'AI Python Rules + LLM','Đối chiếu tiêu chí\nTrả OK/NG\n+ giải thích',ORANGE,21)
arrow(d,(420,665),(510,665)); arrow(d,(805,665),(895,665)); arrow(d,(1195,665),(1285,665)); arrow(d,(1585,665),(1675,665))
# band 3
band(d,(35,850,2165,1200),'3. DB LƯU THEO TỪNG BƯỚC',PURPLE)
box(d,(100,945,450,1110),'(1) BEMT2003','Lượt chạy\nPROCESSING',PURPLE,22)
box(d,(510,945,860,1110),'(3) BEMT2002','Text OCR\nđọc từ file',PURPLE,22)
box(d,(920,945,1270,1110),'(4) BEMT2005 / 2006','Dữ liệu trích xuất\ntừ chứng từ',PURPLE,21)
box(d,(1330,945,1680,1110),'(5) BEMT2004','Kết quả từng tiêu chí\nOK/NG + giải thích',PURPLE,21)
box(d,(1740,945,2100,1110),'(6) BEMT2003','COMPLETED / FAILED\nKết quả tổng OK/NG\n%',PURPLE,21)
arrow(d,(450,1028),(510,1028),PURPLE,5,18); arrow(d,(860,1028),(920,1028),PURPLE,5,18); arrow(d,(1270,1028),(1330,1028),PURPLE,5,18); arrow(d,(1680,1028),(1740,1028),PURPLE,5,18)
center(d,(80,1210,2120,1280),'Queue ở API-AI/RAM. OCR, LLM và Rules ở AI Python. DB chỉ lưu trạng thái/kết quả để ERP9 đọc lại và hiển thị.',f(24,True),'#8A3E00')
a.save(OUT); print(OUT)

