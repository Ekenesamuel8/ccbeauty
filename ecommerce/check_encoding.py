import chardet
with open('category.json', 'rb') as f:
    result = chardet.detect(f.read())
    print(result)