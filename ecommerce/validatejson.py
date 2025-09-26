import json

with open('category.json', 'r', encoding='utf-8') as f:
    try:
        json.load(f)
        print("JSON is valid")
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")