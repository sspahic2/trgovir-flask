# helpers/core_extraction_logic.py

import os
import uuid
import time
from PIL import ImageDraw

from .page_extraction import run_page_extraction

def extract_shapes_and_images(app, pdf, extracted_data, indicator_texts):
    if app.config.get('TESTING'):
        timestamp = "test_timestamp"
    else:
        timestamp = str(str(time.time()) + str(uuid.uuid4()))

    global_data_index = 0
    current_page_position_text = "Pozicija_1" 
    current_page_position_order = -1
    final_payload = []
    position_group_map = {}

    for page_num, page_obj in enumerate(pdf.pages):
        page_text = page_obj.extract_text() or ""
        if not any(indicator.lower() in page_text.lower() for indicator in indicator_texts):
            continue

        page_width_pdf = page_obj.width
        page_height_pdf = page_obj.height

        tables_on_page = page_obj.find_tables(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
        if not tables_on_page:
            continue

        current_table = tables_on_page[0]
        all_cells = [cell for row in current_table.rows for cell in row.cells if cell]
        if not all_cells:
            continue

        table_x_min_pdf = min(cell[0] for cell in all_cells if cell[0] is not None)
        table_x_max_pdf = max(cell[2] for cell in all_cells if cell[2] is not None)

        try:
            pil_image_obj = page_obj.to_image(resolution=300).original
        except Exception as e:
            app.logger.error(f"Failed to render page {page_num}: {e}")
            continue

        img_width_pixels, img_height_pixels = pil_image_obj.size
        image_draw_context = ImageDraw.Draw(pil_image_obj)

        base_shapes_folder = app.config.get('EXTRACTED_SHAPES_FOLDER', 'extracted_shapes')
        page_folder = os.path.join(base_shapes_folder, str(timestamp))
        os.makedirs(page_folder, exist_ok=True)

        row_first_cell_heights = []
        for r in current_table.rows:
            first_cell = r.cells[0] if len(r.cells) > 0 else None
            row_first_cell_heights.append((first_cell[1], first_cell[3]) if first_cell else None)

        images_collected_for_page = []

        exec_globals = {
            "page_obj": page_obj,
            "table": current_table,
            "pil_image_obj": pil_image_obj,
            "image_draw_context": image_draw_context,
            "page_width_pdf": page_width_pdf,
            "page_height_pdf": page_height_pdf,
            "img_width_pixels": img_width_pixels,
            "img_height_pixels": img_height_pixels,
            "table_x_min_pdf": table_x_min_pdf,
            "table_x_max_pdf": table_x_max_pdf,
            "row_first_cell_heights": row_first_cell_heights,
            "timestamp": timestamp,
            "page_folder": page_folder,
            "current_page_position_text": current_page_position_text,
            "current_page_position_order": current_page_position_order,
            "global_data_index": global_data_index,
            "images_collected_for_page": images_collected_for_page,
            "final_payload": final_payload,
            "position_group_map": position_group_map,
            "extracted_data": extracted_data,
            "app": app,
            "page_num": page_num,
            "debug_bbox_dump": True
        }

        run_page_extraction(exec_globals)

        current_page_position_text = exec_globals["current_page_position_text"]
        current_page_position_order = exec_globals["current_page_position_order"]
        global_data_index = exec_globals["global_data_index"]

        try:
            pil_image_obj.save(os.path.join(page_folder, f"preview_{page_num}.png"))
        except Exception as e:
            app.logger.error(f"Failed to save preview image for page {page_num}: {e}")

    return final_payload
