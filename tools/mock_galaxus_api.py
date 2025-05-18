# Placeholder for mock_galaxus_api.py
def search_product(query: str, max_results: int = 20):
    """Returns a mock list of product search results."""
    return [
        {
            "name": "MSI RTX 5060 Gaming X",
            "brand": "MSI",
            "price": 289,
            "cooling": "dual fan",
            "length_mm": 305,
            "rating": 4.7
        },
        {
            "name": "ASUS RTX 5060 OC",
            "brand": "ASUS",
            "price": 315,
            "cooling": "triple fan",
            "length_mm": 325,
            "rating": 4.8
        },
        {
            "name": "Zotac RTX 5060 Twin Edge",
            "brand": "Zotac",
            "price": 269,
            "cooling": "dual fan",
            "length_mm": 230,
            "rating": 4.5
        },
        {
            "name": "Gigabyte RTX 5060 Windforce",
            "brand": "Gigabyte",
            "price": 299,
            "cooling": "dual fan",
            "length_mm": 282,
            "rating": 4.6
        }
    ][:max_results]