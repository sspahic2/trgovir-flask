import io
import time
import uuid
from flask import Flask, abort, request, jsonify, send_from_directory
import os
from flask_cors import CORS
from werkzeug.utils import secure_filename, safe_join

from extractor import PDFSelectiveNumericTableExtractor
import pdfplumber
from PIL import ImageDraw

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}
EXTRACTED_SHAPES_FOLDER = 'extracted_shapes'
MAGIC_NUMBER = 3
os.makedirs(EXTRACTED_SHAPES_FOLDER, exist_ok=True)
BASE_URL = "http://127.0.0.1:5000/"

app = Flask(__name__)
CORS(app, origins=[
    "https://trgovir.vercel.app",
    "http://localhost:3000"
], supports_credentials=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# if not os.path.exists(UPLOAD_FOLDER):
#     os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def object_in_any_row_y(obj, row_bboxes, margin=1):
    oy0 = obj['y0']
    oy1 = obj['y1']
    for row_y0, row_y1 in row_bboxes:
        if not (oy1 < row_y0 - margin or oy0 > row_y1 + margin):
            return True
    return False

@app.route('/extracted_shapes/<path:timestamp>/<path:filename>')
def serve_extracted_shape(timestamp, filename):
    # only allow common image extensions
    if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        abort(403)

    # assemble the absolute directory path
    directory = safe_join(app.root_path, EXTRACTED_SHAPES_FOLDER, timestamp)
    full_path = os.path.join(directory, filename)

    # debug logging to verify the lookup path
    app.logger.debug(f"Looking for shape file at: {full_path}")

    if not os.path.isfile(full_path):
        app.logger.error(f"Shape file not found: {full_path}")
        abort(404)

    # serve the file
    return send_from_directory(directory, filename)

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin')
    allowed_origins = {"https://trgovir.vercel.app", "http://localhost:3000"}
    if origin in allowed_origins:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response

@app.route('/extract-preview', methods=['OPTIONS'])
def extract_preview_options():
    return '', 200

@app.route('/extract', methods=['POST'])
def extract_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in request'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        extractor = PDFSelectiveNumericTableExtractor(
            pdf_path=file_path,
            columns_to_extract=[0, 2, 3, 4, 5],
            indicator_texts=[
                "Šiple - specifikacija", "Šipke-specifikacija",
                "šipke-Specifikacija", "šipke - Specifikacija",
                "Šipke-Specifikacija", "Šipke - Specifikacija",
                "SPECIFIKACIJA - Armaturne šipke"
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
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError as e:
                app.logger.error(f"Error removing uploaded file {file_path}: {e}")
        return jsonify(data)

    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/extract-preview', methods=['POST'])
def extract_preview():
    indicator_texts = [
        "Šipke - specifikacija", "Šipke-specifikacija",
        "šipke-Specifikacija", "šipke - Specifikacija",
        "Šipke-Specifikacija", "Šipke - Specifikacija",
        "SPECIFIKACIJA - Armaturne šipke"
    ]
    field_mapping = { "ozn": 0, "diameter": 2, "lg": 3, "n": 4, "lgn": 5 }
    columns_to_extract = [0, 2, 3, 4, 5]

    pdf_plumber_instance = None
    is_default_pdf = False

    if 'file' not in request.files or request.files['file'].filename == '':
        default_pdf_path = "SPECIFIKACIJA ARMATURE ZIDOVA 2.SPRATA ISPRAVLJENO.pdf"
        if not os.path.exists(default_pdf_path):
            app.logger.error(f"Default PDF not found: {default_pdf_path}")
            return jsonify({'error': 'Default PDF not found'}), 500
        try:
            pdf_plumber_instance = pdfplumber.open(default_pdf_path)
            is_default_pdf = True
        except Exception as e:
            app.logger.error(f"Error opening default PDF {default_pdf_path}: {e}")
            return jsonify({'error': 'Could not open default PDF'}), 500
    else:
        uploaded_file = request.files['file']
        if not allowed_file(uploaded_file.filename):
            return jsonify({'error': 'Invalid file type'}), 400
        try:
            file_bytes = uploaded_file.read()
            pdf_plumber_instance = pdfplumber.open(io.BytesIO(file_bytes))
        except Exception as e:
            app.logger.error(f"Error processing uploaded file {uploaded_file.filename}: {e}")
            return jsonify({'error': 'Could not process uploaded file'}), 500

    if not pdf_plumber_instance:
        return jsonify({'error': 'PDF object could not be initialized'}), 500

    extractor = PDFSelectiveNumericTableExtractor(
        pdf=pdf_plumber_instance,
        pdf_path="default.pdf",
        columns_to_extract=columns_to_extract,
        indicator_texts=indicator_texts,
        field_mapping=field_mapping
    )
    extracted_data = extractor.run()
    
    timestamp = str( str(time.time()) + str(uuid.uuid4()))
    global_data_index = 0
    current_page_position_text = "Pozicija_1" 
    current_page_position_order = -1
    final_payload = []
    position_group_map = {}

    for page_num, page_obj in enumerate(pdf_plumber_instance.pages):
        page_text = page_obj.extract_text() or ""

        if any(indicator.lower() in page_text.lower() for indicator in indicator_texts):
            page_width_pdf = page_obj.width
            page_height_pdf = page_obj.height

            table_settings = { "vertical_strategy": "lines", "horizontal_strategy": "lines" }
            tables_on_page = page_obj.find_tables(table_settings=table_settings)

            if not tables_on_page:
                continue
            
            current_table = tables_on_page[0]
            
            all_cells_in_table = [cell for row in current_table.rows for cell in row.cells if cell]
            if not all_cells_in_table: continue

            table_x_min_pdf = min(cell[0] for cell in all_cells_in_table if cell[0] is not None)
            table_x_max_pdf = max(cell[2] for cell in all_cells_in_table if cell[2] is not None)
            
            if table_x_min_pdf is None or table_x_max_pdf is None : continue

            if page_obj is None or not hasattr(page_obj, "to_image"):
                app.logger.warning(f"Skipping page {page_num}, not a valid page object")
                continue

            if page_num >= len(pdf_plumber_instance.pages):
                app.logger.warning(f"Page {page_num} out of bounds")
                continue

            try:
                page_pil_image = page_obj.to_image(resolution=300)
                pil_image_obj = page_pil_image.original
            except Exception as e:
                app.logger.error(f"Failed to render page {page_num} to image: {e}")
                continue

            img_width_pixels, img_height_pixels = pil_image_obj.size
            image_draw_context = ImageDraw.Draw(pil_image_obj)

            # # DEBUG: Draw red boxes around all detected words
            # for word in page_obj.extract_words():
            #     x0 = (word["x0"] / page_width_pdf) * img_width_pixels
            #     y0 = (word["top"] / page_height_pdf) * img_height_pixels
            #     x1 = (word["x1"] / page_width_pdf) * img_width_pixels
            #     y1 = (word["bottom"] / page_height_pdf) * img_height_pixels
            #     image_draw_context.rectangle([x0, y0, x1, y1], outline="red", width=1)

            x_scale = img_width_pixels / page_width_pdf
            y_scale = img_height_pixels / page_height_pdf

            # for obj_type in ["line", "rect", "curve"]:
            #     for obj in page_obj.objects.get(obj_type, []):
            #         try:
            #             x0 = obj["x0"] * x_scale
            #             x1 = obj["x1"] * x_scale
            #             y0 = img_height_pixels - (obj["y1"] * y_scale)
            #             y1 = img_height_pixels - (obj["y0"] * y_scale)
            #             image_draw_context.rectangle([x0, y0, x1, y1], outline="red", width=1)
            #         except Exception as e:
            #             app.logger.warning(f"Failed to draw object: {e}")


            page_specific_image_folder = os.path.join(EXTRACTED_SHAPES_FOLDER, str(timestamp))
            os.makedirs(page_specific_image_folder, exist_ok=True)
            
            images_collected_for_page = []

            # Pre-compute Y-bounds from first column for all rows
            row_first_cell_heights = []
            for r in current_table.rows:
                first_cell = r.cells[0] if len(r.cells) > 0 else None
                if first_cell:
                    row_first_cell_heights.append((first_cell[1], first_cell[3]))  # (y0, y1)
                else:
                    row_first_cell_heights.append(None)

            for row_index, row_obj in enumerate(current_table.rows):
                for cell_index, cell_coords_pdf in enumerate(row_obj.cells):
                    if cell_coords_pdf is None:
                        continue

                    x0_pdf, _, x1_pdf, _ = cell_coords_pdf  # Width still comes from actual cell
                    inset = 5  # leave as is

                    # Check if cell is wide
                    cell_width_pdf = x1_pdf - x0_pdf
                    is_wide_cell = abs(cell_width_pdf - (table_x_max_pdf - table_x_min_pdf)) < 2

                    # Compute y0 and y1
                    if is_wide_cell and row_index > 0 and row_index + 1 < len(row_first_cell_heights):
                        prev = row_first_cell_heights[row_index - 1]
                        next = row_first_cell_heights[row_index + 1]
                        if prev and next:
                            y_coords = sorted([prev[1], next[0]])
                            y0_pdf, y1_pdf = y_coords[0], y_coords[1]
                        else:
                            y0_pdf = cell_coords_pdf[1]
                            y1_pdf = cell_coords_pdf[3]
                    else:
                        y0_pdf = cell_coords_pdf[1]
                        y1_pdf = cell_coords_pdf[3]

                    scaled_x0 = ((x0_pdf / page_width_pdf) * img_width_pixels) + inset
                    scaled_y0 = ((y0_pdf / page_height_pdf) * img_height_pixels) + inset
                    scaled_x1 = ((x1_pdf / page_width_pdf) * img_width_pixels) - inset
                    scaled_y1 = ((y1_pdf / page_height_pdf) * img_height_pixels) - inset

                    if is_wide_cell and row_index > 0: 
                        try:
                            extracted_text_from_cell = page_obj.crop(cell_coords_pdf).extract_text()
                        except Exception as e:
                            app.logger.warning(f"[page {page_num}] Failed to extract text from wide cell at row {row_index}: {e}")
                            extracted_text_from_cell = None

                        if extracted_text_from_cell:
                            current_page_position_text = extracted_text_from_cell.strip()
                            current_page_position_order = current_page_position_order + 1
                        image_draw_context.rectangle([scaled_x0, scaled_y0, scaled_x1, scaled_y1], outline="green", width=1)

                    if cell_index == 1 and row_index != 1:
                        visual_objects = []

                        for obj_type in ["line", "rect", "curve"]:
                            for obj in page_obj.objects.get(obj_type, []):
                                x0 = obj["x0"] * x_scale
                                x1 = obj["x1"] * x_scale
                                y0 = img_height_pixels - (obj["y1"] * y_scale)
                                y1 = img_height_pixels - (obj["y0"] * y_scale)
                                visual_objects.append({
                                    "x0": min(x0, x1),
                                    "x1": max(x0, x1),
                                    "y0": min(y0, y1),
                                    "y1": max(y0, y1)
                                })

                        # Normalize keys for words
                        word_objects = []
                        try:
                            for word in page_obj.extract_words():
                                x0 = (word["x0"] / page_width_pdf) * img_width_pixels
                                y0 = (word["top"] / page_height_pdf) * img_height_pixels
                                x1 = (word["x1"] / page_width_pdf) * img_width_pixels
                                y1 = (word["bottom"] / page_height_pdf) * img_height_pixels
                                word_objects.append({
                                    "x0": x0,
                                    "x1": x1,
                                    "y0": y0,
                                    "y1": y1
                                })
                        except Exception as e:
                            app.logger.warning(f"[page {page_num}] Failed to extract words: {e}")
                            word_objects = []

                        content_objects = [
                            obj for obj in (word_objects + visual_objects)
                            if obj["x0"] >= scaled_x0 and obj["x1"] <= scaled_x1
                            and obj["y0"] >= scaled_y0 and obj["y1"] <= scaled_y1
                        ]

                        # Default to full cell area
                        scaled_crop_x0 = scaled_x0
                        scaled_crop_y0 = scaled_y0
                        scaled_crop_x1 = scaled_x1
                        scaled_crop_y1 = scaled_y1

                        if content_objects:
                            obj_x0 = min(obj["x0"] for obj in content_objects)
                            obj_y0 = min(obj["y0"] for obj in content_objects)
                            obj_x1 = max(obj["x1"] for obj in content_objects)
                            obj_y1 = max(obj["y1"] for obj in content_objects)

                            pad = 0  # we’re going to fix padding another way
                            scaled_crop_x0 = max(0, obj_x0 - pad)
                            scaled_crop_y0 = min(scaled_y0, max(0, obj_y0 - pad))
                            scaled_crop_x1 = min(img_width_pixels, obj_x1 + pad)
                            scaled_crop_y1 = max(scaled_y1, min(img_height_pixels, obj_y1 + pad))

                            cropped_shape_image = pil_image_obj.crop((scaled_crop_x0, scaled_crop_y0, scaled_crop_x1, scaled_crop_y1))
                        else:
                            # fallback to full cell bounding box
                            cropped_shape_image = pil_image_obj.crop((scaled_x0, scaled_y0, scaled_x1, scaled_y1))

                        img_filename = f"page_{page_num}_row_{row_index}_cell_1.png"
                        img_full_save_path = os.path.join(page_specific_image_folder, img_filename)
                        try:
                            cropped_shape_image.save(img_full_save_path)
                        except Exception as e:
                            app.logger.error(f"Failed to save cropped shape to {img_full_save_path}: {e}")
                            continue

                        img_path_segment_for_url = os.path.join(str(timestamp), img_filename).replace("\\", "/")
                        images_collected_for_page.append({
                            'position': current_page_position_text,
                            'img_path_segment': img_path_segment_for_url,
                            'order': max(current_page_position_order, 0)
                        })

                        image_draw_context.rectangle([scaled_x0, scaled_y0, scaled_x1, scaled_y1], outline="red", width=1)

            for img_details in images_collected_for_page:
                if global_data_index >= len(extracted_data):
                    app.logger.warning(f"Data list exhausted. global_data_index: {global_data_index}, len(data): {len(extracted_data)}")
                    break

                current_data_item = extracted_data[global_data_index]
                global_data_index += 1

                position = img_details["position"]
                order = img_details["order"]
                image_url = f"extracted_shapes/{img_details['img_path_segment']}"

                row = {
                    "ozn": current_data_item.get('ozn'),
                    "diameter": current_data_item.get('diameter'),
                    "lg": current_data_item.get('lg'),
                    "n": current_data_item.get('n'),
                    "lgn": current_data_item.get('lgn'),
                    "oblikIMere": image_url
                }

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

                        
            output_preview_path = os.path.join(page_specific_image_folder, f"preview_{page_num}.png")
            try:
                pil_image_obj.save(output_preview_path)
            except Exception as e:
                app.logger.error(f"[page {page_num}] Failed to save preview image: {e}")

                if pdf_plumber_instance:
                    pdf_plumber_instance.close()
    
    # if file_path_for_cleanup and os.path.exists(file_path_for_cleanup):
    #      try:
    #          os.remove(file_path_for_cleanup)
    #      except OSError as e:
    #          app.logger.error(f"Error removing uploaded file {file_path_for_cleanup}: {e}")

    return jsonify(final_payload)

@app.before_request
def before():
    app.logger.info(f"Start: {request.method} {request.path}")

@app.after_request
def after(response):
    app.logger.info(f"End: {request.method} {request.path}")
    return response

@app.route('/', methods=['GET'])
def index():
    result = { "response": "Hello World" }
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)