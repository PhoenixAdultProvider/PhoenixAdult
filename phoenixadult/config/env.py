from __future__ import annotations

import os
from pathlib import Path


def _cwd() -> Path:
    return Path.cwd()


def _flag(name: str, default: str) -> str:
    return (os.environ.get(name) or default).strip().lower()


class _Env:
    @property
    def is_production(self) -> bool:
        return os.environ.get('NODE_ENV', 'production').strip().lower() not in {'development', 'dev', 'test', 'local'}

    @property
    def log_dir(self) -> str:
        return os.environ.get('LOG_DIR') or str(_cwd() / 'logs')

    @property
    def log_redact_hosts(self) -> bool:
        raw = os.environ.get('LOG_REDACT_HOSTS')
        if raw is None or raw.strip() == '':
            return self.is_production
        return raw.strip().lower() not in {'0', 'false', 'no', 'off'}

    @property
    def log_redact_token(self) -> bool:
        raw = os.environ.get('LOG_REDACT_TOKEN')
        if raw is None or raw.strip() == '':
            return self.is_production
        return raw.strip().lower() not in {'0', 'false', 'no', 'off'}

    @property
    def https_proxy(self) -> str | None:
        return os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy') or os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')

    @property
    def disable_auto_match(self) -> bool:
        return _flag('DISABLE_AUTO_MATCH', 'false') != 'false'

    @property
    def disable_auto_match_raw(self) -> str | None:
        return os.environ.get('DISABLE_AUTO_MATCH')

    @property
    def search_title_trash_raw(self) -> str | None:
        return os.environ.get('SEARCH_TITLE_TRASH')

    @property
    def search_strip_actors_raw(self) -> str | None:
        return os.environ.get('SEARCH_STRIP_ACTORS')

    @property
    def strip_symbols_enabled(self) -> bool:
        return _flag('STRIP_ENABLE', 'false') == 'true'

    @property
    def strip_symbol(self) -> str:
        return os.environ.get('STRIP_SYMBOL') or ''

    @property
    def strip_symbol_reverse(self) -> str:
        return os.environ.get('STRIP_SYMBOL_REVERSE') or ''

    @property
    def manual_nfo_token(self) -> str:
        return (os.environ.get('MANUAL_NFO_TOKEN') or 'manual').strip().lower()

    @property
    def image_dir(self) -> str:
        return os.environ.get('IMAGE_DIR') or str(_cwd() / 'local' / 'images')

    @property
    def logo_cache_dir(self) -> str:
        return str(Path(self.image_dir) / 'logos')

    @property
    def scene_gap(self) -> float:
        try:
            return max(0.0, float(os.environ.get('SCENE_GAP') or 10))
        except ValueError:
            return 10.0

    @property
    def refresh_force_count(self) -> int:
        try:
            return min(10, max(1, int(os.environ.get('REFRESH_FORCE_COUNT') or 3)))
        except ValueError:
            return 3

    @property
    def search_store_ttl_days(self) -> int:
        try:
            return max(0, int(os.environ.get('SEARCH_STORE_TTL_DAYS') or 0))
        except ValueError:
            return 0

    @property
    def state_db_path(self) -> str:
        return os.environ.get('STATE_DB_PATH') or './local/phoenixadult.db'

    @property
    def db_backup_interval_hours(self) -> int:
        try:
            return max(0, int(os.environ.get('DB_BACKUP_INTERVAL_HOURS') or 24))
        except ValueError:
            return 24

    @property
    def db_backup_keep(self) -> int:
        try:
            return max(1, int(os.environ.get('DB_BACKUP_KEEP') or 7))
        except ValueError:
            return 7

    @property
    def db_backup_dir(self) -> str:
        return os.environ.get('DB_BACKUP_DIR') or ''

    @property
    def manual_nfo_path(self) -> str:
        return os.environ.get('MANUAL_NFO_PATH') or str(_cwd() / 'local' / 'manual')

    @property
    def image_max_bytes_raw(self) -> str | None:
        return os.environ.get('IMAGE_MAX_BYTES')

    @property
    def image_proxy_pin(self) -> bool:
        return _flag('IMAGE_PROXY_PIN', 'true') != 'false'

    @property
    def image_guard_enabled(self) -> bool:
        return _flag('IMAGE_GUARD_ENABLE', '') == 'true'

    @property
    def bypass_auto_retry(self) -> bool:
        return _flag('BYPASS_AUTO_RETRY', '') == 'true'

    @property
    def bypass_order_raw(self) -> str | None:
        return os.environ.get('BYPASS_ORDER')

    @property
    def bypass_timeout_ms(self) -> int:
        try:
            raw = int(os.environ.get('BYPASS_TIMEOUT_MS') or '10000')
        except ValueError:
            return 10_000
        return raw if raw > 0 else 10_000

    @property
    def playwright_browser(self) -> str:
        val = (os.environ.get('PLAYWRIGHT_BROWSER') or 'chromium').strip().lower()
        return val if val in ('chromium', 'firefox', 'webkit') else 'chromium'

    @property
    def flaresolverr_url(self) -> str:
        return os.environ.get('FLARESOLVERR_URL') or ''

    @property
    def reqbin_enabled(self) -> bool:
        return _flag('REQBIN_ENABLE', 'false') == 'true'

    @property
    def reqbin_api_key(self) -> str | None:
        return os.environ.get('REQBIN_API_KEY')

    @property
    def people_cache_dir(self) -> str:
        return str(Path(self.image_dir) / 'people')

    @property
    def people_cache_enabled(self) -> bool:
        return _flag('PEOPLE_CACHE_ENABLE', 'true') != 'false'

    @property
    def people_cache_replace_enabled(self) -> bool:
        return _flag('PEOPLE_CACHE_REPLACE_ENABLE', 'false') == 'true'

    @property
    def people_cache_face_enabled(self) -> bool:
        return _flag('PEOPLE_CACHE_FACE_ENABLE', 'false') == 'true'

    @property
    def metadata_cache_enabled(self) -> bool:
        return _flag('METADATA_CACHE_ENABLE', 'false') == 'true'

    @property
    def metadata_cache_dir(self) -> str:
        return os.environ.get('METADATA_CACHE_DIR') or str(_cwd() / 'local' / 'cache')

    @property
    def people_source_order_raw(self) -> str | None:
        return os.environ.get('PEOPLE_SOURCE_ORDER')

    @property
    def image_base_url_raw(self) -> str:
        return _flag('IMAGE_BASE_URL', 'baseurl')

    @property
    def gender_detect_enabled(self) -> bool:
        return _flag('GENDER_DETECT_ENABLE', 'true') != 'false'

    @property
    def gender_skip_male_enabled(self) -> bool:
        return _flag('GENDER_SKIP_MALE_ENABLE', 'false') == 'true'

    @property
    def generic_image_enabled(self) -> bool:
        return _flag('GENERIC_IMAGE_ENABLE', 'true') != 'false'

    @property
    def generic_female_url_raw(self) -> str | None:
        return os.environ.get('GENERIC_FEMALE_URL')

    @property
    def generic_male_url_raw(self) -> str | None:
        return os.environ.get('GENERIC_MALE_URL')

    @property
    def adult_empire_login_token(self) -> str | None:
        return os.environ.get('ADULT_EMPIRE_LOGIN_TOKEN')

    @property
    def data18_enabled(self) -> bool:
        return _flag('DATA18_ENABLE', '') == 'true'

    @property
    def data18_accuracy(self) -> int:
        try:
            raw = int(os.environ.get('DATA18_ACCURACY') or '100')
        except ValueError:
            return 100
        return raw if 0 <= raw <= 100 else 100

    @property
    def data18_extra_enabled(self) -> bool:
        return _flag('DATA18_EXTRA', '') == 'true'

    @property
    def google_search_api_key(self) -> str | None:
        return os.environ.get('GOOGLE_SEARCH_API_KEY')

    @property
    def google_search_cx(self) -> str | None:
        return os.environ.get('GOOGLE_SEARCH_CX')

    @property
    def phoenix_extra_collections(self) -> bool:
        return _flag('PHOENIX_EXTRA_COLLECTIONS', '') == 'true'


env = _Env()
