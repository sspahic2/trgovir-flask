def scale_visual_bbox(obj, x_scale, y_scale, img_height):
    x0 = obj["x0"] * x_scale
    x1 = obj["x1"] * x_scale
    y0 = img_height - (obj["y1"] * y_scale)
    y1 = img_height - (obj["y0"] * y_scale)
    return {
        "x0": min(x0, x1),
        "x1": max(x0, x1),
        "y0": min(y0, y1),
        "y1": max(y0, y1)
    }

def scale_word_bbox(word, width_pdf, height_pdf, width_img, height_img):
    x0 = (word["x0"] / width_pdf) * width_img
    x1 = (word["x1"] / width_pdf) * width_img
    y0 = (word["top"] / height_pdf) * height_img
    y1 = (word["bottom"] / height_pdf) * height_img
    return {
        "x0": x0,
        "x1": x1,
        "y0": y0,
        "y1": y1
    }