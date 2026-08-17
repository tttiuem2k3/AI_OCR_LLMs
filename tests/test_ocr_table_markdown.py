import unittest

from App.OCR_BE.text_format import to_pretty_txt_pages


def _poly(x1, y1, x2, y2):
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _page(texts, boxes, table_box=None):
    layout_boxes = []
    if table_box is not None:
        layout_boxes.append({"label": "table", "coordinate": list(table_box)})
    return {
        "overall_ocr_res": {
            "rec_texts": texts,
            "rec_polys": [_poly(*box) for box in boxes],
        },
        "layout_det_res": {"boxes": layout_boxes},
    }


class OCRTableMarkdownTests(unittest.TestCase):
    def test_table_region_renders_as_markdown_table(self):
        page = _page(
            [
                "HS Code", "Description", "Qty", "Value",
                "850440", "Converter", "20", "5000 USD",
            ],
            [
                (10, 10, 70, 25), (90, 10, 170, 25), (190, 10, 220, 25), (240, 10, 320, 25),
                (10, 40, 70, 55), (90, 40, 170, 55), (190, 40, 220, 55), (240, 40, 320, 55),
            ],
            table_box=(0, 0, 340, 70),
        )

        text = to_pretty_txt_pages([page])[0]

        self.assertIn("| HS Code | Description | Qty | Value |", text)
        self.assertIn("|---|---|---|---|", text)
        self.assertIn("| 850440 | Converter | 20 | 5000 USD |", text)

    def test_table_and_non_table_text_keep_reading_order(self):
        page = _page(
            [
                "Invoice detail",
                "HS Code", "Description",
                "850440", "Converter",
                "Payment due",
            ],
            [
                (10, 5, 130, 20),
                (10, 40, 70, 55), (90, 40, 180, 55),
                (10, 70, 70, 85), (90, 70, 180, 85),
                (10, 110, 120, 125),
            ],
            table_box=(0, 30, 200, 95),
        )

        text = to_pretty_txt_pages([page])[0]

        self.assertLess(text.index("Invoice detail"), text.index("| HS Code | Description |"))
        self.assertLess(text.index("| 850440 | Converter |"), text.index("Payment due"))

    def test_page_without_table_region_keeps_pretty_text_behavior(self):
        page = _page(
            ["A", "B", "C"],
            [(0, 0, 10, 10), (50, 0, 60, 10), (0, 30, 10, 40)],
        )

        text = to_pretty_txt_pages([page])[0]

        self.assertNotIn("|---|", text)
        self.assertIn("A", text)
        self.assertIn("B", text)
        self.assertIn("C", text)

    def test_weak_table_candidate_falls_back_to_text(self):
        page = _page(
            ["Only one row", "Value"],
            [(10, 10, 100, 25), (140, 10, 190, 25)],
            table_box=(0, 0, 220, 40),
        )

        text = to_pretty_txt_pages([page])[0]

        self.assertNotIn("|---|", text)
        self.assertIn("Only one row", text)
        self.assertIn("Value", text)


if __name__ == "__main__":
    unittest.main()
