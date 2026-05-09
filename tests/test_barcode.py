import pytest

from core.barcode import decode_barcode


def test_decode_barcode_returns_none_for_invalid_bytes():
    assert decode_barcode(b"") is None
    assert decode_barcode(b"not an image") is None
    assert decode_barcode(b"\x00\xff\x10random") is None


@pytest.mark.skip(reason="Positive-path image generation would require optional python-barcode.")
def test_decode_barcode_reads_generated_barcode():
    pass
