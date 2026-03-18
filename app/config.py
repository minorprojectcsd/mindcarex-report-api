import os
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 🔥 Force .env to override system variables
load_dotenv(BASE_DIR / ".env", override=True)

DATABASE_URL: str = os.getenv("DATABASE_URL", "")
HF_API_TOKEN: str = os.getenv("HF_API_TOKEN", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama3-70b-8192")

print("USING DB:", DATABASE_URL)  # debug

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set.\n"
        "Add your Neon connection string in svc2/.env"
    )