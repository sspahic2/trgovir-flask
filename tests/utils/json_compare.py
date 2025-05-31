import json
import os
from pprint import pprint

def normalize_oblik_path(row):
    if "oblikIMere" in row and row["oblikIMere"]:
        row["oblikIMere"] = os.path.basename(row["oblikIMere"])
    return row

def normalize_structure(data):
    for group in data:
        for row in group["rows"]:
            normalize_oblik_path(row)
    return data

def json_structures_equal(actual, expected_path):
    with open(expected_path, "r", encoding="utf-8") as f:
        expected = json.load(f)

    normalized_actual = normalize_structure(json.loads(json.dumps(actual)))  # deepcopy
    normalized_expected = normalize_structure(expected)

    if normalized_actual != normalized_expected:
        print("❌ Mismatch Detected!")
        print("EXPECTED:")
        pprint(normalized_expected, width=140)
        print("ACTUAL:")
        pprint(normalized_actual, width=140)

    return normalized_actual == normalized_expected
