import re
from urllib.parse import urlparse, urlunparse, parse_qsl, unquote
from typing import Dict, Any, List, Union, Tuple

class UrlBuilder:
    """
    Утилита для построения и нормализации URL Work.ua.
    Обеспечивает каноничность слагов (транслитерация, lowercase) и 
    специфическое кодирование параметров фильтрации (через '+').
    """

    BASE_URL = "https://www.work.ua"
    
    # Маппинг популярных городов (можно расширять)
    CITY_SLUGS = {
        "киев": "kyiv", "київ": "kyiv", "kyiv": "kyiv", "kiev": "kyiv",
        "харьков": "kharkiv", "харків": "kharkiv", "kharkiv": "kharkiv",
        "одесса": "odesa", "одеса": "odesa", "odesa": "odesa", "odessa": "odesa",
        "днепр": "dnipro", "дніпро": "dnipro", "dnipro": "dnipro",
        "львов": "lviv", "львів": "lviv", "lviv": "lviv",
        "запорожье": "zaporizhzhia", "запоріжжя": "zaporizhzhia",
        "вся украина": "", "украина": "", "ukraine": ""
    }

    # Таблица транслитерации для формирования slug из кириллицы
    TRANS_MAP = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'h', 'ґ': 'g', 'д': 'd', 'е': 'e', 
        'є': 'ie', 'ж': 'zh', 'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'yi', 'й': 'i', 
        'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 
        'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 
        'ш': 'sh', 'щ': 'shch', 'ь': '', 'ю': 'iu', 'я': 'ia',
        'ы': 'y', 'э': 'e', 'ё': 'e', 'ъ': ''
    }

    @classmethod
    def build(cls, query: str, city: str = "", params: Dict[str, Any] = None) -> str:
        """
        Строит канонический URL с поддержкой параметров фильтрации.
        
        Args:
            query: Поисковый запрос (например, "Python Developer").
            city: Город (например, "Киев").
            params: Словарь фильтров. Поддерживает списки и кортежи для language_level.
                    Пример: {'category': [1, 17], 'language_level': [(1, 5), (2, 4)]}
        """
        if not query:
            raise ValueError("Query cannot be empty")

        # 1. Формирование Path (Slug)
        city_slug = cls._get_city_slug(city)
        query_slug = cls._slugify(query)
        
        parts = ["resumes"]
        if city_slug:
            parts.append(city_slug)
        parts.append(query_slug)
        
        path = "/".join(["", "-".join(parts), ""]) # /resumes-city-query/

        # 2. Формирование Query String (специфическое кодирование Work.ua)
        query_string = ""
        if params:
            query_string = cls._encode_params(params)

        # 3. Сборка
        url = f"{cls.BASE_URL}{path}"
        if query_string:
            url += f"?{query_string}"
            
        return url

    @classmethod
    def normalize(cls, url: str) -> str:
        """
        Приводит URL к каноническому виду:
        - Удаляет UTM-метки.
        - Сортирует параметры по ключу и значения внутри списков.
        - Приводит домен и схему.
        """
        if not url: return ""
        if not url.startswith("http"): url = "https://" + url.lstrip("/")

        parsed = urlparse(url)
        path = parsed.path
        if not path.endswith("/"): path += "/"
        # Детальная страница резюме всегда канонизируется без query-параметров
        if re.search(r"^/resumes/[a-zA-Z0-9]+/?$", path):
            return urlunparse(("https", "www.work.ua", path, "", "", ""))


        # Обработка Query Params
        query_str = ""
        if parsed.query:
            # Парсим параметры. Work.ua использует '+' как разделитель внутри значений,
            # но стандартный parse_qsl может это не разобрать корректно, если не декодировать.
            # Для надежности разбиваем вручную, фильтруем и собираем обратно.
            
            # 1. Получаем сырые пары key=value
            pairs = parsed.query.split('&')
            clean_params = {}
            
            for pair in pairs:
                if not pair: continue
                if '=' not in pair: continue
                key, val = pair.split('=', 1)
                
                # Удаляем трекинг
                if key.lower().startswith("utm_") or key in ["gclid", "fbclid"]:
                    continue
                
                # Декодируем значение (там могут быть +)
                # Work.ua: category=1+2. unquote заменит + на пробел, если это standard urlencoding,
                # но здесь + это разделитель.
                # Считаем, что на входе + разделяет значения.
                
                values = [v for v in val.split('+') if v != ""]
                values = cls._sort_tokens(values)
                clean_params.setdefault(key, [])
                clean_params[key].extend(values)


            # 2. Собираем обратно с сортировкой ключей
            if clean_params:
                sorted_keys = sorted(clean_params.keys())
                encoded_parts = []
                for k in sorted_keys:
                    # Собираем значения через +
                    val_str = "+".join(clean_params[k])
                    encoded_parts.append(f"{k}={val_str}")
                query_str = "&".join(encoded_parts)

        return urlunparse(("https", "www.work.ua", path, "", query_str, ""))

    @classmethod
    def _slugify(cls, text: str) -> str:
        """
        Транслитерирует кириллицу, переводит в lower, оставляет безопасные символы.
        """
        text = text.lower().strip()
        
        # Транслитерация
        res = []
        for char in text:
            res.append(cls.TRANS_MAP.get(char, char))
        text = "".join(res)
        
        # Очистка (оставляем a-z, 0-9, ., +, -)
        # Заменяем пробелы на +
        text = re.sub(r"\s+", "+", text)
        # Удаляем всё кроме разрешенных
        text = re.sub(r"[^a-z0-9\.\+\-]", "", text)
        # Убираем дубли плюсов
        text = re.sub(r"\++", "+", text)
        
        return text.strip("+")

    @classmethod
    def _get_city_slug(cls, city: str) -> str:
        if not city:
            return ""
        key = city.lower().strip()

        # 1) Из известного справочника
        if key in cls.CITY_SLUGS:
            return cls.CITY_SLUGS[key]

        # 2) Fallback: город в path должен быть одним токеном без '+'
        slug = cls._slugify(key)
        slug = slug.replace("+", "-")
        slug = re.sub(r"-{2,}", "-", slug).strip("-")
        return slug

    @classmethod
    def _sort_tokens(cls, tokens: List[str]) -> List[str]:
        """
        Стабильная сортировка:
        - если все токены цифры -> сортируем численно
        - иначе -> лексикографически
        """
        if not tokens:
            return tokens
        if all(t.isdigit() for t in tokens):
            return sorted(tokens, key=lambda x: int(x))
        return sorted(tokens)


    @classmethod
    def _encode_params(cls, params: Dict[str, Any]) -> str:
        """
        Кодирует параметры в формат Work.ua:
        - Списки: key=val1+val2
        - Tuple (lang, level): key=lang-level+lang-level
        """
        parts = []
        # Сортировка ключей для стабильности URL
        for key in sorted(params.keys()):
            val = params[key]
            if val is None: continue
            
            val_str = ""
            if isinstance(val, list):
                # Обработка списка
                str_vals = []
                for item in val:
                    if isinstance(item, tuple) or isinstance(item, list):
                        # Составное значение (например, язык-уровень)
                        # (1, 5) -> "1-5"
                        str_vals.append(f"{item[0]}-{item[1]}")
                    else:
                        str_vals.append(str(item))
                # Сортируем значения для каноничности
                str_vals.sort() 
                val_str = "+".join(str_vals)
            else:
                # Скаляр
                val_str = str(val)
            
            if val_str:
                parts.append(f"{key}={val_str}")
                
        return "&".join(parts)