from PIL import Image, ImageChops
import numpy as np

def images_are_equal(path1, path2, tolerance=5):
    try:
        img1 = Image.open(path1).convert("RGB")
        img2 = Image.open(path2).convert("RGB")

        if img1.size != img2.size:
            print(f"❌ Size mismatch: {img1.size} vs {img2.size}")
            return False

        diff = ImageChops.difference(img1, img2)
        diff_stat = np.max(np.array(diff))

        if diff_stat > tolerance:
            print(f"❌ Pixel diff too large: {diff_stat}")
            return False

        return True
    except Exception as e:
        print(f"❌ Image comparison failed for {path1} vs {path2}: {e}")
        return False

