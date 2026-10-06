from pathlib import Path
import json,re
root=Path(r'E:\Asoft\AI_BEM\AI_BEM_Check_T08_09')
audit=json.loads((root/'Accuracy_Recheck_T09_20261002'/'audit_current_workbook_fast.json').read_text(encoding='utf-8'))
db=json.loads((root/'Accuracy_Recheck_T09_20261002'/'db_t09_latest_20261002.json').read_text(encoding='utf-8-sig'))['Records']
db_by={str(x['VoucherNo']):x for x in db}
positive=('AI đọc đúng','AI trả lời đúng','AI trả lời đúng theo Rules','AI trả lời tốt')
negative=('AI đọc sai','AI trả lời sai','AI đối chiếu sai')

def pnum(v):
    try:
        x=float(str(v).replace('%','').strip())
        return x/100 if x>1 else x
    except:return None

def mark(text,patterns): return any(re.search(x,text,re.I) for x in patterns)
ng_phrases=[r'AI\s+(?:báo|trả|đối chiếu)\s+NG',r'giữ\s+kết\s+quả\s+AI\s+NG',r'kết\s+quả\s+NG\b',r'AI\s+NG\s+tại']
ok_phrases=[r'AI\s+(?:báo|trả|đối chiếu)\s+OK',r'giữ\s+kết\s+quả\s+AI\s+OK',r'kết\s+quả\s+(?:9\s+tiêu\s+chí\s+)?OK',r'AI\s+đã\s+trả\s+lời\s+chính\s+xác']
needs=[]; safe=[]; uncertain=[]
for x in audit['records']:
    issue=str(x.get('issue') or '')
    if not any(s.lower() in issue.lower() for s in positive): continue
    if any(s.lower() in issue.lower() for s in negative): continue
    acc=pnum(x.get('acc'))
    if acc is None or acc>=.9999: continue
    d=db_by.get(str(x['voucher']))
    text='\n'.join(str(x.get(k) or '') for k in ('p','issue','r','t'))
    reasons=[]
    if not d:
        reasons.append('Không tìm thấy phiếu trên DB')
    else:
        process=str(d.get('StatusProcess') or '').upper(); status=str(d.get('Status') or '').upper()
        if process!='COMPLETED': reasons.append(f'Lần chạy DB mới nhất là {process or "trống"}')
        if status=='NG' and mark(text,ok_phrases): reasons.append('DB đang NG nhưng nội dung nói AI OK/đúng')
        if status=='OK' and mark(text,ng_phrases): reasons.append('DB đang OK nhưng nội dung nói AI NG')
    if reasons:
        x['db']=d;x['reasons']=reasons;needs.append(x)
    else:
        # Rows that have only a generic review sentence are still safe if DB is completed and label explicitly says correct.
        if mark(text,[r'đã mở|đã đọc|đã kiểm tra|đã đồng bộ|đã refresh|AI đã trả lời chính xác|AI trả lời tốt|AI trả lời đúng']):
            x['db']=d;safe.append(x)
        else:
            x['db']=d;uncertain.append(x)
print('safe',len(safe),'needs',len(needs),'uncertain',len(uncertain))
for label,items in [('NEEDS_RECHECK',needs),('UNCERTAIN',uncertain),('SAFE_100',safe)]:
    print('\n###',label,len(items))
    for x in items:
        d=x.get('db') or {}
        print(json.dumps({'row':x['row'],'voucher':x['voucher'],'oldAcc':x['acc'],'ai':x['ai'],'dbProcess':d.get('StatusProcess'),'dbStatus':d.get('Status'),'dbPct':d.get('Percentage'),'issue':x['issue'],'P':x.get('p'),'R':x.get('r'),'T':x.get('t'),'reasons':x.get('reasons')},ensure_ascii=False,default=str))
(root/'Accuracy_Recheck_T09_20261002'/'accuracy_t09_triage.json').write_text(json.dumps({'safe_100':safe,'needs_recheck':needs,'uncertain':uncertain},ensure_ascii=False,indent=2,default=str),encoding='utf-8')
