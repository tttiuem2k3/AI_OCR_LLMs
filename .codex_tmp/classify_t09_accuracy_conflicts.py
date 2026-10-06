from pathlib import Path
import json,re
root=Path(r'E:\Asoft\AI_BEM\AI_BEM_Check_T08_09')
data=json.loads((root/'Accuracy_Recheck_T09_20261002'/'workbook_vs_db_t09_20261002.json').read_text(encoding='utf-8'))
rows=data['positive_below_100']
wrong_words=re.compile(r'AI\s+(?:đọc|trả|đối chiếu|báo).*?(?:sai|nhầm|thiếu)|không đủ.*kết luận|chưa đủ.*kết luận|không đọc được tiêu chí|cần.*chạy lại|chưa thể kết luận',re.I)
review_words=re.compile(r'đã (?:mở|đọc|kiểm tra|refresh|đồng bộ).*file|đã.*đối chiếu',re.I)
correct_words=re.compile(r'AI (?:đã )?(?:trả lời|đối chiếu|đọc).*?(?:chính xác|đúng|phù hợp)|kết quả.*phù hợp|giữ kết quả AI',re.I)
classes={'safe_100':[],'needs_recheck':[],'needs_manual_review':[]}
for x in rows:
    text='\n'.join(str(x.get(k) or '') for k in ('p','issue','r','note'))
    db_completed=str(x.get('db_process') or '').upper()=='COMPLETED'
    status=str(x.get('db_status') or '').upper()
    pct=x.get('db_pct')
    issues=[]
    if not db_completed: issues.append('DB latest run không COMPLETED')
    if wrong_words.search(text): issues.append('Nội dung có tín hiệu AI sai/chưa kết luận/chạy lại')
    if status=='OK' and re.search(r'AI\s+(?:báo|trả)\s+NG',text,re.I): issues.append('DB OK nhưng mô tả nói AI NG')
    if status=='NG' and re.search(r'AI\s+(?:báo|trả)\s+OK',text,re.I): issues.append('DB NG nhưng mô tả nói AI OK')
    if not review_words.search(text): issues.append('Không thấy bằng chứng đã mở/đọc file trong ghi chú')
    if issues:
        x['classification_reasons']=issues
        classes['needs_recheck'].append(x)
    elif correct_words.search(text): classes['safe_100'].append(x)
    else: classes['needs_manual_review'].append(x)
print({k:len(v) for k,v in classes.items()})
for k,v in classes.items():
    print('\n###',k)
    for x in v:
        print(x['row'],x['voucher'],'acc',x['acc'],'db',x['db_process'],x['db_status'],x['db_pct'],'reasons=',x.get('classification_reasons'),'issue=',repr(x['issue']),'p=',repr(str(x.get('p') or '')[:180]),'r=',repr(str(x.get('r') or '')[:180]),'note=',repr(str(x.get('note') or '')[:180]))
(root/'Accuracy_Recheck_T09_20261002'/'positive_below_100_classification.json').write_text(json.dumps(classes,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
