import json
from flask import Flask, abort, request, jsonify, send_from_directory
import os
from flask_cors import CORS
from werkzeug.utils import secure_filename, safe_join

from extractor import PDFSelectiveNumericTableExtractor
import io
import base64
import pdfplumber
import time
from PIL import Image, ImageDraw

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

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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
            columns_to_extract=[2, 3, 4, 5],
            indicator_texts=[
                "Šiple - specifikacija", "Šipke-specifikacija",
                "šipke-Specifikacija", "šipke - Specifikacija",
                "Šipke-Specifikacija", "Šipke - Specifikacija",
                "SPECIFIKACIJA - Armaturne šipke"
            ],
            field_mapping={
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
    field_mapping = { "diameter": 2, "lg": 3, "n": 4, "lgn": 5 }
    columns_to_extract = [2, 3, 4, 5]

    pdf_plumber_instance = None
    file_path_for_cleanup = None
    
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
        
        filename = secure_filename(uploaded_file.filename)
        saved_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        try:
            uploaded_file.save(saved_file_path)
            pdf_plumber_instance = pdfplumber.open(saved_file_path)
            file_path_for_cleanup = saved_file_path
        except Exception as e:
            app.logger.error(f"Error processing uploaded file {filename}: {e}")
            if os.path.exists(saved_file_path): # Attempt cleanup even if open failed after save
                 try:
                    os.remove(saved_file_path)
                 except OSError as remove_e:
                    app.logger.error(f"Error removing partially uploaded file {saved_file_path}: {remove_e}")
            return jsonify({'error': 'Could not process uploaded file'}), 500

    if not pdf_plumber_instance:
         return jsonify({'error': 'PDF object could not be initialized'}), 500

    extractor = PDFSelectiveNumericTableExtractor(
        pdf=pdf_plumber_instance,
        pdf_path=file_path_for_cleanup if file_path_for_cleanup else "default.pdf", # Path for context if needed by extractor
        columns_to_extract=columns_to_extract,
        indicator_texts=indicator_texts,
        field_mapping=field_mapping
    )
    extracted_data = extractor.run()
    
    timestamp = int(time.time())
    global_data_index = 0
    response_payload = {}
    current_page_position_text = "Pozicija_1" 

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

            page_pil_image = page_obj.to_image(resolution=300)
            pil_image_obj = page_pil_image.original
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

            for row_index, row_obj in enumerate(current_table.rows):
                for cell_index, cell_coords_pdf in enumerate(row_obj.cells):
                    if cell_coords_pdf is None:
                        continue

                    x0_pdf, y0_pdf, x1_pdf, y1_pdf = cell_coords_pdf
                    inset = 3  # or 5 pixels if needed

                    scaled_x0 = ((x0_pdf / page_width_pdf) * img_width_pixels) + inset
                    scaled_y0 = ((y0_pdf / page_height_pdf) * img_height_pixels) + inset
                    scaled_x1 = ((x1_pdf / page_width_pdf) * img_width_pixels) - inset
                    scaled_y1 = ((y1_pdf / page_height_pdf) * img_height_pixels) - inset

                    
                    cell_width_pdf = x1_pdf - x0_pdf
                    is_wide_cell = abs(cell_width_pdf - (table_x_max_pdf - table_x_min_pdf)) < 2
                    
                    if is_wide_cell and row_index > 0: 
                        extracted_text_from_cell = page_obj.crop(cell_coords_pdf).extract_text()
                        if extracted_text_from_cell:
                            current_page_position_text = extracted_text_from_cell.strip()
                        image_draw_context.rectangle([scaled_x0, scaled_y0, scaled_x1, scaled_y1], outline="green", width=2)

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

                        content_objects = [
                            obj for obj in (word_objects + visual_objects)
                            if obj["x0"] >= scaled_x0 and obj["x1"] <= scaled_x1
                            and obj["y0"] >= scaled_y0 and obj["y1"] <= scaled_y1
                        ]

                        if content_objects:
                            obj_x0 = min(obj["x0"] for obj in content_objects)
                            obj_y0 = min(obj["y0"] for obj in content_objects)
                            obj_x1 = max(obj["x1"] for obj in content_objects)
                            obj_y1 = max(obj["y1"] for obj in content_objects)

                            pad = 10
                            scaled_cx0 = max(0, obj_x0 - pad)
                            scaled_cy0 = max(0, obj_y0 - pad)
                            scaled_cx1 = min(img_width_pixels, obj_x1 + pad)
                            scaled_cy1 = min(img_height_pixels, obj_y1 + pad)

                            cropped_shape_image = pil_image_obj.crop((scaled_cx0, scaled_cy0, scaled_cx1, scaled_cy1))
                        else:
                            # fallback to full cell bounding box
                            cropped_shape_image = pil_image_obj.crop((scaled_x0, scaled_y0, scaled_x1, scaled_y1))

                        img_filename = f"page_{page_num}_row_{row_index}_cell_1.png"
                        img_full_save_path = os.path.join(page_specific_image_folder, img_filename)
                        cropped_shape_image.save(img_full_save_path)

                        img_path_segment_for_url = os.path.join(str(timestamp), img_filename).replace("\\", "/")
                        images_collected_for_page.append({
                            'position': current_page_position_text,
                            'img_path_segment': img_path_segment_for_url
                        })

                        image_draw_context.rectangle([scaled_x0, scaled_y0, scaled_x1, scaled_y1], outline="red", width=1)
            
            for img_details in images_collected_for_page:
                if global_data_index < len(extracted_data):
                    current_data_item = extracted_data[global_data_index]
                    image_url = f"extracted_shapes/{img_details['img_path_segment']}"
                    
                    response_payload.setdefault(img_details["position"], []).append({
                        "diameter": current_data_item.get('diameter'),
                        "lg": current_data_item.get('lg'),
                        "n": current_data_item.get('n'),
                        "lgn": current_data_item.get('lgn'),
                        "oblikIMere": image_url
                    })
                    global_data_index += 1
                else:
                    app.logger.warning(f"Data list exhausted. global_data_index: {global_data_index}, len(data): {len(extracted_data)}")
                    break
            
            output_preview_path = os.path.join(page_specific_image_folder, f"preview_{page_num}.png")
            pil_image_obj.save(output_preview_path)

    if pdf_plumber_instance:
        pdf_plumber_instance.close()
    
    if file_path_for_cleanup and os.path.exists(file_path_for_cleanup):
         try:
             os.remove(file_path_for_cleanup)
         except OSError as e:
             app.logger.error(f"Error removing uploaded file {file_path_for_cleanup}: {e}")
             
    return jsonify(response_payload)

@app.route('/', methods=['GET'])
def index():
    result = { "response": "Hello World" }
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)