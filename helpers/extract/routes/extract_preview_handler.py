# helpers/routes/extract_preview_handler.py

import os
import time
import uuid
import io
import pdfplumber
from flask import current_app as app

from extractor import PDFSelectiveNumericTableExtractor
from helpers.extract.services.extract_from_pdf import extract_from_pdf

def run_extract_preview(request):
    indicator_texts = [
        "Šipke - specifikacija", "Šipke-specifikacija",
        "šipke-Specifikacija", "šipke - Specifikacija",
        "Šipke-Specifikacija", "Šipke - Specifikacija",
        "SPECIFIKACIJA - Armaturne šipke"
    ]
    field_mapping = { "ozn": 0, "diameter": 2, "lg": 3, "n": 4, "lgn": 5 }
    columns_to_extract = [0, 2, 3, 4, 5]

    pdf = None

    if 'file' not in request.files or request.files['file'].filename == '':
        default_path = "SPECIFIKACIJA ARMATURE ZIDOVA 2.SPRATA ISPRAVLJENO.pdf"
        if not os.path.exists(default_path):
            return { "error": "Default PDF not found" }, 500
        try:
            pdf = pdfplumber.open(default_path)
        except Exception:
            return { "error": "Could not open default PDF" }, 500
    else:
        uploaded = request.files['file']
        if not ('.' in uploaded.filename and uploaded.filename.rsplit('.', 1)[1].lower() == "pdf"):
            return { "error": "Invalid file type" }, 400
        try:
            pdf = pdfplumber.open(io.BytesIO(uploaded.read()))
        except Exception:
            return { "error": "Could not process uploaded file" }, 500

    if not pdf:
        return { "error": "PDF object could not be initialized" }, 500

    extractor = PDFSelectiveNumericTableExtractor(
        pdf=pdf,
        pdf_path="default.pdf",
        columns_to_extract=columns_to_extract,
        indicator_texts=indicator_texts,
        field_mapping=field_mapping
    )

    extracted_data = extractor.run()
    return extract_from_pdf(app, pdf, extracted_data, indicator_texts)
