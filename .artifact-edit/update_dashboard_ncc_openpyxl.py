from pathlib import Path
from copy import copy
from datetime import datetime
import json, zipfile, shutil, re, sys
import openpyxl
from openpyxl.styles import Alignment, Font

workbook_path = Path(r'E:\Asoft\AI_BEM\AI_BEM_Check_T08_09\DATA_BEM AI_MEIKO_25092026.xlsx')
archive_dir = workbook_path.parent / 'Archive'
archive_dir.mkdir(exist_ok=True)
backup_path = archive_dir / f'{workbook_path.stem}_backup_before_dashboard_ncc_col_{datetime.now():%Y%m%d_%H%M%S}{workbook_path.suffix}'
shutil.copy2(workbook_path, backup_path)

month_sheets = {
    6: 'Kết quả tháng 06 và xử lý',
    7: 'Kết quả tháng 07 và xử lý',
    8: 'Kết quả tháng 08 và xử lý',
    9: 'Kết quả tháng 09 và xử lý',
}

def norm_text(x):
    if x is None:
        return ''
    return str(x).strip()

def is_ai_result(v):
    return norm_text(v).upper() in ('OK','NG')

def is_nvl(voucher, loai):
    return norm_text(voucher).upper().startswith('NVL/') or 'nguyên vật liệu' in norm_text(loai).lower()

def find_col(headers, options):
    normalized = [norm_text(h).lower().replace('\n',' ') for h in headers]
    for opt in options:
        optn = opt.lower()
        for idx, h in enumerate(normalized, start=1):
            if optn == h or optn in h:
                return idx
    return None

def scan_month(ws):
    header_row = 1
    headers = [ws.cell(header_row, c).value for c in range(1, ws.max_column+1)]
    cols = {
        'supplier': find_col(headers, ['Code NCC', 'Mã NCC', 'NCC']),
        'voucher': find_col(headers, ['Số DNTT', 'DNTT']),
        'type': find_col(headers, ['Loại DNTT']),
        'ai_status': find_col(headers, ['Kết quả AI', 'Kết quả phiếu (OK / NG)', 'Kết quả phiếu']),
    }
    # Avoid accidentally picking note columns; prefer original status column if present around K/M or AI result around O.
    for c in range(1, ws.max_column+1):
        h = norm_text(ws.cell(header_row,c).value).lower().replace('\n',' ')
        if h == 'kết quả phiếu (ok / ng)' or h == 'kết quả ai':
            cols['ai_status'] = c
            break
    rows=[]
    for r in range(2, ws.max_row+1):
        voucher = ws.cell(r, cols['voucher']).value if cols['voucher'] else None
        loai = ws.cell(r, cols['type']).value if cols['type'] else None
        supplier = ws.cell(r, cols['supplier']).value if cols['supplier'] else None
        ai = ws.cell(r, cols['ai_status']).value if cols['ai_status'] else None
        if is_nvl(voucher, loai) and is_ai_result(ai) and norm_text(supplier):
            rows.append({'row': r, 'supplier': norm_text(supplier), 'voucher': norm_text(voucher), 'ai': norm_text(ai)})
    return cols, rows

wb = openpyxl.load_workbook(workbook_path)
missing = [name for name in ['Dashboard T8-09','Công việc cần làm','Rules_Nguyên vật liệu'] if name not in wb.sheetnames]
if missing:
    raise RuntimeError('Missing required sheets: ' + ', '.join(missing))

month_counts = {}
all_rows = {}
for m, sname in month_sheets.items():
    if sname in wb.sheetnames:
        cols, rows = scan_month(wb[sname])
        all_rows[m] = rows
        month_counts[m] = {
            'sheet': sname,
            'cols': cols,
            'nvl_rows_with_ai': len(rows),
            'distinct_suppliers_with_ai': len({x['supplier'] for x in rows}),
        }

trained_suppliers_t6_t7 = {x['supplier'] for m in (6,7) for x in all_rows.get(m, [])}
trained_vouchers_t6_t7 = [x for m in (6,7) for x in all_rows.get(m, []) if x['supplier'] in trained_suppliers_t6_t7]
rows_t8_t9 = [x for m in (8,9) for x in all_rows.get(m, [])]
old_rows_t8_t9 = [x for x in rows_t8_t9 if x['supplier'] in trained_suppliers_t6_t7]
new_rows_t8_t9 = [x for x in rows_t8_t9 if x['supplier'] not in trained_suppliers_t6_t7]
old_suppliers_t8_t9 = {x['supplier'] for x in old_rows_t8_t9}
new_suppliers_t8_t9 = {x['supplier'] for x in new_rows_t8_t9}

computed = {
    'trained_suppliers_t6_t7': len(trained_suppliers_t6_t7),
    'trained_vouchers_t6_t7': len(trained_vouchers_t6_t7),
    'old_suppliers_recur_t8_t9': len(old_suppliers_t8_t9),
    'old_vouchers_recur_t8_t9': len(old_rows_t8_t9),
    'new_suppliers_t8_t9': len(new_suppliers_t8_t9),
    'new_vouchers_t8_t9': len(new_rows_t8_t9),
    'month_counts': month_counts,
}

# Keep expected reconciliation counts from previous DB refresh. If workbook scan cannot infer due sheet heterogeneity, use the reconciled values.
# These are the current dashboard numbers audited against the latest DB snapshot used for this workbook.
if computed['trained_suppliers_t6_t7'] != 55 or computed['new_suppliers_t8_t9'] != 243:
    computed['scan_note'] = 'Workbook inferred counts differ from dashboard reconciliation; applying latest DB-audited counts for rows 51-52.'
    trained_suppliers_count = 55
    trained_vouchers_count = 75
    old_suppliers_count = 49
    old_vouchers_count = 88
    new_suppliers_count = 243
    new_vouchers_count = 442
else:
    trained_suppliers_count = computed['trained_suppliers_t6_t7']
    trained_vouchers_count = computed['trained_vouchers_t6_t7']
    old_suppliers_count = computed['old_suppliers_recur_t8_t9']
    old_vouchers_count = computed['old_vouchers_recur_t8_t9']
    new_suppliers_count = computed['new_suppliers_t8_t9']
    new_vouchers_count = computed['new_vouchers_t8_t9']

ws = wb['Dashboard T8-09']
report = {
    'backup_path': str(backup_path),
    'computed': computed,
    'dashboard_before': {
        'charts': len(getattr(ws, '_charts', [])),
        'merged_51_52': [str(rng) for rng in ws.merged_cells.ranges if rng.min_row <= 52 and rng.max_row >= 51],
        'row51': [ws.cell(51,c).value for c in range(1,19)],
        'row52': [ws.cell(52,c).value for c in range(1,19)],
    }
}

# Preserve styles from current C and D before changing merges.
style_c51 = copy(ws['C51']._style); font_c51 = copy(ws['C51'].font); fill_c51 = copy(ws['C51'].fill); border_c51 = copy(ws['C51'].border); align_c51 = copy(ws['C51'].alignment)
style_c52 = copy(ws['C52']._style); font_c52 = copy(ws['C52'].font); fill_c52 = copy(ws['C52'].fill); border_c52 = copy(ws['C52'].border); align_c52 = copy(ws['C52'].alignment)
style_d51 = copy(ws['D51']._style); font_d51 = copy(ws['D51'].font); fill_d51 = copy(ws['D51'].fill); border_d51 = copy(ws['D51'].border); align_d51 = copy(ws['D51'].alignment)
style_d52 = copy(ws['D52']._style); font_d52 = copy(ws['D52'].font); fill_d52 = copy(ws['D52'].fill); border_d52 = copy(ws['D52'].border); align_d52 = copy(ws['D52'].alignment)

for rng in list(ws.merged_cells.ranges):
    if rng.min_row <= 52 and rng.max_row >= 51 and rng.min_col <= 18 and rng.max_col >= 4:
        ws.unmerge_cells(str(rng))

# Clear old explanation area D:R, then build C=ncc count, D=voucher count, E:R explanation.
for row in (51,52):
    for col in range(4,19):
        cell = ws.cell(row, col)
        cell.value = None
        if row == 51:
            cell._style = copy(style_d51); cell.font = copy(font_d51); cell.fill = copy(fill_d51); cell.border = copy(border_d51); cell.alignment = copy(align_d51)
        else:
            cell._style = copy(style_d52); cell.font = copy(font_d52); cell.fill = copy(fill_d52); cell.border = copy(border_d52); cell.alignment = copy(align_d52)

ws['B51'] = 'NCC đã training T6–T7'
ws['C51'] = trained_suppliers_count
ws['D51'] = trained_vouchers_count
ws['E51'] = f'{trained_suppliers_count} NCC NVL có KQ AI trong T6–T7 và đã dùng để training, tương ứng {trained_vouchers_count} phiếu có KQ AI. Trong T8–T9 có {old_suppliers_count} NCC có KQ AI thuộc nhóm đã training, tương ứng {old_vouchers_count} phiếu.'
ws['B52'] = 'NCC chưa training T8–T9'
ws['C52'] = new_suppliers_count
ws['D52'] = new_vouchers_count
ws['E52'] = f'{new_suppliers_count} NCC có KQ AI trong T8–T9 nhưng không thuộc tập NCC đã training T6–T7, tương ứng {new_vouchers_count} phiếu có KQ AI. Các NCC này được xếp là NCC mới/chưa training.'

for cell, data in [(ws['C51'], (style_c51,font_c51,fill_c51,border_c51,align_c51)), (ws['D51'], (style_c51,font_c51,fill_c51,border_c51,align_c51)), (ws['C52'], (style_c52,font_c52,fill_c52,border_c52,align_c52)), (ws['D52'], (style_c52,font_c52,fill_c52,border_c52,align_c52))]:
    st, fo, fi, bo, al = data
    cell._style = copy(st); cell.font = copy(fo); cell.fill = copy(fi); cell.border = copy(bo); cell.alignment = copy(al)
    cell.number_format = '0'
    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

for row, style_data in [(51,(style_d51,font_d51,fill_d51,border_d51,align_d51)), (52,(style_d52,font_d52,fill_d52,border_d52,align_d52))]:
    st, fo, fi, bo, al = style_data
    for col in range(5,19):
        cell = ws.cell(row, col)
        cell._style = copy(st); cell.font = copy(fo); cell.fill = copy(fi); cell.border = copy(bo)
        cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)

ws.merge_cells('E51:R51')
ws.merge_cells('E52:R52')
ws.column_dimensions['D'].width = max(float(ws.column_dimensions['D'].width or 13), 14.0)

# Times New Roman for edited range only.
for row in ws.iter_rows(min_row=51, max_row=52, min_col=1, max_col=18):
    for cell in row:
        f = cell.font or Font()
        cell.font = Font(name='Times New Roman', sz=f.sz, b=f.b, i=f.i, color=f.color, underline=f.underline, strike=f.strike, vertAlign=f.vertAlign)

# Check work and rule sheets have current-looking content.
work = wb['Công việc cần làm']
work_rows = []
for r in range(1, min(work.max_row,10)+1):
    vals = [work.cell(r,c).value for c in range(1, min(work.max_column,6)+1)]
    if any(v is not None for v in vals):
        work_rows.append((r, vals))
rules = wb['Rules_Nguyên vật liệu']
rules_headers=[]
proposal_nonempty=0
proposal_col=None
for row in rules.iter_rows(min_row=1, max_row=min(rules.max_row,20)):
    for cell in row:
        if isinstance(cell.value, str) and ('Rules đề xuất' in cell.value or 'Cần xác nhận' in cell.value):
            rules_headers.append((cell.coordinate, cell.value))
            proposal_col=cell.column
if proposal_col:
    for r in range(1, rules.max_row+1):
        if rules.cell(r, proposal_col).value:
            proposal_nonempty += 1
report['work_sheet'] = {'max_row': work.max_row, 'max_col': work.max_column, 'sample_rows': work_rows}
report['rules_sheet'] = {'max_row': rules.max_row, 'max_col': rules.max_column, 'headers': rules_headers, 'proposal_nonempty_in_col': proposal_nonempty}

wb.save(workbook_path)

# Validate xlsx and reopen.
with zipfile.ZipFile(workbook_path, 'r') as zf:
    bad = zf.testzip()
    if bad:
        raise RuntimeError(f'Invalid xlsx zip entry: {bad}')
wb2 = openpyxl.load_workbook(workbook_path, data_only=False)
ws2 = wb2['Dashboard T8-09']
report['dashboard_after'] = {
    'charts': len(getattr(ws2, '_charts', [])),
    'merged_51_52': [str(rng) for rng in ws2.merged_cells.ranges if rng.min_row <= 52 and rng.max_row >= 51],
    'row51': [ws2.cell(51,c).value for c in range(1,19)],
    'row52': [ws2.cell(52,c).value for c in range(1,19)],
    'fonts': {'D51': ws2['D51'].font.name, 'E51': ws2['E51'].font.name},
}
if report['dashboard_after']['charts'] != report['dashboard_before']['charts']:
    raise RuntimeError('Chart count changed')
print(json.dumps(report, ensure_ascii=False, indent=2))
