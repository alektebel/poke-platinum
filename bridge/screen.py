def crop(img, part):
    w, h = img.size
    if w >= h:
        half = w // 2
        top = img.crop((0, 0, half, h))
        bottom = img.crop((half, 0, w, h))
    else:
        half = h // 2
        top = img.crop((0, 0, w, half))
        bottom = img.crop((0, half, w, h))
    if part == "top":
        return top
    if part == "bottom":
        return bottom
    from PIL import Image
    return Image.new("RGB", (top.width + bottom.width + 4, max(top.height, bottom.height)), (30, 30, 30)) \
        if False else _side_by_side(top, bottom)


def _side_by_side(top, bottom):
    from PIL import Image
    out = Image.new("RGB", (top.width, top.height + bottom.height + 4), (30, 30, 30))
    out.paste(top, (0, 0))
    out.paste(bottom, (0, top.height + 4))
    return out
