import os
import json
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
    debug_bbox_dump = g.get("debug_bbox_dump", False)

    x_scale = width_img / width_pdf
    y_scale = height_img / height_pdf

    visual_objects = []
    for obj_type in ["line", "rect", "curve"]:
        for idx, obj in enumerate(page_obj.objects.get(obj_type, [])):
            bbox = scale_visual_bbox(obj, x_scale, y_scale, height_img)
            width_px = bbox["x1"] - bbox["x0"]
            height_px = bbox["y1"] - bbox["y0"]
            if width_px <= 1 and height_px <= 1:
                continue
            bbox['source'] = f'visual:{obj_type}'
            bbox['index'] = idx
            bbox['pdf_x0'] = min(obj.get('x0', 0), obj.get('x1', 0))
            bbox['pdf_x1'] = max(obj.get('x0', 0), obj.get('x1', 0))
            bbox['pdf_y0'] = min(obj.get('y0', 0), obj.get('y1', 0))
            bbox['pdf_y1'] = max(obj.get('y0', 0), obj.get('y1', 0))
            bbox['width'] = width_px
            bbox['height'] = height_px
            visual_objects.append(bbox)

    try:
        word_objects = []
        for idx, w in enumerate(page_obj.extract_words()):
            bbox = scale_word_bbox(w, width_pdf, height_pdf, width_img, height_img)
            bbox['source'] = 'word'
            bbox['index'] = idx
            bbox['text'] = w.get('text')
            bbox['pdf_x0'] = w.get('x0')
            bbox['pdf_x1'] = w.get('x1')
            bbox['pdf_y0'] = w.get('top')
            bbox['pdf_y1'] = w.get('bottom')
            word_objects.append(bbox)
    except Exception as e:
        app.logger.warning(f"[page {page_num}] Failed to extract words: {e}")
        word_objects = []

    all_objects = visual_objects + word_objects

    for row_index, row_obj in enumerate(table.rows):
        for cell_index, cell_coords in enumerate(row_obj.cells):
            if cell_coords is None:
                continue

            x0_pdf, _, x1_pdf, _ = cell_coords
            inset_x = 5
            inset_y = 10

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

            scaled_x0 = ((x0_pdf / width_pdf) * width_img) + inset_x
            scaled_y0 = ((y0_pdf / height_pdf) * height_img) + inset_y
            scaled_x1 = ((x1_pdf / width_pdf) * width_img) - inset_x
            scaled_y1 = ((y1_pdf / height_pdf) * height_img) - inset_y

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

                    pad_x = 0
                    pad_y = 0
                    scaled_crop_x0 = max(0, obj_x0 - pad_x)
                    scaled_crop_y0 = min(scaled_y0, max(0, obj_y0 - pad_y))
                    scaled_crop_x1 = min(width_img, obj_x1 + pad_x)
                    scaled_crop_y1 = max(scaled_y1, min(height_img, obj_y1 + pad_y))

                    if debug_bbox_dump:
                        sorted_objects = sorted(content_objects, key=lambda o: (o["x0"], o["y0"]))
                        serialized_objects = []
                        visual_serialized = []
                        for item in sorted_objects:
                            obj_data = {
                                "source": item.get("source"),
                                "index": item.get("index"),
                                "text": item.get("text"),
                                "bbox": [item["x0"], item["y0"], item["x1"], item["y1"]],
                                "pdf_bbox": [item.get("pdf_x0"), item.get("pdf_y0"), item.get("pdf_x1"), item.get("pdf_y1")],
                                "width": (item["x1"] - item["x0"]),
                                "height": (item["y1"] - item["y0"])
                            }
                            serialized_objects.append(obj_data)
                            if str(item.get("source", "")).startswith("visual"):
                                visual_serialized.append(obj_data)
                        debug_payload = {
                            "page": page_num,
                            "row_index": row_index,
                            "cell_index": cell_index,
                            "scaled_cell_bbox": [scaled_x0, scaled_y0, scaled_x1, scaled_y1],
                            "scaled_crop_bbox": [scaled_crop_x0, scaled_crop_y0, scaled_crop_x1, scaled_crop_y1],
                            "min_object_x0": obj_x0,
                            "max_object_x1": obj_x1,
                            "left_gap_pixels": scaled_crop_x0 - obj_x0,
                            "objects": serialized_objects,
                            "visual_objects_in_cell": visual_serialized,
                            "cell_inset_x": inset_x,
                            "cell_inset_y": inset_y,
                            "pad_x": pad_x,
                            "pad_y": pad_y,
                            "scaled_cell_x0": scaled_x0,
                            "scaled_cell_x1": scaled_x1
                        }
                        debug_filename = f"page_{page_num}_row_{row_index}_cell_{cell_index}_debug.json"
                        debug_path = os.path.join(folder, debug_filename)
                        try:
                            with open(debug_path, 'w', encoding='utf-8') as debug_file:
                                json.dump(debug_payload, debug_file, indent=2)
                        except Exception as err:
                            app.logger.warning(f'[page {page_num}] Failed to write bbox debug data for row {row_index}, cell {cell_index}: {err}')

                elif debug_bbox_dump:
                    debug_payload = {
                        "page": page_num,
                        "row_index": row_index,
                        "cell_index": cell_index,
                        "scaled_cell_bbox": [scaled_x0, scaled_y0, scaled_x1, scaled_y1],
                        "scaled_crop_bbox": [scaled_crop_x0, scaled_crop_y0, scaled_crop_x1, scaled_crop_y1],
                        "min_object_x0": None,
                        "max_object_x1": None,
                        "left_gap_pixels": None,
                        "objects": [],
                        "visual_objects_in_cell": [],
                        "cell_inset_x": inset_x,
                        "cell_inset_y": inset_y,
                        "pad_x": 0,
                        "pad_y": 0,
                        "scaled_cell_x0": scaled_x0,
                        "scaled_cell_x1": scaled_x1
                    }
                    debug_filename = f"page_{page_num}_row_{row_index}_cell_{cell_index}_debug.json"
                    debug_path = os.path.join(folder, debug_filename)
                    try:
                        with open(debug_path, 'w', encoding='utf-8') as debug_file:
                            json.dump(debug_payload, debug_file, indent=2)
                    except Exception as err:
                        app.logger.warning(f'[page {page_num}] Failed to write bbox debug data for row {row_index}, cell {cell_index}: {err}')

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
