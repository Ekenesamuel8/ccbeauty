with open('category.json', 'rb') as f:
    content = f.read().decode('utf-16')  # Adjust based on detected encoding
with open('category.json', 'w', encoding='utf-8') as f:
    f.write(content)