
import os
import re
import requests

def extract_numeric_price(price_str):
    if isinstance(price_str, (int, float)):
        return float(price_str)
    if not isinstance(price_str, str):
        return None
    match = re.search(r"[\d,.]+", price_str.replace("’", "").replace(",", ""))
    if match:
        try:
            return float(match.group().replace(",", ""))
        except ValueError:
            return None
    return None

def search_google_shopping(query, location='Switzerland', gl='ch', hl='en'):
    api_key = os.getenv('SEARCHAPI_KEY')
    if not api_key:
        raise ValueError("SEARCHAPI_KEY not set in environment variables.")

    url = "https://www.searchapi.io/api/v1/search"
    params = {
        "engine": "google_shopping",
        "q": query,
        "location": location,
        "gl": gl,
        "hl": hl,
        "api_key": api_key
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print("❌ API request failed:", str(e))
        return []

    shopping_results = data.get("shopping_results", [])
    products = []
    for item in shopping_results:
        raw_price = item.get("price") or item.get("extracted_price")
        product = {
            "name": item.get("title", "Unknown"),
            "brand": item.get("brand", "Unknown"),
            "price": extract_numeric_price(raw_price),
            "rating": item.get("rating"),
            "reviews": item.get("reviews"),
            "link": item.get("link"),
            "thumbnail": item.get("thumbnail")
        }
        products.append(product)

    return products
