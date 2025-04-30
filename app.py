import json
from flask import Flask, abort, request, jsonify, send_from_directory
import os
from flask_cors import CORS
from werkzeug.utils import secure_filename

from extractor import PDFSelectiveNumericTableExtractor  # assuming you moved the class into extractor.py
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
BASE_URL = "https://trgovir-flask.onrender.com/"

app = Flask(__name__)
CORS(app)
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
    if not filename.endswith((".png", ".jpg", ".jpeg")):
        abort(403)
    return send_from_directory('extracted_shapes', f"{timestamp}/{filename}")

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

        print(data)
        return jsonify(data)

    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/extract-preview', methods=['POST'])
def extract_preview():
    if 'file' not in request.files:
        default_pdf_path = "SPECIFIKACIJA ARMATURE ZIDOVA 2.SPRATA ISPRAVLJENO.pdf"
        pdf = pdfplumber.open(default_pdf_path)
        file = None
    else:
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
        pdf = pdfplumber.open(file)

    indicator_texts = [
        "Šipke - specifikacija", "Šipke-specifikacija",
        "šipke-Specifikacija", "šipke - Specifikacija",
        "Šipke-Specifikacija", "Šipke - Specifikacija",
        "SPECIFIKACIJA - Armaturne šipke"
    ]
    data = []
    response:dict[str, any] = {}
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        extractor = PDFSelectiveNumericTableExtractor(
                pdf=pdf,
                pdf_path=file_path,
                columns_to_extract=[2, 3, 4, 5],
                indicator_texts=indicator_texts,
                field_mapping={
                    "diameter": 2,
                    "lg": 3,
                    "n": 4,
                    "lgn": 5
                }
            )
        data = extractor.run()

    previews = []
    timestamp = int(time.time())

    position = ""
    for page_num, page in enumerate(pdf.pages):
        first_page = page
        page_text = first_page.extract_text() or ""

        if any(indicator.lower() in page_text.lower() for indicator in indicator_texts):
            page_width = first_page.width
            page_height = first_page.height

            table_settings = {
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
            }
            tables = first_page.find_tables(table_settings=table_settings)

            if not tables:
                return jsonify({'error': 'No tables found'}), 400

            table = tables[0]
            column_index = 1  # second column

            # Bounding boxes of all second column cells
            second_column_cells = [
                (cell[0], cell[1], cell[2], cell[3])
                for row in table.rows
                if column_index < len(row.cells) and (cell := row.cells[column_index])
            ]


            if not second_column_cells:
                return jsonify({'error': 'Could not determine second column bounds'}), 400

            # Calculate x_min and x_max from second column, with buffer
            x_min = min(cell[0] for cell in second_column_cells) - 1
            x_max = max(cell[2] for cell in second_column_cells) + 1

            # Get full table width
            table_x_min = min(cell[0] for row in table.rows for cell in row.cells if cell)
            table_x_max = max(cell[2] for row in table.rows for cell in row.cells if cell)

            # Helper function
            def rect_spans_table(rect, table_x_min, table_x_max, tolerance=2):
                rect_width = rect['x1'] - rect['x0']
                table_width = table_x_max - table_x_min
                return abs(rect_width - table_width) <= tolerance

            # Begin drawing
            page_image = first_page.to_image(resolution=300)
            pil_image = page_image.original
            img_width, img_height = pil_image.size
            draw = ImageDraw.Draw(pil_image)

            path = f"{EXTRACTED_SHAPES_FOLDER}/{timestamp}"
            os.makedirs(path, exist_ok=True)

            images = []
            for i_r, row in enumerate(table.rows):
                for i, cell in enumerate(row.cells):
                    if cell is None:
                        continue

                    x0, y0, x1, y1 = cell
                    sx0 = (x0 / page_width) * img_width
                    sy0 = (y0 / page_height) * img_height
                    sx1 = (x1 / page_width) * img_width
                    sy1 = (y1 / page_height) * img_height
                    is_wide = False
                    if abs((x1 - x0) - (table_x_max - table_x_min)) < 2:  # tolerance for float rounding
                        is_wide = True
                    
                    if is_wide == True and i_r != 0 and i_r:
                        position = first_page.crop((x0, y0, x1, y1)).extract_text()
                        draw.rectangle([sx0, sy0, sx1, sy1], outline="green", width=2)

                    if i != 1 or i_r == 1:
                        continue

                    cropped_image = pil_image.crop((sx0, sy0, sx1, sy1))
                    img_path = f"{path}/page_{page_num}_row_{i_r}_cell_1_{i}.png"
                    cropped_image.save(img_path)
                    images.append({'position': position, 'img_path': img_path})
                    draw.rectangle([sx0, sy0, sx1, sy1], outline="red", width=1)
                


            for i_r, img in enumerate(images):
                response.setdefault(img["position"], []).append({ 'diameter': data[i_r]['diameter'], 'lg': data[i_r]["lg"], 'n': data[i_r]['n'], 'lgn': data[i_r]['lgn'], 'oblikIMere': f"{BASE_URL}{img['img_path']}" })
            # Draw lines - PINK
            # for line in first_page.lines:
            #     if line['x0'] >= x_min and line['x1'] <= x_max:
            #         x0 = (line['x0'] / page_width) * img_width
            #         y0 = (1 - line['y1'] / page_height) * img_height
            #         x1 = (line['x1'] / page_width) * img_width
            #         y1 = (1 - line['y0'] / page_height) * img_height
            #         draw.line([x0, y0, x1, y1], fill="pink", width=1)

            # print(first_page.rect_edges)
            # print("----------------------------------------------------------------------------------------------------------------")
            # print(jsonify(first_page.lines))
            # print("----------------------------------------------------------------------------------------------------------------")
            # # print(first_page.chars)
            # with open('page_chars.txt', 'w', encoding='utf-8') as f:
            #     json.dump(first_page.lines, f, indent=2, ensure_ascii=False)

            # Draw full-width rects - PURPLE
            # for rect in first_page.rects:
            #     if rect_spans_table(rect, table_x_min, table_x_max):
            #         x0 = (rect['x0'] / page_width) * img_width
            #         y0 = (1 - rect['y1'] / page_height) * img_height
            #         x1 = (rect['x1'] / page_width) * img_width
            #         y1 = (1 - rect['y0'] / page_height) * img_height
            #         left = min(x0, x1)
            #         right = max(x0, x1)
            #         top = min(y0, y1)
            #         bottom = max(y0, y1)
            #         draw.rectangle([left, top, right, bottom], outline="purple", width=3)

            # Draw rects - RED
            # for rect in first_page.rects:
            #     # if rect['x0'] >= x_min and rect['x1'] <= x_max:
            #     x0 = (rect['x0'] / page_width) * img_width
            #     y0 = (1 - rect['y1'] / page_height) * img_height
            #     x1 = (rect['x1'] / page_width) * img_width
            #     y1 = (1 - rect['y0'] / page_height) * img_height
            #     left = min(x0, x1)
            #     right = max(x0, x1)
            #     top = min(y0, y1)
            #     bottom = max(y0, y1)
            #     draw.rectangle([left, top, right, bottom], outline="red", width=5)

            # --- Group vertical objects first ---
            # vertical_groups = []
            # visited = set()

            # chars = [obj for obj in first_page.objects['char'] if obj['x0'] >= x_min and obj['x1'] <= x_max]

            # for i, obj in enumerate(chars):
            #     if i in visited:
            #         continue
            #     group = [obj]
            #     visited.add(i)
            #     for j, other in enumerate(chars):
            #         if j in visited:
            #             continue
            #         # Same column (x0/x1 aligned), and very close vertically
            #         if abs(obj['x0'] - other['x0']) < MAGIC_NUMBER and abs(obj['x1'] - other['x1']) < MAGIC_NUMBER and abs(obj['y1'] - other['y0']) < MAGIC_NUMBER and obj['upright'] == other['upright']:
            #             group.append(other)
            #             visited.add(j)
            #     if len(group) > 1:
            #         vertical_groups.append(group)

            # # Mark used objects
            # vertical_used_ids = set(id(char) for group in vertical_groups for char in group)

            # # --- Then group horizontal objects (words) ---
            # horizontal_groups = []
            # current_group = []

            # # Sort remaining chars top-down, left-right
            # remaining_chars = sorted(
            #     [c for c in chars if id(c) not in vertical_used_ids],
            #     key=lambda c: (round(c['top'], 1), c['x0'])
            # )

            # for char in remaining_chars:
            #     if not current_group:
            #         current_group.append(char)
            #         continue

            #     last_char = current_group[-1]
            #     same_line = abs(char['y0'] - last_char['y0']) < MAGIC_NUMBER and abs(char['y1'] - last_char['y1']) < MAGIC_NUMBER
            #     close_enough = abs(char['x0'] - last_char['x1']) < MAGIC_NUMBER

            #     if same_line and close_enough:
            #         current_group.append(char)
            #     else:
            #         horizontal_groups.append(current_group)
            #         current_group = [char]

            # if current_group:
            #     horizontal_groups.append(current_group)

            # # --- Draw all grouped boxes ---
            # for group in vertical_groups + horizontal_groups:
            #     x0 = (min(c['x0'] for c in group) / page_width) * img_width
            #     y0 = (1 - max(c['y1'] for c in group) / page_height) * img_height
            #     x1 = (max(c['x1'] for c in group) / page_width) * img_width
            #     y1 = (1 - min(c['y0'] for c in group) / page_height) * img_height
            #     draw.rectangle([x0, y0, x1, y1], outline="blue", width=1)

            # Draw curves - GREEN
            # for curve in first_page.curves:
            #     if 'x0' in curve and 'x1' in curve and curve['x0'] >= x_min and curve['x1'] <= x_max:
            #         x0 = (curve['x0'] / page_width) * img_width
            #         y0 = (1 - curve['y1'] / page_height) * img_height
            #         x1 = (curve['x1'] / page_width) * img_width
            #         y1 = (1 - curve['y0'] / page_height) * img_height
            #         left = min(x0, x1)
            #         right = max(x0, x1)
            #         top = min(y0, y1)
            #         bottom = max(y0, y1)
            #         draw.rectangle([left, top, right, bottom], outline="green", width=2)

            # Save image
            output_path = os.path.join(path, f"preview_{page_num}.png")
            pil_image.save(output_path)

            # Also prepare base64 to preview in frontend if needed
            img_byte_arr = io.BytesIO()
            pil_image.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            img_base64 = base64.b64encode(img_byte_arr.read()).decode('utf-8')

            previews.append({
                "page_index": 0,
                "image": img_base64
            })

        # # Optional: Cleanup uploaded file after extraction
        # os.remove(file_path)
        pdf.close()
    return jsonify(response)

@app.route('/', methods=['GET'])
def index():
    result = {
        "response": "Hello World"
    }

    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)