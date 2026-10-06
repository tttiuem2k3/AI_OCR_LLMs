import re, statistics
from pathlib import Path
p=Path(r"E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\app_2.log")
s=[float(x) for x in re.findall(r"OCR infer done in ([0-9.]+)s", p.read_text(encoding='utf-8',errors='ignore'))]
s.sort()
def pct(values,p):
 i=(len(values)-1)*p; lo=int(i); hi=min(lo+1,len(values)-1); return values[lo]+(values[hi]-values[lo])*(i-lo)
print('count',len(s)); print('min',min(s)); print('median',statistics.median(s)); print('p90',pct(s,.9)); print('p95',pct(s,.95)); print('max',max(s)); print('over60',sum(v>=60 for v in s)); print('over120',sum(v>=120 for v in s)); print('slowest',s[-10:])
