from hardware.scale_service import get_weight_grams

try:
    weight = get_weight_grams()
    print(f"Weight: {weight} g")
except Exception as e:
    print("Error:", e)
