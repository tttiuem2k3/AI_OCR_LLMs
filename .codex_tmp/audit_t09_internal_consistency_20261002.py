from pathlib import Path
import json,re
root=Path(r'E:\Asoft\AI_BEM\AI_BEM_Check_T08_09')
audit=json.loads((root/'Accuracy_Recheck_T09_20261002/audit_current_workbook_fast.json').read_text(encoding='utf-8'))
db=json.loads((root/'Accuracy_Recheck_T09_20261002/db_t09_latest_20261002.json').read_text(encoding='utf-8-sig'))['Records']
db_by={str(x['VoucherNo']):x for x in db}
pos=('AI đọc đúng','AI trả lời đúng','AI trả lời đúng theo Rules','AI trả lời tốt')
neg=('AI đọc sai','AI trả lời sai','AI đối chiếu sai')

def pct(v):
 try:
  n=float(str(v).replace('%','').strip()); return n/100 if n>1 else n
 except:return None

def bullet_lines(text): return [re.sub(r'^[-+•]\s*','',x.strip()) for x in str(text or '').splitlines() if x.strip()]
flags=[]
for x in audit['records']:
 v=str(x['voucher']); d=db_by.get(v); issue=str(x.get('issue') or ''); text='\n'.join(str(x.get(k) or '') for k in ('p','r','t')); lines=bullet_lines(text); reasons=[]
 db_status=str((d or {}).get('Status') or '').upper(); process=str((d or {}).get('StatusProcess') or '').upper(); db_pct=pct((d or {}).get('Percentage'))
 has_pos=any(a.lower() in issue.lower() for a in pos); has_neg=any(a.lower() in issue.lower() for a in neg); acc=pct(x.get('acc'))
 if has_pos and not has_neg and acc is not None and acc<.9999: reasons.append('Nhãn chỉ ghi AI đúng nhưng độ chính xác dưới 100%')
 if has_neg and acc is not None and acc>=.9999: reasons.append('Có nhãn AI sai nhưng độ chính xác 100%')
 if process=='FAILED' and has_pos: reasons.append('Lần chạy mới nhất FAILED nhưng nhãn ghi AI đúng')
 if process not in ('COMPLETED','FAILED') and (has_pos or has_neg): reasons.append('Chưa có kết quả AI cuối nhưng đã kết luận đúng/sai')
 for line in lines:
  low=line.lower()
  if db_status=='OK' and (re.match(r'^(ai|kết quả).*\bng\b',low) or 'giữ kết quả ai ng' in low):
   reasons.append(f'DB OK nhưng nội dung ghi NG: {line}')
  if db_status=='NG' and (re.match(r'^ai\s+(?:trả|báo|đối chiếu)\s+ok\b',low) or 'giữ kết quả ai ok' in low or re.match(r'^kết quả(?:\s+\d+\s+tiêu chí)?\s+ok\b',low)):
   reasons.append(f'DB NG nhưng nội dung ghi OK: {line}')
  m=re.search(r'(?:giữ\s+)?kết\s+quả\s+ai\s+(?:ok|ng)?\s*(\d+(?:[.,]\d+)?)\s*%',low)
  if m and db_pct is not None:
   text_pct=float(m.group(1).replace(',','.'))/100
   if abs(text_pct-db_pct)>.0002: reasons.append(f'% trong nội dung {text_pct:.4f} khác DB {db_pct:.4f}: {line}')
 if db_status in ('OK','NG') and 'Không có kết quả AI' in issue: reasons.append('DB có kết quả nhưng nhãn ghi Không có kết quả AI')
 if db_status not in ('OK','NG') and acc not in (None,0): reasons.append('DB chưa có kết quả nhưng độ chính xác khác 0')
 if reasons:
  flags.append({'row':x['row'],'voucher':v,'db_process':process,'db_status':db_status,'db_pct':(d or {}).get('Percentage'),'issue':issue,'accuracy':x.get('acc'),'P':x.get('p'),'R':x.get('r'),'T':x.get('t'),'reasons':list(dict.fromkeys(reasons))})
print('FLAGS',len(flags))
for f in flags:
 print(json.dumps({'row':f['row'],'voucher':f['voucher'],'db':f['db_process']+'/'+f['db_status']+' '+str(f['db_pct']),'accuracy':f['accuracy'],'issue':f['issue'],'reasons':f['reasons']},ensure_ascii=False))
(root/'Accuracy_Recheck_T09_20261002/internal_consistency_flags.json').write_text(json.dumps(flags,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
