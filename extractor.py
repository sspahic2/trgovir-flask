import json
import pdfplumber
import os
import re
from typing import List, Optional, Dict

class PDFSelectiveNumericTableExtractor:
    def __init__(self, pdf_path: str, columns_to_extract: List[int], indicator_texts: List[str], field_mapping: Dict[str, int], pdf = None):
        self.pdf_path = pdf_path
        self.columns_to_extract = columns_to_extract
        self.indicator_texts = indicator_texts
        self.field_mapping = field_mapping
        self.rows = []
        self.pdf = pdf

    def clean_number(self, value: str) -> Optional[float | int]:
        if(value == ''): return 0

        if not value:
            return None
        value = value.strip()
        value = re.sub(r'[^0-9\.\-]', '', value)
        try:
            num = float(value)
            if num.is_integer():
                return int(num)
            return num
        except ValueError:
            return None
        
    def clamp_bbox(self, bbox, page):
        x0, y0, x1, y1 = bbox
        page_x0, page_y0, page_x1, page_y1 = page.bbox
        return (
            max(x0, page_x0),
            max(y0, page_y0),
            min(x1, page_x1),
            min(y1, page_y1)
        )

    def page_contains_indicator(self, page) -> bool:
        text = page.extract_text()
        if not text:
            return False
        for indicator in self.indicator_texts:
            if indicator.lower() in text.lower():
                return True
        return False

    def extract(self):
        if self.pdf is not None:
            pdf = self.pdf
        else:
            pdf = pdfplumber.open(self.pdf_path)

        for page_num, page in enumerate(pdf.pages):
            if not self.page_contains_indicator(page):
                continue

            table_settings = {
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
            }
            tables = page.find_tables(table_settings=table_settings)
            if not tables:
                continue

            for table_idx, table in enumerate(tables):
                for row_idx, row in enumerate(table.rows):
                    # 🛑 STOP parsing more rows if this row contains the stop keyword
                    row_text = " ".join(
                        filter(None, [
                            page.crop(self.clamp_bbox(cell, page)).extract_text() if cell else ""
                            for cell in row.cells
                        ])
                    ).lower()

                    if ("mreže - specifikacija" or "mreže - rekapitulacija" or "šipke - rekapitulacija") in row_text:
                        break  # stop parsing rows for this page

                    # 👇 Use backup_field_mappings for 12-cell rows
                    # print("Length of cells ",len(row.cells))
                    if len(row.cells) == 12:
                        used_mapping = {
                            "ozn": 0,
                            "diameter": 6,
                            "lg": 8,
                            "n": 10,
                            "lgn": 11
                        }
                    elif len(row.cells) == 10:
                        used_mapping = {
                            "ozn": 0,
                            "diameter": 3,
                            "lg": 5,
                            "n": 6,
                            "lgn": 8
                        }
                    elif len(row.cells) == 16:
                        used_mapping = {
                            "ozn": 0,
                            "diameter": 7,
                            "lg": 9,
                            "n": 11,
                            "lgn": 13
                        }
                    elif len(row.cells) == 9:
                        used_mapping = {
                            "ozn": 0,
                            "diameter": 4,
                            "lg": 5,
                            "n":7,
                            "lgn": 8
                        }
                    else:
                        used_mapping = self.field_mapping

                    mapped_row = {}
                    for field_name, idx in used_mapping.items():
                        if idx < len(row.cells):
                            bbox = row.cells[idx]
                            if bbox:
                                value = page.crop(self.clamp_bbox(bbox, page)).extract_text().replace(',', '.')
                                # print(value, "My idx " + str(idx) + " " + field_name)
                                value = self.clean_number(f"{value}")
                            else:
                                value = None
                        else:
                            value = None
                        mapped_row[field_name] = value

                    none_count = sum(1 for v in mapped_row.values() if v is None)
                    if none_count < 2:
                        self.rows.append(mapped_row)



    def to_json(self):
        return self.rows

    def run(self):
        self.extract()
        return self.to_json()

# Example usage
if __name__ == "__main__":
    extractor = PDFSelectiveNumericTableExtractor(
        pdf_path="SPECIFIKACIJA ARMATURE ZIDOVA 2.SPRATA ISPRAVLJENO.pdf",
        columns_to_extract=[2, 3, 4, 5],
        indicator_texts=[
            "Šipke - specifikacija", "Šipke-specifikacija",
            "šipke-Specifikacija", "šipke - Specifikacija",
            "Šipke-Specifikacija", "Šipke - Specifikacija",
            "Šipke specifikacija"
        ],
        field_mapping={
            "ozn": 0,
            "diameter": 2,
            "lg": 3,
            "n": 4,
            "lgn": 5
        }
    )

    data = extractor.run()
    # print(json.dumps(data, indent=2))
