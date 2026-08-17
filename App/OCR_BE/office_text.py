# App/office_text.py
from __future__ import annotations
from pathlib import Path
import re
from typing import List
from io import BytesIO

_EXCEL_FALLBACK_PAGE_ROWS = 75
_EXCEL_FALLBACK_MAX_COLS = 64
_CUSTOMS_PAGE_MARKER_RE = re.compile(r"^\s*(\d{1,3})\s*/\s*(\d{1,3})\s*$")
_A1_CELL_RE = re.compile(r"^\s*([A-Z]+)\s*(\d+)\s*$", re.IGNORECASE)


def _wrap_line(text: str, max_len: int) -> List[str]:
    if max_len <= 0:
        return [text]
    if text == "":
        return [""]
    return [text[i : i + max_len] for i in range(0, len(text), max_len)]


def _paginate_lines(lines: List[str], *, max_lines: int, max_chars: int) -> List[str]:
    wrapped: List[str] = []
    for line in lines:
        wrapped.extend(_wrap_line(line, max_chars))

    pages: List[str] = []
    if not wrapped:
        return [""]

    for i in range(0, len(wrapped), max_lines):
        page_lines = wrapped[i : i + max_lines]
        pages.append("\n".join(page_lines).rstrip())
    return pages

def _excel_cell_to_text(v) -> str:
    if v is None:
        return ""
    try:
        if isinstance(v, float) and v.is_integer():
            v = int(v)
    except Exception:
        pass
    return str(v).replace("\r", " ").replace("\n", " ").strip()

def _excel_row_to_text(values) -> str:
    return "\t".join(_excel_cell_to_text(v) for v in values).rstrip()

def _excel_page_text(sheet_name: str, rows_txt: List[str]) -> str:
    body = "\n".join(r for r in rows_txt if r.strip()).rstrip()
    return f"[Sheet] {sheet_name}\n{body}" if body else f"[Sheet] {sheet_name}"

def _break_ranges_1based(start: int, end: int, break_ids) -> List[tuple[int, int]]:
    if end < start:
        return []

    points = []
    for break_id in break_ids or []:
        try:
            point = int(break_id)
        except Exception:
            continue
        if start <= point <= end:
            points.append(point)

    ranges: List[tuple[int, int]] = []
    cursor = start
    for point in sorted(set(points)):
        if point < cursor:
            continue
        ranges.append((cursor, point))
        cursor = point + 1

    if cursor <= end:
        ranges.append((cursor, end))

    return ranges or [(start, end)]

def _break_ranges_0based(size: int, break_indexes) -> List[tuple[int, int]]:
    if size <= 0:
        return []

    points = []
    for break_index in break_indexes or []:
        try:
            point = int(break_index)
        except Exception:
            continue
        if 0 < point <= size:
            points.append(point)

    ranges: List[tuple[int, int]] = []
    cursor = 0
    for point in sorted(set(points)):
        if point <= cursor:
            continue
        ranges.append((cursor, point))
        cursor = point

    if cursor < size:
        ranges.append((cursor, size))

    return ranges or [(0, size)]

def _break_ranges_0based_bounds(start: int, end: int, break_indexes) -> List[tuple[int, int]]:
    if end <= start:
        return []

    points = []
    for break_index in break_indexes or []:
        try:
            point = int(break_index)
        except Exception:
            continue
        if start < point < end:
            points.append(point)

    ranges: List[tuple[int, int]] = []
    cursor = start
    for point in sorted(set(points)):
        if point <= cursor:
            continue
        ranges.append((cursor, point))
        cursor = point

    if cursor < end:
        ranges.append((cursor, end))

    return ranges or [(start, end)]

def _looks_like_customs_page_start(values) -> bool:
    cells = [_excel_cell_to_text(v) for v in values]
    if not any(c.upper() == "<IMP>" for c in cells):
        return False

    for cell in cells:
        m = _CUSTOMS_PAGE_MARKER_RE.match(cell)
        if not m:
            continue
        cur = int(m.group(1))
        total = int(m.group(2))
        if 1 <= cur <= total <= 500:
            return True

    return False

def extract_docx_text(src: str | Path) -> List[str]:

    from docx import Document
    data = Path(src).read_bytes() if isinstance(src, (str, Path)) else src 
    doc = Document(BytesIO(data))
    blocks = []

    for p in doc.paragraphs:
        t = (p.text or "").strip()
        if t:
            blocks.append(t)

    for tb in doc.tables:
        for row in tb.rows:
            cells = []
            for cell in row.cells:
                cells.append((cell.text or "").strip())
            if any(cells):
                blocks.append("\t".join(cells))

    lines = [b for b in blocks if b is not None]
    pages = _paginate_lines(lines, max_lines=40, max_chars=88)
    return pages

def _xlsx_print_bounds(ws) -> tuple[int, int, int, int]:
    from openpyxl.utils.cell import range_boundaries

    bounds = []
    print_area = getattr(ws, "print_area", "") or ""
    area_refs = [p.strip() for p in str(print_area).split(",") if p.strip()]

    for area_ref in area_refs:
        if "!" in area_ref:
            area_ref = area_ref.split("!", 1)[1]
        area_ref = area_ref.replace("$", "").strip().strip("'")
        try:
            min_col, min_row, max_col, max_row = range_boundaries(area_ref)
        except Exception:
            continue
        min_row = min_row or 1
        max_row = max_row or ws.max_row
        min_col = min_col or 1
        max_col = max_col or ws.max_column
        bounds.append((min_row, max_row, min_col, max_col))

    if bounds:
        return (
            min(b[0] for b in bounds),
            max(b[1] for b in bounds),
            min(b[2] for b in bounds),
            max(b[3] for b in bounds),
        )

    max_col = min(ws.max_column or 1, _EXCEL_FALLBACK_MAX_COLS)
    return 1, ws.max_row or 1, 1, max_col

def _xlsx_break_ids(break_list) -> List[int]:
    ids: List[int] = []
    for br in getattr(break_list, "brk", []) or []:
        try:
            ids.append(int(br.id))
        except Exception:
            continue
    return ids

def _xlsx_customs_page_row_ranges(
    ws,
    *,
    min_row: int,
    max_row: int,
    min_col: int,
    max_col: int,
) -> List[tuple[int, int]]:
    starts: List[int] = []
    for row_no in range(min_row, max_row + 1):
        values = [
            ws.cell(row_no, col_no).value
            for col_no in range(min_col, max_col + 1)
        ]
        if _looks_like_customs_page_start(values):
            starts.append(row_no)

    if len(starts) < 2:
        return []

    ranges: List[tuple[int, int]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] - 1 if idx + 1 < len(starts) else max_row
        ranges.append((start, end))
    return ranges

def _xlsx_page_ranges(ws, min_row: int, max_row: int, min_col: int, max_col: int):
    customs_row_ranges = _xlsx_customs_page_row_ranges(
        ws,
        min_row=min_row,
        max_row=max_row,
        min_col=min_col,
        max_col=max_col,
    )
    if customs_row_ranges:
        return [(row_range, (min_col, max_col)) for row_range in customs_row_ranges]

    row_ranges = _break_ranges_1based(
        min_row,
        max_row,
        _xlsx_break_ids(getattr(ws, "row_breaks", None)),
    )
    col_ranges = _break_ranges_1based(
        min_col,
        max_col,
        _xlsx_break_ids(getattr(ws, "col_breaks", None)),
    )

    if len(row_ranges) > 1 or len(col_ranges) > 1:
        page_ranges = []
        page_order = (getattr(ws.page_setup, "pageOrder", None) or "downThenOver")
        if page_order == "overThenDown":
            for row_range in row_ranges:
                for col_range in col_ranges:
                    page_ranges.append((row_range, col_range))
        else:
            for col_range in col_ranges:
                for row_range in row_ranges:
                    page_ranges.append((row_range, col_range))
        return page_ranges

    return []

def _xlsx_page_lines(ws, row_range: tuple[int, int], col_range: tuple[int, int]) -> List[str]:
    rows_txt: List[str] = []
    for row in ws.iter_rows(
        min_row=row_range[0],
        max_row=row_range[1],
        min_col=col_range[0],
        max_col=col_range[1],
        values_only=True,
    ):
        line = _excel_row_to_text(row)
        if line.strip():
            rows_txt.append(line)
    return rows_txt

def extract_xlsx_text(src: str | Path) -> List[str]:
    """
    Extract text from XLSX and split pages by Excel print/page-break metadata.
    """
    from openpyxl import load_workbook
    data = Path(src).read_bytes() if isinstance(src, (str, Path)) else src
    bio = BytesIO(data)
    wb = load_workbook(filename=bio, data_only=True, read_only=False)
    try:
        pages: List[str] = []
        worksheets = [ws for ws in wb.worksheets if getattr(ws, "sheet_state", "visible") == "visible"]
        if not worksheets:
            worksheets = list(wb.worksheets)

        for ws in worksheets:
            min_row, max_row, min_col, max_col = _xlsx_print_bounds(ws)
            page_ranges = _xlsx_page_ranges(ws, min_row, max_row, min_col, max_col)
            if page_ranges:
                for row_range, col_range in page_ranges:
                    rows_txt = _xlsx_page_lines(ws, row_range, col_range)
                    if rows_txt:
                        pages.append(_excel_page_text(ws.title, rows_txt))
                continue

            rows_txt = _xlsx_page_lines(ws, (min_row, max_row), (min_col, max_col))
            if not rows_txt:
                pages.append("")
                continue

            for i in range(0, len(rows_txt), _EXCEL_FALLBACK_PAGE_ROWS):
                chunk = rows_txt[i : i + _EXCEL_FALLBACK_PAGE_ROWS]
                pages.append(_excel_page_text(ws.title, chunk))

        return pages if pages else [""]
    finally:
        wb.close()

def _xls_open_workbook(xlrd, data):
    try:
        return xlrd.open_workbook(
            file_contents=data,
            on_demand=True,
            formatting_info=True,
        )
    except Exception:
        return xlrd.open_workbook(file_contents=data, on_demand=True)

def _xls_cell_to_text(xlrd, wb, sh, r: int, c: int) -> str:
    v = sh.cell_value(r, c)
    ct = sh.cell_type(r, c)
    if ct == xlrd.XL_CELL_DATE:
        try:
            v = xlrd.xldate.xldate_as_datetime(v, wb.datemode).isoformat()
        except Exception:
            pass
    return _excel_cell_to_text(v)

def _xls_row_to_text(xlrd, wb, sh, r: int, col_range: tuple[int, int]) -> str:
    values = [_xls_cell_to_text(xlrd, wb, sh, r, c) for c in range(col_range[0], col_range[1])]
    return "\t".join(values).rstrip()

def _xls_break_indexes(page_breaks) -> List[int]:
    indexes: List[int] = []
    for br in page_breaks or []:
        try:
            indexes.append(int(br[0]))
        except Exception:
            continue
    return indexes

def _xls_col_letters_to_index(letters: str) -> int:
    col = 0
    for ch in letters.upper():
        if not ("A" <= ch <= "Z"):
            continue
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return col - 1

def _xls_parse_area_ref(area_ref: str) -> tuple[int, int, int, int] | None:
    if not area_ref:
        return None
    if "!" in area_ref:
        area_ref = area_ref.split("!", 1)[1]
    area_ref = area_ref.replace("$", "").strip().strip("'").lstrip("=")
    if not area_ref:
        return None

    if ":" in area_ref:
        start_ref, end_ref = [p.strip() for p in area_ref.split(":", 1)]
    else:
        start_ref = end_ref = area_ref

    m1 = _A1_CELL_RE.match(start_ref)
    m2 = _A1_CELL_RE.match(end_ref)
    if not m1 or not m2:
        return None

    min_col = _xls_col_letters_to_index(m1.group(1))
    min_row = int(m1.group(2)) - 1
    max_col = _xls_col_letters_to_index(m2.group(1))
    max_row = int(m2.group(2)) - 1
    if min_col < 0 or min_row < 0 or max_col < 0 or max_row < 0:
        return None
    return min_row, max_row, min_col, max_col

def _xls_print_bounds(wb, sh) -> tuple[int, int, int, int]:
    max_cols = min(int(sh.ncols or 1), _EXCEL_FALLBACK_MAX_COLS)
    max_rows = int(sh.nrows or 1)
    default_bounds = (0, max_rows - 1, 0, max_cols - 1)

    name_map = getattr(wb, "name_map", None)
    if not isinstance(name_map, dict):
        return default_bounds

    candidates = []
    for key in ("Print_Area", "PRINT_AREA", "print_area"):
        entries = name_map.get(key)
        if entries:
            candidates.extend(entries)

    if not candidates:
        return default_bounds

    sh_index = getattr(sh, "number", None)
    bounds = []
    for name in candidates:
        scope = getattr(name, "scope", -1)
        if sh_index is not None and scope not in (-1, sh_index):
            continue
        formula = getattr(name, "formula_text", None) or getattr(name, "raw_formula", None)
        if not formula:
            continue
        for part in str(formula).split(","):
            parsed = _xls_parse_area_ref(part)
            if parsed:
                bounds.append(parsed)

    if not bounds:
        return default_bounds

    min_row = max(min(b[0] for b in bounds), 0)
    max_row = min(max(b[1] for b in bounds), max_rows - 1)
    min_col = max(min(b[2] for b in bounds), 0)
    max_col = min(max(b[3] for b in bounds), max_cols - 1)

    if max_row < min_row or max_col < min_col:
        return default_bounds
    return min_row, max_row, min_col, max_col

def _xls_customs_page_row_ranges(
    xlrd,
    wb,
    sh,
    *,
    min_row: int,
    max_row: int,
    min_col: int,
    max_col: int,
) -> List[tuple[int, int]]:
    starts: List[int] = []
    for r in range(min_row, max_row + 1):
        values = [_xls_cell_to_text(xlrd, wb, sh, r, c) for c in range(min_col, max_col + 1)]
        if _looks_like_customs_page_start(values):
            starts.append(r)

    if len(starts) < 2:
        return []

    ranges: List[tuple[int, int]] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else max_row + 1
        ranges.append((start, end))
    return ranges

def _xls_page_ranges(
    xlrd,
    wb,
    sh,
    *,
    min_row: int,
    max_row: int,
    min_col: int,
    max_col: int,
):
    customs_row_ranges = _xls_customs_page_row_ranges(
        xlrd,
        wb,
        sh,
        min_row=min_row,
        max_row=max_row,
        min_col=min_col,
        max_col=max_col,
    )
    if customs_row_ranges:
        return [(row_range, (min_col, max_col + 1)) for row_range in customs_row_ranges]

    row_ranges = _break_ranges_0based_bounds(
        min_row,
        max_row + 1,
        _xls_break_indexes(getattr(sh, "horizontal_page_breaks", [])),
    )
    col_ranges = _break_ranges_0based_bounds(
        min_col,
        max_col + 1,
        _xls_break_indexes(getattr(sh, "vertical_page_breaks", [])),
    )

    if len(row_ranges) > 1 or len(col_ranges) > 1:
        page_ranges = []
        page_order = getattr(sh, "pageOrder", None) or getattr(sh, "page_order", None) or "downThenOver"
        if page_order == "overThenDown":
            for row_range in row_ranges:
                for col_range in col_ranges:
                    page_ranges.append((row_range, col_range))
        else:
            for col_range in col_ranges:
                for row_range in row_ranges:
                    page_ranges.append((row_range, col_range))
        return page_ranges

    return []

def _xls_page_lines(xlrd, wb, sh, row_range: tuple[int, int], col_range: tuple[int, int]) -> List[str]:
    rows_txt: List[str] = []
    for r in range(row_range[0], row_range[1]):
        line = _xls_row_to_text(xlrd, wb, sh, r, col_range)
        if line.strip():
            rows_txt.append(line)
    return rows_txt

def extract_xls_text(src: str | Path) -> List[str]:
    """
    Extract text from XLS and split pages by Excel print/page-break metadata.
    """
    import xlrd
    data = Path(src).read_bytes() if isinstance(src, (str, Path)) else src
    wb = _xls_open_workbook(xlrd, data)
    pages: List[str] = []
    try:
        sheets = [sh for sh in wb.sheets() if getattr(sh, "visibility", 0) == 0]
        if not sheets:
            sheets = wb.sheets()

        for sh in sheets:
            min_row, max_row, min_col, max_col = _xls_print_bounds(wb, sh)
            page_ranges = _xls_page_ranges(
                xlrd,
                wb,
                sh,
                min_row=min_row,
                max_row=max_row,
                min_col=min_col,
                max_col=max_col,
            )
            if page_ranges:
                for row_range, col_range in page_ranges:
                    rows_txt = _xls_page_lines(xlrd, wb, sh, row_range, col_range)
                    if rows_txt:
                        pages.append(_excel_page_text(sh.name, rows_txt))
                continue

            rows_txt = _xls_page_lines(
                xlrd,
                wb,
                sh,
                (min_row, max_row + 1),
                (min_col, max_col + 1),
            )

            if not rows_txt:
                pages.append("")
                continue

            for i in range(0, len(rows_txt), _EXCEL_FALLBACK_PAGE_ROWS):
                chunk = rows_txt[i : i + _EXCEL_FALLBACK_PAGE_ROWS]
                pages.append(_excel_page_text(sh.name, chunk))
    finally:
        wb.release_resources()
    if not pages:
        pages = [""]
    return pages

def extract_pptx_text(src: str | Path) -> List[str]:
    """
    Trích xuất chữ từ PPTX bằng python-pptx qua BytesIO.
    Mỗi slide -> 1 'page'.
    """
    from pptx import Presentation
    data = Path(src).read_bytes() if isinstance(src, (str, Path)) else src
    prs = Presentation(BytesIO(data))
    lines: List[str] = []
    for slide in prs.slides:
        chunks: List[str] = []
        for shape in slide.shapes:
            if hasattr(shape, "has_text_frame") and shape.has_text_frame:
                t = (shape.text or "").replace("\r", "\n")
                lines = [ln.strip() for ln in t.split("\n")]
                t = "\n".join([ln for ln in lines if ln])
                if t:
                    chunks.append(t)
        if hasattr(slide, "notes_slide") and slide.notes_slide and slide.notes_slide.notes_text_frame:
            nt = slide.notes_slide.notes_text_frame.text or ""
            nt = "\n".join(ln.strip() for ln in nt.splitlines() if ln.strip())
            if nt:
                chunks.append(f"[Notes]\n{nt}")
        if chunks:
            lines.extend("\n".join(chunks).split("\n"))

    if not lines:
        return [""]

    return _paginate_lines(lines, max_lines=30, max_chars=50)

def extract_office_text(path: str | Path) -> List[str]:
    ext = Path(path).suffix.lower()
    if ext == ".docx":
        return extract_docx_text(path)
    if ext == ".xlsx":
        return extract_xlsx_text(path)
    if ext == ".xls":
        return extract_xls_text(path)
    if ext == ".pptx":
        return extract_pptx_text(path)
    raise ValueError(f"Unsupported Office format without conversion: {ext}")
