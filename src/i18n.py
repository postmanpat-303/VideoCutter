import ctypes
import json
import locale

from src.config import get_resource_path


class LanguageManager:
    def __init__(self):
        self.translations = {}
        lang_code = self.detect_language()
        self.load_language(lang_code)

    def detect_language(self):
        try:
            # 1. Спробуємо отримати поточну локаль (може повернути 'Ukrainian_Ukraine' або 'uk_UA')
            # Використовуємо LC_CTYPE, бо на Windows LC_MESSAGES часто не ініціалізовано
            current_locale, _ = locale.getlocale()

            # 2. Якщо порожньо, спробуємо отримати системну локаль за замовчуванням
            if not current_locale:
                # Використовуємо getencoding як непрямий метод або повертаємося до базових налаштувань
                current_locale = ctypes.windll.kernel32.GetUserDefaultUILanguage()
                # Код 1058 — це українська в Windows (LCID)
                if current_locale == 1058:
                    return "uk"

            if current_locale:
                current_locale = str(current_locale).lower()
                # Перевірка за ключовими словами (охоплює 'uk_ua', 'ukrainian', 'ukraine')
                if any(word in current_locale for word in ["uk", "ua", "ukrainian"]):
                    return "uk"

        except Exception as e:
            print(f"Language detection error: {e}")

        return "en"  # Англійська як стандарт для всього іншого

    def load_language(self, lang_code):
        lang_file = get_resource_path(f"locales/{lang_code}.json")
        if not lang_file.exists():
            lang_file = get_resource_path("locales/en.json")
        try:
            with open(lang_file, "r", encoding="utf-8") as f:
                self.translations = json.load(f)
        except:
            self.translations = {}

    def get(self, key, **kwargs):
        text = self.translations.get(key, key)
        try:
            return text.format(**kwargs) if kwargs else text
        except KeyError:
            return text
