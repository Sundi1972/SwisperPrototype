
import os
import json
from engine.contract_engine import ContractEngine

# Simulated intent data
intent_data = {
    "product": "RTX 4060",
    "price_limit": 300,
    "delivery_by": "2024-09-11",
    "preference": "best_rating",
    "preferences": ["low noise", "high performance", "power efficiency"],
    "constraints": {
        "motherboard compatibility": "MSI MAG B850 Tomahawk Max WIFI"
    },
    "must_match_model": True
}

# Load contract template and schema
engine = ContractEngine(template_path="contract_templates/purchase_item.yaml", schema_path="schemas/purchase_item.schema.json")

# Run the engine
engine.fill_parameters(intent_data)

print("\n✅ Filled Contract:")
engine.print_contract()

engine.run()

# Save final contract
engine.save_final_contract("final_contract.json")
