import json
import sys
import os
print("CURRENT WORKING DIRECTORY:", os.getcwd())
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app as flask_app
import pytest
import pathlib

@pytest.fixture(params=["test_1", "test_2", "test_3", "test_4", "test_5"])  # Add more as needed
def test_env(request, tmp_path):
    fixture_name = request.param

    BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
    test_fixture = BASE_DIR / "tests" / "fixtures" / fixture_name

    output_folder = tmp_path / "test_output"
    output_folder.mkdir()

    
    meta_path = test_fixture / "meta.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta_info = json.load(f)
    else:
        meta_info = {}

    flask_app.config['TESTING'] = True
    flask_app.config['EXTRACTED_SHAPES_FOLDER'] = str(output_folder)
    flask_app.config["DRAW_DEBUG_SHAPES"] = True

    pdf_path = test_fixture / "test_file.pdf"
    with open(pdf_path, "rb") as f:
        file_data = f.read()

    yield {
        "client": flask_app.test_client(),
        "pdf_bytes": file_data,
        "expected_json_path": os.path.join(test_fixture, "expected_result.json"),
        "expected_image_folder": os.path.join(test_fixture, "extracted_shapes"),
        "actual_image_folder": os.path.join(output_folder, "test_timestamp"),
        "meta": meta_info
    }
