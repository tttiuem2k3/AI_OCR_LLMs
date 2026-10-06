from pathlib import Path
from io import BytesIO
from PIL import Image
from docx import Document
base=Path(r"E:\Asoft\AI_BEM\AI_BEM_Check_T08_09")
docx=base/'Bao_cao_co_che_code_doi_chieu_AI_BEM_01102026.docx'
new=base/'Temp'/'code_flow_simplified_20261001'/'01_ban_do_van_hanh.png'
d=Document(docx); replaced=0
for part in d.part.related_parts.values():
    if getattr(part,'content_type','').startswith('image/'):
        try:
            im=Image.open(BytesIO(part.blob))
            if im.size==(1900,960):
                part._blob=new.read_bytes(); replaced+=1
        except Exception: pass
assert replaced==1,replaced
d.save(docx)
print('embedded image replaced:',replaced)
