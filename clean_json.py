import re

# Вкажіть правильний шлях до вашого файлу
file_path = "app/config/rabotaua_filters_map.json"

try:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Видаляємо всі разом із пробілами перед ними
    cleaned_content = re.sub(r'\s*\]+\]', '', content)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(cleaned_content)
        
    print("✅ Файл успішно очищено від артефактів!")
except FileNotFoundError:
    print(f"❌ Файл не знайдено за шляхом: {file_path}")