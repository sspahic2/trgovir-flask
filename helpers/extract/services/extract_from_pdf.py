# helpers/services/extract_from_pdf.py

import os
import time
import uuid
from PIL import ImageDraw
from helpers.extract.core.page_extraction import run_page_extraction

def extract_from_pdf(app, pdf, extracted_data, indicator_texts):
    timestamp = "test_timestamp" if app.config.get("TESTING") else str(time.time()) + str(uuid.uuid4())

    final_payload = []
    position_group_map = {}
    global_data_index = 0
    current_position = "Pozicija_1"
    current_order = -1

    for page_num, page_obj in enumerate(pdf.pages):
        text = page_obj.extract_text() or ""
        if not any(ind.lower() in text.lower() for ind in indicator_texts):
            continue

        tables = page_obj.find_tables({
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines"
        })

        if not tables:
            continue

        table = tables[0]
        all_cells = [cell for row in table.rows for cell in row.cells if cell]
        if not all_cells:
            continue

        try:
            image = page_obj.to_image(resolution=300).original
        except Exception as e:
            app.logger.error(f"Page {page_num} render failed: {e}")
            continue

        folder = os.path.join(app.config.get("EXTRACTED_SHAPES_FOLDER", "extracted_shapes"), str(timestamp))
        os.makedirs(folder, exist_ok=True)

        ctx = {
            "page_num": page_num,
            "page_obj": page_obj,
            "page_width_pdf": page_obj.width,
            "page_height_pdf": page_obj.height,
            "pil_image_obj": image,
            "image_draw_context": ImageDraw.Draw(image),
            "img_width_pixels": image.width,
            "img_height_pixels": image.height,
            "table": table,
            "table_x_min_pdf": min(cell[0] for cell in all_cells),
            "table_x_max_pdf": max(cell[2] for cell in all_cells),
            "row_first_cell_heights": [
                (r.cells[0][1], r.cells[0][3]) if len(r.cells) > 0 and r.cells[0] else None
                for r in table.rows
            ],
            "page_folder": folder,
            "timestamp": timestamp,
            "current_page_position_text": current_position,
            "current_page_position_order": current_order,
            "global_data_index": global_data_index,
            "images_collected_for_page": [],
            "extracted_data": extracted_data,
            "position_group_map": position_group_map,
            "final_payload": final_payload,
            "app": app
        }

        run_page_extraction(ctx)

        current_position = ctx["current_page_position_text"]
        current_order = ctx["current_page_position_order"]
        global_data_index = ctx["global_data_index"]

        try:
            image.save(os.path.join(folder, f"preview_{page_num}.png"))
        except Exception as e:
            app.logger.error(f"Preview image save failed: {e}")

    return final_payload
