def purchase_intent_prompt(user_input):
    return f"""
You are an assistant helping users complete shopping tasks.

Analyze the following message and extract the following fields:
- product
- price_limit (number, if mentioned)
- delivery_by (ISO date format, if mentioned)
- preferences (list of strings)
- must_match_model (true if a specific model is mentioned)
- constraints (dictionary, e.g. motherboard compatibility)

Output your answer strictly in this JSON format:

{{
  "product": ...,
  "price_limit": ...,
  "delivery_by": ...,
  "preferences": [...],
  "must_match_model": true,
  "constraints": {{
    "motherboard compatibility": ...
  }}
}}

User message: \"{user_input}\"
"""