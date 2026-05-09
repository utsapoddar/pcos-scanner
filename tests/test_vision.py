from core.vision import extract_product_from_label


def test_extract_product_from_label_invalid_image_returns_none():
    assert extract_product_from_label(b"not an image") is None
