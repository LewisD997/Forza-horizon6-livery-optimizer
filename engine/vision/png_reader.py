import struct
import zlib
from collections import Counter


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def inspect_png_with_stdlib(path):
    pixels, width, height = _read_png_rgb(path)
    dominant_colors = _dominant_colors(pixels)
    edge_density = _edge_density(pixels, width, height)
    return {
        "path": str(path),
        "size": {"width": width, "height": height},
        "dominant_colors": dominant_colors,
        "edge_density": edge_density,
        "high_detail_regions": [],
        "reader": "stdlib_png",
    }


def _read_png_rgb(path):
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError(f"Reference image is not a PNG and Pillow is not installed: {path}")

    offset = len(PNG_SIGNATURE)
    width = None
    height = None
    bit_depth = None
    color_type = None
    compressed = bytearray()

    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        offset += 12 + length

        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
            if bit_depth != 8 or color_type not in (2, 6) or compression != 0 or filter_method != 0 or interlace != 0:
                raise ValueError("Only non-interlaced 8-bit RGB/RGBA PNG files are supported without Pillow.")
        elif chunk_type == b"IDAT":
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    if width is None or height is None:
        raise ValueError(f"PNG header not found: {path}")

    channels = 4 if color_type == 6 else 3
    stride = width * channels
    raw = zlib.decompress(bytes(compressed))
    rows = []
    cursor = 0
    previous = [0] * stride

    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = list(raw[cursor : cursor + stride])
        cursor += stride
        row = _unfilter(row, previous, filter_type, channels)
        rows.append(row)
        previous = row

    pixels = []
    for row in rows:
        for index in range(0, len(row), channels):
            pixels.append((row[index], row[index + 1], row[index + 2]))
    return pixels, width, height


def _unfilter(row, previous, filter_type, bpp):
    result = row[:]
    for index, value in enumerate(row):
        left = result[index - bpp] if index >= bpp else 0
        up = previous[index]
        up_left = previous[index - bpp] if index >= bpp else 0

        if filter_type == 0:
            result[index] = value
        elif filter_type == 1:
            result[index] = (value + left) & 255
        elif filter_type == 2:
            result[index] = (value + up) & 255
        elif filter_type == 3:
            result[index] = (value + ((left + up) // 2)) & 255
        elif filter_type == 4:
            result[index] = (value + _paeth(left, up, up_left)) & 255
        else:
            raise ValueError(f"Unsupported PNG filter type: {filter_type}")
    return result


def _paeth(left, up, up_left):
    estimate = left + up - up_left
    distance_left = abs(estimate - left)
    distance_up = abs(estimate - up)
    distance_up_left = abs(estimate - up_left)
    if distance_left <= distance_up and distance_left <= distance_up_left:
        return left
    if distance_up <= distance_up_left:
        return up
    return up_left


def _dominant_colors(pixels, count=5):
    if not pixels:
        return []

    bucketed = Counter()
    for r, g, b in pixels:
        bucket = (r // 16 * 16, g // 16 * 16, b // 16 * 16)
        bucketed[bucket] += 1

    return [
        {"color": f"#{r:02x}{g:02x}{b:02x}", "pixels": total}
        for (r, g, b), total in bucketed.most_common(count)
    ]


def _edge_density(pixels, width, height):
    if width < 2 or height < 2:
        return 0.0

    def luminance(pixel):
        return int(pixel[0] * 0.299 + pixel[1] * 0.587 + pixel[2] * 0.114)

    active = 0
    total = 0
    for y in range(height - 1):
        for x in range(width - 1):
            current = luminance(pixels[y * width + x])
            right = luminance(pixels[y * width + x + 1])
            below = luminance(pixels[(y + 1) * width + x])
            if abs(current - right) + abs(current - below) > 48:
                active += 1
            total += 1

    return round(active / total, 4)
