# App/text_format.py
from __future__ import annotations
from typing import Any, Iterable, List, Tuple
import statistics

try:
    import numpy as np 
except Exception:
    np = None 

# ---- Kiểu dữ liệu cơ bản -----
BBox = Tuple[int, int, int, int]  
TextItem = Tuple[BBox, str]

# ==============================================================
# A. Helpers chung
# ==============================================================

def _to_list(obj: Any) -> Any:
    """Chuyển ndarray -> list an toàn; để nguyên nếu không phải ndarray."""
    if np is not None and isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj

def _iter_points(poly: Any) -> Iterable:
    """Trả về iterable các điểm (x, y) mà không đụng tới truthiness của ndarray."""
    if poly is None:
        return []
    poly = _to_list(poly)
    if isinstance(poly, (list, tuple)):
        return poly
    return []

def _bbox_from_poly(poly: Any) -> BBox:
    xs: List[float] = []
    ys: List[float] = []
    for pt in _iter_points(poly):
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            try:
                xs.append(float(pt[0]))
                ys.append(float(pt[1]))
            except Exception:
                continue
    if not xs or not ys:
        return (0, 0, 0, 0)
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))

def _poly_to_bbox_float(poly) -> Tuple[float, float, float, float]:
    """Bản float để tính toán pitch/chỉ số cột chính xác hơn."""
    poly = _to_list(poly) or []
    xs, ys = [], []
    for p in poly:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            xs.append(float(p[0])); ys.append(float(p[1]))
    if not xs or not ys:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))

# ==============================================================
# B. TXT đơn giản
# ==============================================================

def _extract_overall_items(page: Any) -> List[TextItem]:
    """
    Ưu tiên lấy từ overall_ocr_res: rec_texts + (rec_boxes|rec_polys).
    """
    items: List[TextItem] = []
    ov = getattr(page, "overall_ocr_res", None)
    if ov is None and isinstance(page, dict):
        ov = page.get("overall_ocr_res")

    if not isinstance(ov, dict):
        return items

    texts = ov.get("rec_texts") or []
    rec_boxes = _to_list(ov.get("rec_boxes"))
    rec_polys = _to_list(ov.get("rec_polys"))

    if isinstance(rec_boxes, (list, tuple)) and len(rec_boxes) == len(texts):
        boxes = rec_boxes
    elif isinstance(rec_polys, (list, tuple)) and len(rec_polys) == len(texts):
        boxes = [_bbox_from_poly(poly) for poly in rec_polys]
    else:
        boxes = [None] * len(texts)

    for t, b in zip(texts, boxes):
        if isinstance(t, str) and t.strip():
            # nếu b None -> (0,0,0,0)
            bb = (0, 0, 0, 0) if b is None else b
            items.append((bb, t.strip()))
    return items

def _extract_layout_boxes(page: Any, target_labels=("table",)) -> List[BBox]:
    """Lấy bbox layout (ví dụ 'table') để giữ form tốt hơn (gom text theo vùng)."""
    out: List[BBox] = []
    lay = getattr(page, "layout_det_res", None)
    if lay is None and isinstance(page, dict):
        lay = page.get("layout_det_res")
    if not isinstance(lay, dict):
        return out
    boxes = lay.get("boxes") or []
    for obj in boxes:
        lbl = obj.get("label")
        if lbl in target_labels:
            coord = _to_list(obj.get("coordinate"))
            if isinstance(coord, (list, tuple)) and len(coord) >= 4:
                try:
                    out.append((int(coord[0]), int(coord[1]), int(coord[2]), int(coord[3])))
                except Exception:
                    pass
    return out

def _cluster_lines(items: List[TextItem], y_tol: int = 10) -> List[List[TextItem]]:
    """Nhóm các token theo dòng đơn giản bằng ngưỡng |Δy|."""
    if not items:
        return []
    items.sort(key=lambda it: (it[0][1], it[0][0]))  # sort theo top,y rồi left,x
    lines: List[List[TextItem]] = []
    for bbox, text in items:
        placed = False
        for line in lines:
            ly1 = min(b[1] for b, _ in line)
            if abs(bbox[1] - ly1) <= y_tol:
                line.append((bbox, text))
                placed = True
                break
        if not placed:
            lines.append([(bbox, text)])
    for line in lines:
        line.sort(key=lambda it: it[0][0])
    return lines

def _join_line(line: List[TextItem]) -> str:
    return " ".join(t for _, t in line if t)

def _render_region(items: List[TextItem]) -> str:
    lines = _cluster_lines(items, y_tol=10)
    return "\n".join(_join_line(line) for line in lines if line)

def _inside(b: BBox, region: BBox) -> bool:
    x1, y1, x2, y2 = b
    rx1, ry1, rx2, ry2 = region
    return (x1 >= rx1 and y1 >= ry1 and x2 <= rx2 and y2 <= ry2)

def page_to_txt(page: Any) -> str:
    """
    Xuất *chỉ chữ* đã OCR, giữ thứ tự đọc & gần 'form':
      - Nếu có 'table' trong layout: render riêng text nằm trong từng table,
        sau đó render phần còn lại của trang.
    """
    items = _extract_overall_items(page)
    if not items:
        return ""

    tables = _extract_layout_boxes(page, target_labels=("table",))
    used = [False] * len(items)
    blocks: List[str] = []

    for tb in sorted(tables, key=lambda b: (b[1], b[0])):
        in_tb: List[TextItem] = []
        for i, (b, t) in enumerate(items):
            if not used[i] and _inside(b, tb):
                in_tb.append((b, t))
                used[i] = True
        if in_tb:
            blocks.append(_render_region(in_tb))

    remain = [it for i, it in enumerate(items) if not used[i]]
    if remain:
        blocks.append(_render_region(remain))

    return "\n\n".join(blocks)

def to_txt_pages(page_results: List[Any]) -> List[str]:
    return [page_to_txt(p) for p in page_results]

# ==============================================================
# C. TXT tối ưu
# ==============================================================

# --- Tham số pitch & hiển thị TXT ---
EPS_Y_FACTOR = 0.48
OVERLAP_THR  = 0.25
MIN_CHAR_PX   = 6
MAX_CHAR_PX   = 28
COLS_MARGIN   = 2
MIN_COLS      = 20
MAX_COLS      = 20000 

def _extract_items_for_pitch(page: Any):
    """
    Rút trích token (x1,x2,y1,y2,ym,text) từ overall_ocr_res cho thuật toán canh lưới.
    Trả về: items(sorted), med_h, max_x2 (xmax động theo dữ liệu)
    """
    ov = getattr(page, "overall_ocr_res", None)
    if ov is None and isinstance(page, dict):
        ov = page.get("overall_ocr_res")
    if not isinstance(ov, dict):
        return [], 20.0, 1000.0

    texts = ov.get("rec_texts") or ov.get("texts") or ov.get("text") or []
    polys = ov.get("rec_polys") or ov.get("dt_polys") or ov.get("text_polys") or []

    texts = _to_list(texts) or []
    polys = _to_list(polys) or []
    if not texts or not polys or len(texts) != len(polys):
        return [], 20.0, 1000.0

    items, heights = [], []
    for poly, txt in zip(polys, texts):
        x1, y1, x2, y2 = _poly_to_bbox_float(poly)
        t = (txt or "").strip()
        if not t:
            continue
        w = max(1.0, x2 - x1)
        h = max(1.0, y2 - y1)
        items.append({
            "x1": float(x1), "y1": float(y1),
            "x2": float(x2), "y2": float(y2),
            "w":  float(w),
            "h":  float(h),
            "ym": float((y1 + y2) / 2.0),
            "text": t
        })
        heights.append(h)

    items.sort(key=lambda t: (t["ym"], t["x1"]))
    med_h  = statistics.median(heights) if heights else 20.0
    max_x2 = max([it["x2"] for it in items]) if items else 1000.0  # ✅ xmax động
    return items, med_h, max_x2

def _v_overlap(a, b):
    inter = max(0.0, min(a["y2"], b["y2"]) - max(a["y1"], b["y1"]))
    union = max(a["y2"], b["y2"]) - min(a["y1"], b["y1"])
    return (inter/union) if union > 0 else 0.0

def _cluster_lines_pitch(items, med_h):
    """Gom dòng theo Y với ngưỡng động: eps = EPS_Y_FACTOR * med_h."""
    eps = EPS_Y_FACTOR * med_h
    lines, cur = [], []
    cur_mid = None

    for it in items:
        if not cur:
            cur = [it]; cur_mid = it["ym"]; continue
        if abs(it["ym"] - cur_mid) <= eps and _v_overlap(cur[-1], it) >= OVERLAP_THR:
            cur.append(it)
            cur_mid = statistics.median(x["ym"] for x in cur)
        else:
            lines.append(sorted(cur, key=lambda t: t["x1"]))
            cur = [it]; cur_mid = it["ym"]
    if cur:
        lines.append(sorted(cur, key=lambda t: t["x1"])) 
    return lines

def _estimate_pitch(items):
    """Trung vị (bbox_width / len(text)) trên toàn trang, kẹp biên."""
    vals = []
    for it in items:
        L = max(1, len(it["text"]))
        vals.append(it["w"] / L)
    if not vals:
        return 10.0
    p = statistics.median(vals)
    return max(MIN_CHAR_PX, min(MAX_CHAR_PX, p))

def _ceil_div(x, y):
    return int(-(-x // y))

def _build_txt(lines, pitch, min_cols):
    """
    Dựng TXT:
      - Dùng floor(x1/pitch) cho col_s, CEIL(x2/pitch) cho col_e (giữ lề phải)
      - Buffer động, không rstrip để không “mất chữ phải”
      - Tránh overlap bằng prev_end
    """
    out = []
    for r in lines:
        buf = [" "] * int(min_cols)
        prev_end = -1

        for it in r:
            col_s = int(it["x1"] // pitch)                  
            col_e = _ceil_div(it["x2"], pitch)             
            need  = max(len(it["text"]), col_e - col_s)     

            place_s = max(col_s, prev_end + 1)              
            place_e = place_s + need

            if place_e > len(buf):
                buf.extend([" "] * (place_e - len(buf)))    

            for k, ch in enumerate(it["text"]):
                idx = place_s + k
                if idx >= len(buf):
                    buf.extend([" "] * (idx - len(buf) + 1))
                buf[idx] = ch

            prev_end = place_s + len(it["text"]) - 1

        out.append("".join(buf))  
    return out

def _item_center(item):
    return (
        (float(item["x1"]) + float(item["x2"])) / 2.0,
        (float(item["y1"]) + float(item["y2"])) / 2.0,
    )

def _item_inside_region(item, region: BBox) -> bool:
    center_x, center_y = _item_center(item)
    region_x1, region_y1, region_x2, region_y2 = region
    return (
        region_x1 <= center_x <= region_x2
        and region_y1 <= center_y <= region_y2
    )

def _escape_markdown_cell(value: str) -> str:
    return " ".join(str(value).split()).replace("|", r"\|")

def _render_markdown_table(items, med_h):
    ordered_items = sorted(items, key=lambda item: (item["ym"], item["x1"]))
    rows = _cluster_lines_pitch(ordered_items, med_h)
    if len(rows) < 2:
        return None

    reference_row = max(rows, key=len)
    if len(reference_row) < 2:
        return None

    column_anchors = [
        _item_center(item)[0]
        for item in sorted(reference_row, key=lambda item: item["x1"])
    ]
    rendered_rows = []
    multi_cell_rows = 0
    for row in rows:
        cells = [[] for _ in column_anchors]
        for item in sorted(row, key=lambda item: item["x1"]):
            center_x, _ = _item_center(item)
            column_index = min(
                range(len(column_anchors)),
                key=lambda index: abs(column_anchors[index] - center_x),
            )
            cells[column_index].append(item)

        rendered_cells = []
        occupied_cells = 0
        for cell_items in cells:
            cell_text = " ".join(
                item["text"] for item in sorted(cell_items, key=lambda item: item["x1"])
            )
            cell_text = _escape_markdown_cell(cell_text)
            if cell_text:
                occupied_cells += 1
            rendered_cells.append(cell_text)
        if occupied_cells >= 2:
            multi_cell_rows += 1
        rendered_rows.append(rendered_cells)

    if multi_cell_rows < 2 or sum(bool(value) for value in rendered_rows[0]) < 2:
        return None

    markdown_lines = ["| " + " | ".join(rendered_rows[0]) + " |"]
    markdown_lines.append("|" + "|".join("---" for _ in column_anchors) + "|")
    markdown_lines.extend(
        "| " + " | ".join(row) + " |"
        for row in rendered_rows[1:]
    )
    return "\n".join(markdown_lines)

def _render_table_aware_page(items, med_h, max_x2, table_regions):
    successful_tables = []
    used_item_ids = set()
    for table_region in sorted(table_regions, key=lambda box: (box[1], box[0])):
        table_items = [
            item
            for item in items
            if id(item) not in used_item_ids and _item_inside_region(item, table_region)
        ]
        markdown = _render_markdown_table(table_items, med_h)
        if markdown is None:
            continue
        successful_tables.append((table_region[1], table_region[0], markdown))
        used_item_ids.update(id(item) for item in table_items)

    if not successful_tables:
        return None

    pitch = _estimate_pitch(items)
    base_cols = int(max(max_x2 / pitch, MIN_COLS)) + COLS_MARGIN
    base_cols = min(base_cols, MAX_COLS)
    blocks = list(successful_tables)

    remaining_items = [item for item in items if id(item) not in used_item_ids]
    remaining_lines = _cluster_lines_pitch(
        sorted(remaining_items, key=lambda item: (item["ym"], item["x1"])),
        med_h,
    )
    for line in remaining_lines:
        line_text = _build_txt([line], pitch, base_cols)[0].rstrip()
        if not line_text.strip():
            continue
        blocks.append((min(item["y1"] for item in line), min(item["x1"] for item in line), line_text))

    blocks.sort(key=lambda block: (block[0], block[1]))
    return "\n".join(block[2] for block in blocks)

def page_to_pretty_txt(page: Any) -> str:
    """
    Trang -> TXT tối ưu (canh lưới, buffer động, không rstrip).
    - Tính pitch theo median(w/len(text))
    - Cột cơ sở: max(max_x2/pitch, MIN_COLS) + COLS_MARGIN, clamp MAX_COLS
    """
    items, med_h, max_x2 = _extract_items_for_pitch(page)
    if not items:
        return ""

    table_regions = _extract_layout_boxes(page, target_labels=("table",))
    if table_regions:
        table_aware_text = _render_table_aware_page(
            items,
            med_h,
            max_x2,
            table_regions,
        )
        if table_aware_text is not None:
            return table_aware_text

    lines = _cluster_lines_pitch(items, med_h)
    pitch = _estimate_pitch(items)

    base_cols = int(max(max_x2 / pitch, MIN_COLS)) + COLS_MARGIN
    base_cols = min(base_cols, MAX_COLS)

    page_lines = _build_txt(lines, pitch, base_cols)
    return "\n".join(page_lines)

def to_pretty_txt_pages(page_results: List[Any]) -> List[str]:
    return [page_to_pretty_txt(p) for p in page_results]
