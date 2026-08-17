# App/annotate.py
from pathlib import Path
from typing import Dict
from PIL import Image

def _save_fullres(img: Image.Image, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() in {".jpg", ".jpeg"}:
        img.convert("RGB").save(out_path, quality=95, subsampling=0)
    else:
        img.save(out_path)

def save_annot_images(per_page_imgs: Dict[str, Image.Image],
                      out_dir: Path,
                      page_idx: int,
                      fmt: str = "png",
                      stem: str | None = None) -> None:
    """
    Lưu ảnh annotate. Nếu cung cấp stem (tên file pdf không đuôi),
    sẽ lưu vào outputs/annot_images/<stem>/... 
    """
    preferred = ["overall_ocr_res", "layout_det_res", "text_paragraphs_ocr_res"]
    keys = [k for k in per_page_imgs if k in preferred] or list(per_page_imgs.keys())
    if "overall_ocr_res" in per_page_imgs:
        keys = ["overall_ocr_res"]

    if stem:
        out_dir = out_dir / stem

    for key in keys:
        img = per_page_imgs[key].convert("RGB")
        out_file = out_dir / f"annot_p{page_idx:02d}_{key}.{fmt}"
        _save_fullres(img, out_file)
