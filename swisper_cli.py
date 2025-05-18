import json
from engine.contract_engine import ContractEngine  # adjust path as needed

def main():
    print("👋 Welcome to Swisper – Your Smart Shopping Assistant!\n")

    product = input("🔍 What product are you looking for? ")
    price_limit = input("💰 What's your maximum budget (optional)? ")
    delivery_by = input("📦 Do you need it by a certain date (optional)? ")

    print("\n🎯 Enter your preferences (e.g., 'low noise', 'high performance').")
    print("   Separate multiple with commas or press Enter to skip.")
    preferences = input("   Preferences: ")
    preferences_list = [p.strip() for p in preferences.split(",") if p.strip()]

    print("\n🔧 Any technical constraints (e.g. compatibility)?")
    constraints = {}
    constraint_input = input("   E.g., enter compatibility (or press Enter): ")
    if constraint_input:
        constraints["motherboard compatibility"] = constraint_input

    contract_template_path = "contract_templates/purchase_item.yaml"
    schema_path = "schemas/purchase_item.schema.json"
    engine = ContractEngine(contract_template_path, schema_path)

    engine.contract["parameters"]["product"] = product
    engine.contract["parameters"]["preferences"] = preferences_list
    engine.contract["parameters"]["must_match_model"] = True
    if price_limit:
        engine.contract["parameters"]["price_limit"] = int(price_limit)
    if delivery_by:
        engine.contract["parameters"]["delivery_by"] = delivery_by
    if constraints:
        engine.contract["parameters"]["constraints"] = constraints

    print("\n🚀 Executing purchase contract...\n")
    engine.run()

    print("\n✅ Final Output Summary:")
    print(json.dumps(engine.contract, indent=2))
    engine.save_final_contract("final_contract.json")
    print("📝 Final contract saved to final_contract.json")

if __name__ == "__main__":
    main()