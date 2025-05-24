import os
import json
import re
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()

# Retrieve API key and project ID from environment
api_key = os.getenv("OPENAI_API_KEY")
project_id = os.getenv("OPENAI_PROJECT_ID")

# Debug: Show if key and project are set
print("🔑 Detected API Key:", "SET" if api_key else "NOT SET")
print("🧭 Project ID:", project_id if project_id else "NOT SET")

# Initialize OpenAI client
client = OpenAI(
    api_key=api_key,
    project=project_id
)

def analyze_product_differences(product_list: list) -> str:
    prompt = (
        "Analyze the following product search results and summarize key differences in terms "
        "of price, brand, cooling system, size, and performance characteristics. "
        "Return a concise summary that could help a user decide what to prioritize.\n\n"
        f"{json.dumps(product_list, indent=2)}"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content

def analyze_user_preferences(user_input: str, product_search_results: list) -> dict:
    prompt = (
        "You are an assistant that extracts structured product preferences and compatibility constraints "
        "from user input.\n\n"
        "User said:\n"
        f"{user_input}\n\n"
        "Here is a representative sample of available products:\n"
        f"{json.dumps(product_search_results, indent=2)}\n\n"
        "Please return a JSON object with two keys:\n"
        "- preferences: A list of inferred user preferences (e.g. 'low noise', 'energy efficiency')\n"
        "- constraints: A dictionary of technical constraints (e.g. motherboard compatibility, width, voltage)\n"
        "Return only valid JSON. Do not include markdown or explanations. Do not wrap the JSON in triple backticks."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )

        raw_output = response.choices[0].message.content.strip()
        print("📎 Raw output:\n", raw_output)

        # 🔧 Strip markdown code block formatting if present
        if raw_output.startswith("```"):
            raw_output = re.sub(r"^```(?:json)?\s*", "", raw_output)
            raw_output = re.sub(r"\s*```$", "", raw_output)

        return json.loads(raw_output)

    except Exception as e:
        print("❌ Failed to parse LLM response:", str(e))
        return {"preferences": [], "constraints": {}}

def check_product_compatibility(product_list: list, user_constraints: dict, product_type: str = None) -> list:
    constraint_text = json.dumps(user_constraints)

    prompt = (
        "You are a compatibility expert assistant.\n\n"
        f"The user is searching for a {product_type or 'product'} with this constraint:\n"
        f"{constraint_text}\n\n"
        "Here is a list of products with their attributes:\n"
        f"{json.dumps(product_list, indent=2)}\n\n"
        "Your task:\n"
        "1. Analyze which product attributes matter for compatibility.\n"
        "2. Search the web and see whether you find additional attributes for the products that would determine compatiblity.For example a graphics card would have a pCI slot and a length"
        "3. For each product, return whether it is 'compatible': true or false.\n\n"
        "Return a JSON list where each item includes the product name and compatibility flag."
        "Return only valid JSON. Do not include markdown or explanations. Do not wrap the JSON in triple backticks."    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )

        raw_output = response.choices[0].message.content.strip()
        print("📎 Compatibility Output:\n", raw_output)

        if raw_output.startswith("```"):
            raw_output = re.sub(r"^```(?:json)?\s*", "", raw_output)
            raw_output = re.sub(r"\s*```$", "", raw_output)

        return json.loads(raw_output)

    except Exception as e:
        print("❌ Compatibility check failed:", str(e))
        return []

def filter_products_with_llm(product_list: list, preferences: list) -> list:
    prompt = (
        "You are an intelligent shopping assistant.\n"
        f"The user has the following preferences:\n{json.dumps(preferences)}\n\n"
        f"Here are the products to evaluate:\n{json.dumps(product_list, indent=2)}\n\n"
        "Please filter the products based on how well they align with the user's preferences. "
        "Return a JSON list of the best-matching products (including all their attributes)."
        "Return only valid JSON. Do not include markdown or explanations. Do not wrap the JSON in triple backticks."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )

        raw_output = response.choices[0].message.content.strip()
        print("📎 Filter Output:\n", raw_output)

        if raw_output.startswith("```"):
            raw_output = re.sub(r"^```(?:json)?\s*", "", raw_output)
            raw_output = re.sub(r"\s*```$", "", raw_output)

        return json.loads(raw_output)

    except Exception as e:
        print("❌ Failed to filter products:", str(e))
        return []
