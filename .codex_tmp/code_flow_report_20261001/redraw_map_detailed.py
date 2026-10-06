from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

OUT=Path(r"E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\Temp\code_flow_simplified_20261001\01_ban_do_van_hanh.png")
FONT=r'C:\Windows\Fonts\times.ttf'; FONT_B=r'C:\Windows\Fonts\timesbd.ttf'
NAVY='#17365D'; BLUE='#2F75B5'; TEAL='#168A8A'; GOLD='#D6A300'; ORANGE='#ED7D31'; PURPLE='#7030A0'; LINE='#6B8299'; DARK='#1F2933'; PALE='#F7FAFD'
W,H=2200,1150

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
 hs=[max(1,d.textbbox((0,0),x,font=font)[3]-d.textbbox((0,0),x,font=font)[1]) for x in lines]
 y=y1+((y2-y1)-(sum(hs)+leading*(len(lines)-1)))/2
 for s,h in zip(lines,hs):
  b=d.textbbox((0,0),s,font=font); d.text((x1+(x2-x1-(b[2]-b[0]))/2,y),s,font=font,fill=fill); y+=h+leading

def group(d,xy,title,color):
 x1,y1,x2,y2=xy; d.rounded_rectangle(xy,22,fill=PALE,outline=color,width=4); d.rectangle((x1,y1,x2,y1+62),fill=color); center(d,(x1+5,y1+5,x2-5,y1+57),title,f(28,True),'white')
def box(d,xy,title,body,color,sz=22):
 x1,y1,x2,y2=xy; d.rounded_rectangle(xy,18,fill='white',outline=color,width=3); d.rounded_rectangle((x1,y1,x2,y1+50),18,fill=color,outline=color); d.rectangle((x1,y1+27,x2,y1+50),fill=color); center(d,(x1+8,y1+5,x2-8,y1+45),title,f(22,True),'white'); center(d,(x1+12,y1+60,x2-12,y2-10),body,f(sz),DARK)
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
def small(d,xy,text,color='#5B6573'):
 d.rounded_rectangle(xy,8,fill='white',outline='#D7E1EA',width=2); center(d,(xy[0]+4,xy[1]+2,xy[2]-4,xy[3]-2),text,f(17,True),color)

im=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(im)
d.rectangle((0,0,W,100),fill=NAVY); d.text((45,17),'Bản đồ vận hành AI BEM',font=f(42,True),fill='white'); d.text((47,68),'ERP khởi tạo yêu cầu • API-AI điều phối • AI Python xử lý • DB lưu tiến độ và kết quả',font=f(22),fill='#DCE6F1')
# areas
group(d,(25,130,495,1080),'ERP9 WEB',BLUE)
group(d,(525,130,825,1080),'API ERP',TEAL)
group(d,(855,130,1255,1080),'API-AI',GOLD)
group(d,(1285,130,1665,1080),'AI Python',ORANGE)
group(d,(1695,130,2175,1080),'DB',PURPLE)
# ERP
box(d,(65,250,455,410),'WEB UI','Người dùng bấm\nĐối chiếu thủ công',BLUE,25)
box(d,(65,520,455,700),'ERP Controller','Lấy phiếu + chi tiết\nLấy file đính kèm\nGửi request sang API-AI',BLUE,23)
arrow(d,(260,410),(260,520))
# API
box(d,(565,520,785,700),'Quartz','Lịch chạy tự động\n\nChưa xác nhận\njob BEM cụ thể',TEAL,21)
# API AI
box(d,(895,520,1215,700),'Controller + Run','Nhận request\nTạo BEMT2003\nPROCESSING',GOLD,22)
box(d,(895,770,1215,890),'Queue RAM','ChannelJobQueue\nTối đa 200 job',GOLD,23)
box(d,(895,940,1215,1040),'Worker','Lấy job từ Queue\nGọi chuỗi xử lý AI',GOLD,21)
arrow(d,(1055,700),(1055,770)); arrow(d,(1055,890),(1055,940))
# AI Python
box(d,(1325,300,1625,450),'OCR','Route /ocr\nFile → text',ORANGE,23)
box(d,(1325,570,1625,720),'LLM','Trích xuất dữ liệu\ntừ text OCR',ORANGE,23)
box(d,(1325,840,1625,1010),'Rules + LLM','Đối chiếu theo tiêu chí\nTrả OK/NG + giải thích',ORANGE,22)
arrow(d,(1475,450),(1475,570)); arrow(d,(1475,720),(1475,840))
# DB
box(d,(1735,240,2135,370),'BEMT2003','Lượt chạy\nPROCESSING',PURPLE,22)
box(d,(1735,455,2135,585),'BEMT2002','Text OCR',PURPLE,23)
box(d,(1735,670,2135,800),'BEMT2005 / 2006','Dữ liệu trích xuất',PURPLE,23)
box(d,(1735,885,2135,1015),'BEMT2004','Kết quả từng tiêu chí\nOK/NG + giải thích',PURPLE,22)
small(d,(1745,1035,2125,1065),'BEMT2003 cập nhật: COMPLETED / FAILED','#7030A0')
# connections strict horizontal/vertical
arrow(d,(455,610),(895,610)); small(d,(550,580,800,620),'Thủ công: WEB gọi API-AI')
arrow(d,(785,610),(895,610),dashed=True); small(d,(545,720,805,770),'Tự động: API gọi API-AI\n(khi có job BEM)','#8A3E00')
arrow(d,(1215,635),(1735,305)); # run->db intentionally diagonal? should fix maybe it is diagonal and may cross AI? It crosses AI. Need use route with no diagonal but source request persist. hmm.
# hide previous crossing with not use? we need status drawing. let's vertical from controller start? designed to DB. Use boxed label at flow perhaps but diagonal ugly.
# add calls to AI at matched lines, Worker source abstractly starts AI sequence
arrow(d,(1215,990),(1325,925)); small(d,(1165,890,1300,930),'Gọi AI')
arrow(d,(1625,375),(1735,520)); arrow(d,(1625,645),(1735,735)); arrow(d,(1625,925),(1735,950))
# Explain status write using non-obtrusive top arrow line
small(d,(1265,185,1665,230),'API-AI ghi PROCESSING vào DB trước khi xếp Queue','#8A3E00')
arrow(d,(1215,540),(1680,540),color='#9A6A00',w=5,head=18)
# need line to db but y 540 arrows would not aligns and crosses AI. Actually label points and arrow passes AI, still overlap. use only label no arrow? well arrow passes through AI. Remove impossible but currently line comes from prior diagonal.
# footer
center(d,(65,1078,2135,1135),'Queue nằm tại API-AI/RAM. OCR, LLM và Rules nằm tại AI Python. DB chỉ lưu trạng thái và kết quả để ERP9 hiển thị lại.',f(22,True),'#8A3E00')
im.save(OUT)
print(OUT)
