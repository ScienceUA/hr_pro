class CSS:
    """
    Централизованное хранилище CSS-селекторов.
    Связь с PageType:
    - SIGNATURE_* -> используются в BaseParser._classify_page() для определения PageType
    - RESUME_* -> используются для извлечения данных, если PageType == RESUME
    - SERP_* -> используются для извлечения данных, если PageType == SERP
    """
    
    # --- 1. Signatures (Определение PageType) ---
    
    # PageType.LOGIN
    SIGNATURE_LOGIN = "form[action*='login'], input[name='login']"
    
    # PageType.CAPTCHA
    SIGNATURE_CAPTCHA = "#g-recaptcha-response, iframe[src*='captcha']"
    
    # PageType.BAN (WAF / Cloudflare)
    # :contains не работает в BS4.select, проверяем наличие контейнера ошибки
    SIGNATURE_WAF = "div.cf-error-details" 
    
    # PageType.NOT_FOUND
    # Требует доп. проверки текста "не знайдено" внутри
    SIGNATURE_404 = "h1.text-center" 
    
    # PageType.RESUME
    # Уникальный контейнер резюме (из отчета: div#resume_7502793)
    SIGNATURE_RESUME = "div[id^='resume_']"

    # PageType.SERP
    # Контейнер списка
    SIGNATURE_SERP = "#pjax-resume-list"


    # --- 2. SERP Data Extraction (Только если PageType.SERP) ---
    
    # Карточка резюме.
    # Из отчета: карточки имеют класс .card-visited (если посещали) или .card
    # Исключаем прямые div, берем только сущности с классами карточки
    SERP_ITEM = "#pjax-resume-list div.card, #pjax-resume-list div.card-visited"
    
    # Данные внутри карточки
    SERP_LINK = "h2 a" 
    SERP_TITLE = "h2 a"
    SERP_SALARY = "p.nowrap"
    SERP_SNIPPET = "div.mt-sm, p.text-default-7"
    SERP_NEXT_PAGE = "ul.pagination a[rel='next']"
    SERP_TOTAL_FOUND = "h1, h2, .text-default-7, .text-muted"


    # --- 3. DETAIL Data Extraction (Только если PageType.RESUME) ---
    
    # Основные данные
    RESUME_H1 = "h1"                   # Имя
    RESUME_POSITION = "h2.title-print" # Должность
    
    # Монолитный текст резюме (часто для резюме из прикреплённого файла)
    RESUME_ADD_INFO = "div#add_info.wordwrap, div.wordwrap#add_info"

    # ===== "Розглядає посади" (positions the candidate considers) =====
    # HTML pattern (confirmed in provided page source):
    # label:  <span class="dt-print">Розглядає посади:</span>
    # value:  <span class="dt-print-desc">CMO, Маркетолог, ...</span> (usually in the next <tr>)
    RESUME_CONSIDERS_LABEL = "span.dt-print"
    RESUME_CONSIDERS_VALUE = "span.dt-print-desc"

    # Зарплата
    RESUME_SALARY_BLOCK = "ul.list-unstyled > li.no-style"
    
    # Мета (Возраст, Город)
    RESUME_META_LIST = "ul.list-unstyled li"

    # Блоки (Опыт, Образование)
    BLOCK_HEADER = "h2"
    
    # Навыки
    SKILL_TAGS = "ul.list-unstyled.my-0.flex.flex-wrap span.ellipsis"
    
    # Скрытые контакты (Флаг)
    RESUME_HIDDEN_ALERT = "div.alert-warning, div.modal-silence-alert"

    # ===== Uploaded file (resume attached as a file) =====

    # Download links
    RESUME_FILE_DOWNLOAD_ORIGINAL = "a.js-resume-file-download"
    RESUME_FILE_DOWNLOAD_PDF = "a.js-resume-file-pdf-download"
    RESUME_FILE_PRINT_PDF = "a.js-resume-file-pdf-print"

    # File preview thumbnails (present even if text preview is absent)
    RESUME_FILE_PREVIEW_CONTAINER = "div.resume-preview.clearfix"
    RESUME_FILE_PREVIEW_ITEM = "div.resume-preview-item.js-show-pdf-viewer"

    # Warning block (resume uploaded as file)
    RESUME_FILE_WARNING = "div.alert.alert-warning.mt-lg"
