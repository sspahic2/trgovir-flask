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
                            page.crop(cell).extract_text() if cell else ""
                            for cell in row.cells
                        ])
                    ).lower()

                    if "mreže - specifikacija" in row_text:
                        break  # stop parsing rows for this page

                    # 👇 Use backup_field_mappings for 12-cell rows
                    if len(row.cells) == 12:
                        used_mapping = {
                            "diameter": 6,
                            "lg": 8,
                            "n": 10,
                            "lgn": 11
                        }
                    else:
                        used_mapping = self.field_mapping

                    mapped_row = {}
                    for field_name, idx in used_mapping.items():
                        if idx < len(row.cells):
                            bbox = row.cells[idx]
                            if bbox:
                                value = page.crop(bbox).extract_text()
                                value = self.clean_number(f"{value}")
                            else:
                                value = None
                        else:
                            value = None
                        mapped_row[field_name] = value

                    if any(mapped_row.values()):
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
            "Šipke-Specifikacija", "Šipke - Specifikacija"
        ],
        field_mapping={
            "diameter": 2,
            "lg": 3,
            "n": 4,
            "lgn": 5
        }
    )

    data = extractor.run()
    print(json.dumps(data, indent=2))
