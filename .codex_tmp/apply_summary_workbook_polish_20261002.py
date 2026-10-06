import json
from pathlib import Path
out=Path(r"E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\Mapping_DNTT_Files_NVL_20261002")
payload_path=out/'mapping_dataset_payload_20261002.json'
payload=json.loads(payload_path.read_text(encoding='utf-8'))
for sheet in payload['sheets']:
    if sheet['name']=='00_Tong_quan':
        for row in sheet['rows']:
            voucher=row['VoucherNo'].replace('/','-')
            row['CopiedFolder']=f"Files_dinh_kem\\{voucher}"
            row['SelectionBasis']='AI OK 100%; ApprovingLevel = 6; số file/tổng trang-sheet > 30.'
payload_path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
