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

from helpers.extract.routes.extract_preview_handler import run_extract_preview  # ✅ NEW IMPORT

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
app.config["DRAW_DEBUG_SHAPES"] = False

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
    if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
        abort(403)

    directory = safe_join(app.root_path, EXTRACTED_SHAPES_FOLDER, timestamp)
    full_path = os.path.join(directory, filename)

    app.logger.debug(f"Looking for shape file at: {full_path}")

    if not os.path.isfile(full_path):
        app.logger.error(f"Shape file not found: {full_path}")
        abort(404)

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
    result = run_extract_preview(request)  # ✅ ONLY THIS LINE IS NEW
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    return jsonify(result)

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
