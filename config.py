import os
import json
from pathlib import Path

_SETTINGS_FILE = Path(__file__).parent / "settings.json"


def _load():
    if _SETTINGS_FILE.exists():
        try:
            with open(_SETTINGS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


_s = _load()

DEEPSEEK_API_KEY  = _s.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = _s.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
MAIN_MODEL        = _s.get("MAIN_MODEL", "deepseek-chat")
REFLECT_MODEL     = _s.get("REFLECT_MODEL", "deepseek-reasoner")
USE_MOCK          = not bool(DEEPSEEK_API_KEY)
DB_PATH           = "slang_learning.db"
MAX_RETRIES       = 2
QUALITY_THRESHOLD = float(_s.get("QUALITY_THRESHOLD", 7.0))
