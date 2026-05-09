"""Open Food Facts client."""

import requests

API_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
HEADERS = {"User-Agent": "PCOSScanner/0.1 (utsapoddar@gmail.com)"}
NUTRIMENT_KEYS = (
    "proteins_100g",
    "fiber_100g",
    "sugars_100g",
    "added-sugars_100g",
    "saturated-fat_100g",
    "sodium_100g",
    "energy-kcal_100g",
)


def fetch_product(barcode: str) -> dict | None:
    try:
        response = requests.get(API_URL.format(barcode=barcode), headers=HEADERS, timeout=5)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return None
    product = data.get("product") or {}
    if data.get("status") != 1 or not product:
        return None

    nutriments = product.get("nutriments") or {}
    return {
        "barcode": str(product.get("code") or barcode),
        "name": product.get("product_name") or None,
        "brands": product.get("brands") or None,
        "nova_group": product.get("nova_group"),
        "serving_size": product.get("serving_size") or None,
        "nutriments_100g": {key: nutriments.get(key) for key in NUTRIMENT_KEYS},
    }
