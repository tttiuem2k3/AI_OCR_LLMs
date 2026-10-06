from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
root=Path(r"E:\Asoft\AI_BEM\BEM_AI_PROJECT\.codex_tmp\code_flow_report_20261001\images")
files=sorted(root.glob("*.png"))
thumbs=[]
for f in files:
 im=Image.open(f).convert("RGB"); im.thumbnail((820,433)); thumbs.append((f,im.copy()))
w,h=1700, 520*((len(thumbs)+1)//2)
out=Image.new("RGB",(w,h),"#E9EEF3"); d=ImageDraw.Draw(out); ft=ImageFont.truetype(r"C:\Windows\Fonts\timesbd.ttf",24)
for i,(f,im) in enumerate(thumbs):
 x=25+(i%2)*840; y=25+(i//2)*520
 out.paste(im,(x,y+45)); d.text((x,y),f.name,font=ft,fill="#17365D")
p=root.parent/"contact_sheet.png"; out.save(p); print(p)
