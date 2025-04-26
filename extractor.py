import json
import pdfplumber
import pandas as pd
import re
from typing import List, Optional, Dict

class PDFSelectiveNumericTableExtractor:
    def __init__(self, pdf_path: str, columns_to_extract: List[int], indicator_texts: List[str], field_mapping: Dict[str, int]):
        self.pdf_path = pdf_path
        self.columns_to_extract = columns_to_extract  # 0-based indexes of the columns you want
        self.indicator_texts = indicator_texts  # list of strings that must appear on the page
        self.field_mapping = field_mapping  # {"field_name": column_index}
        self.rows = []

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
        with pdfplumber.open(self.pdf_path) as pdf:
            for page in pdf.pages:
                if self.page_contains_indicator(page):
                    tables = page.extract_tables()
                    if not tables:
                        continue
                    for table in tables:
                        for row in table:
                            mapped_row = {}
                            for field_name, idx in self.field_mapping.items():
                                if idx < len(row):
                                    value = self.clean_number(row[idx])
                                    mapped_row[field_name] = value
                                else:
                                    mapped_row[field_name] = None
                            if any(mapped_row.values()):  # At least one number present
                                self.rows.append(mapped_row)

    def to_json(self):
        return self.rows  # It’s already a list of dictionaries

    def run(self):
        self.extract()
        return self.to_json()

# Example usage

if __name__ == "__main__":
    extractor = PDFSelectiveNumericTableExtractor(
        pdf_path="SPECIFIKACIJA ARMATURE ZIDOVA 2.SPRATA ISPRAVLJENO.pdf",
        columns_to_extract=[2, 3, 4, 5],  # optional now because mapping is enough
        indicator_texts=[
            "Šiple - specifikacija", "Šipke-specifikacija",
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
    print(json.dumps(data))
