from utils.images_are_equal import images_are_equal
from utils.json_compare import json_structures_equal
import io
import os

def test_extract_preview(test_env):
    client = test_env["client"]
    pdf_bytes = test_env["pdf_bytes"]

    response = client.post("/extract-preview", data={
        "file": (io.BytesIO(pdf_bytes), "test_file.pdf")
    }, content_type='multipart/form-data')

    assert response.status_code == 200

    assert json_structures_equal(response.json, test_env["expected_json_path"])

    print(f"📄 Testing original file: {test_env['meta'].get('original_filename', 'unknown')}")
    # ✅ Validate each image by filename
    for group in response.json:
      for row in group["rows"]:
        filename = os.path.basename(row["oblikIMere"])
        expected_path = os.path.join(test_env["expected_image_folder"], filename)
        actual_path = os.path.join(test_env["actual_image_folder"], filename)

        print(f"Comparing expected: {expected_path}")
        print(f"      to actual:   {actual_path}")

        assert os.path.exists(expected_path), f"Missing expected image: {expected_path}"
        assert os.path.exists(actual_path), f"Missing actual image: {actual_path}"
        assert images_are_equal(actual_path, expected_path), f"Image mismatch: {filename}"
