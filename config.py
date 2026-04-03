import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    JWT_SECRET = os.getenv("JWT_SECRET", "finans-asistan-secret-key")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
