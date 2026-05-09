import io
from PIL import Image
import zxingcpp


def decode_barcode(image_bytes: bytes) -> str | None:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        results = zxingcpp.read_barcodes(img)
        return results[0].text if results else None
    except Exception:
        return None
