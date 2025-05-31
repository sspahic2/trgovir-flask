import os
from PIL import ImageDraw

from helpers.extract.core.scaling_utils import (
    scale_visual_bbox,
    scale_word_bbox
)

def run_page_extraction(g):
    page_obj = g["page_obj"]
    table = g["table"]
    image = g["pil_image_obj"]
    draw = g["image_draw_context"]
    width_pdf = g["page_width_pdf"]
    height_pdf = g["page_height_pdf"]
    width_img = g["img_width_pixels"]
    height_img = g["img_height_pixels"]
    xmin = g["table_x_min_pdf"]
    xmax = g["table_x_max_pdf"]
    row_heights = g["row_first_cell_heights"]
    folder = g["page_folder"]
    timestamp = g["timestamp"]
    position_text = g["current_page_position_text"]
    position_order = g["current_page_position_order"]
    global_data_index = g["global_data_index"]
    extracted_data = g["extracted_data"]
    position_group_map = g["position_group_map"]
    final_payload = g["final_payload"]
    images_collected = g["images_collected_for_page"]
    app = g["app"]
    page_num = g["page_num"]

    x_scale = width_img / width_pdf
    y_scale = height_img / height_pdf

    visual_objects = []
    for obj_type in ["line", "rect", "curve"]:
        for obj in page_obj.objects.get(obj_type, []):
            visual_objects.append(
                scale_visual_bbox(obj, x_scale, y_scale, height_img)
            )

    try:
        word_objects = [
            scale_word_bbox(w, width_pdf, height_pdf, width_img, height_img)
            for w in page_obj.extract_words()
        ]
    except Exception as e:
        app.logger.warning(f"[page {page_num}] Failed to extract words: {e}")
        word_objects = []

    all_objects = visual_objects + word_objects

    for row_index, row_obj in enumerate(table.rows):
        for cell_index, cell_coords in enumerate(row_obj.cells):
            if cell_coords is None:
                continue

            x0_pdf, _, x1_pdf, _ = cell_coords
            inset = 5

            cell_width = x1_pdf - x0_pdf
            is_wide = abs(cell_width - (xmax - xmin)) < 2

            if is_wide and row_index > 0 and row_index + 1 < len(row_heights):
                prev = row_heights[row_index - 1]
                next = row_heights[row_index + 1]
                if prev and next:
                    y_coords = sorted([prev[1], next[0]])
                    y0_pdf, y1_pdf = y_coords[0], y_coords[1]
                else:
                    y0_pdf = cell_coords[1]
                    y1_pdf = cell_coords[3]
            else:
                y0_pdf = cell_coords[1]
                y1_pdf = cell_coords[3]

            scaled_x0 = ((x0_pdf / width_pdf) * width_img) + inset
            scaled_y0 = ((y0_pdf / height_pdf) * height_img) + inset
            scaled_x1 = ((x1_pdf / width_pdf) * width_img) - inset
            scaled_y1 = ((y1_pdf / height_pdf) * height_img) - inset

            if is_wide and row_index > 0:
                try:
                    extracted_text = page_obj.crop(cell_coords).extract_text()
                    try:
                        if (
                            extracted_text.isnumeric() or
                            float(extracted_text) or
                            extracted_text == ''
                        ):
                            extracted_text = None
                    except Exception:
                        pass
                except Exception as e:
                    app.logger.warning(f"[page {page_num}] Failed to extract text from wide cell at row {row_index}: {e}")
                    extracted_text = None

                if extracted_text:
                    position_text = extracted_text.strip()
                    position_order += 1
                    draw.rectangle([scaled_x0, scaled_y0, scaled_x1, scaled_y1], outline="green", width=1)

            if cell_index == 1 and row_index != 1:
                content_objects = [
                    obj for obj in all_objects
                    if obj["x0"] >= scaled_x0 and obj["x1"] <= scaled_x1
                    and obj["y0"] >= scaled_y0 and obj["y1"] <= scaled_y1
                ]

                scaled_crop_x0 = scaled_x0
                scaled_crop_y0 = scaled_y0
                scaled_crop_x1 = scaled_x1
                scaled_crop_y1 = scaled_y1

                if content_objects:
                    obj_x0 = min(obj["x0"] for obj in content_objects)
                    obj_y0 = min(obj["y0"] for obj in content_objects)
                    obj_x1 = max(obj["x1"] for obj in content_objects)
                    obj_y1 = max(obj["y1"] for obj in content_objects)

                    pad = 0
                    scaled_crop_x0 = max(0, obj_x0 - pad)
                    scaled_crop_y0 = min(scaled_y0, max(0, obj_y0 - pad))
                    scaled_crop_x1 = min(width_img, obj_x1 + pad)
                    scaled_crop_y1 = max(scaled_y1, min(height_img, obj_y1 + pad))

                cropped = image.crop((scaled_crop_x0, scaled_crop_y0, scaled_crop_x1, scaled_crop_y1))

                filename = f"page_{page_num}_row_{row_index}_cell_1.png"
                full_path = os.path.join(folder, filename)
                try:
                    cropped.save(full_path)
                except Exception as e:
                    app.logger.error(f"Failed to save cropped shape to {full_path}: {e}")
                    continue

                img_url = os.path.join(str(timestamp), filename).replace("\\", "/")
                images_collected.append({
                    "position": position_text,
                    "img_path_segment": img_url,
                    "order": max(position_order, 0)
                })

                draw.rectangle([scaled_x0, scaled_y0, scaled_x1, scaled_y1], outline="red", width=1)

    for img in images_collected:
        if global_data_index >= len(extracted_data):
            app.logger.warning(f"Data index exceeded: {global_data_index}/{len(extracted_data)}")
            break

        row_data = extracted_data[global_data_index]
        global_data_index += 1

        row = {
            "ozn": row_data.get("ozn"),
            "diameter": row_data.get("diameter"),
            "lg": row_data.get("lg"),
            "n": row_data.get("n"),
            "lgn": row_data.get("lgn"),
            "oblikIMere": f"extracted_shapes/{img['img_path_segment']}"
        }

        if row["diameter"] == 0 and row["lg"] == 0 and row["lgn"] == 0 and row["n"] == 0:
            continue

        position = img["position"]
        order = img["order"]

        if position in position_group_map:
            position_group_map[position]["rows"].append(row)
        else:
            group = {
                "position": position,
                "order": order,
                "rows": [row]
            }
            final_payload.append(group)
            position_group_map[position] = group

    g["current_page_position_text"] = position_text
    g["current_page_position_order"] = position_order
    g["global_data_index"] = global_data_index
