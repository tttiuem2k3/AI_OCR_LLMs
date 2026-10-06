from pathlib import Path
from io import BytesIO
from PIL import Image
from docx import Document
import shutil
base=Path(r"E:\Asoft\AI_BEM\AI_BEM_Check_T08_09")
source=Path(r"E:\Asoft\AI_BEM\BEM_AI_PROJECT\.codex_tmp\code_flow_report_20261001\images\08_ban_do_instance_db.png")
dest=base/'Temp'/'code_flow_report_20261001'/'08_ban_do_instance_db.png'
dest.parent.mkdir(parents=True,exist_ok=True)
shutil.copy2(source,dest)
docx=base/'Bao_cao_co_che_code_doi_chieu_AI_BEM_01102026.docx'
doc=Document(docx)
replacement=source.read_bytes(); found=0
for part in doc.part.related_parts.values():
    if getattr(part,'content_type','').startswith('image/'):
        try:
            im=Image.open(BytesIO(part.blob))
            if im.size==(2100,1320):
                part._blob=replacement; found+=1
        except Exception:
            pass
assert found==1, found
doc.save(docx)
md_path=base/'Noi_dung_co_che_code_doi_chieu_AI_BEM_01102026.md'
md=md_path.read_text(encoding='utf-8').replace('![Bản đồ instance và DB](08_ban_do_instance_db.png)','![Bản đồ instance và DB](Temp/code_flow_report_20261001/08_ban_do_instance_db.png)')
md_path.write_text(md,encoding='utf-8')
print('updated embedded image:',found)
print(dest)
