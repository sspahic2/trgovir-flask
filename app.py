from flask import Flask, request, jsonify
import os
from flask_cors import CORS
from werkzeug.utils import secure_filename

from extractor import PDFSelectiveNumericTableExtractor  # assuming you moved the class into extractor.py

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}

app = Flask(__name__)
CORS(app)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

        # Optional: Cleanup uploaded file after extraction
        os.remove(file_path)

        print(data)
        return jsonify(data)

    return jsonify({'error': 'Invalid file type'}), 400

if __name__ == '__main__':
    app.run(debug=True)

@app.route('/', methods=['GET'])
def index():
    result = {
        "response": "Hello World"
    }

    return jsonify(result)