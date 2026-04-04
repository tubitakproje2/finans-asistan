import os
import itertools
from dotenv import load_dotenv

load_dotenv()

class Config:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    JWT_SECRET   = os.getenv("JWT_SECRET", "finans-asistan-secret-key")
    DEBUG        = os.getenv("DEBUG", "False").lower() == "true"

    GEMINI_API_KEYS = [
        key for key in [
            os.getenv("GEMINI_API_KEY"),
            os.getenv("GEMINI_API_KEY_2"),
            os.getenv("GEMINI_API_KEY_3"),
        ] if key
    ]

    # Geriye dönük uyumluluk
    GEMINI_API_KEY = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else None

_key_cycle = None

def get_gemini_key() -> str:
    global _key_cycle
    if _key_cycle is None:
        _key_cycle = itertools.cycle(Config.GEMINI_API_KEYS)
    return next(_key_cycle)
