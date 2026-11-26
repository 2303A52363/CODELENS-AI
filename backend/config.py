import os
from dotenv import load_dotenv
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite"
)
GEMINI_FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv(
        "GEMINI_FALLBACK_MODELS",
        "gemini-3.5-flash"
    ).split(",")
    if m.strip()
]
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb://localhost:27017"
)
MONGO_DB = os.getenv("MONGO_DB", "code_review")
SANDBOX_MODE = os.getenv("SANDBOX_MODE", "local")
EXEC_TIMEOUT = float(os.getenv("EXEC_TIMEOUT", "5"))
EXEC_MEMORY_MB = int(os.getenv("EXEC_MEMORY_MB", "256"))
MAX_CODE_BYTES = int(os.getenv("MAX_CODE_BYTES", "50000"))
CORS_ORIGIN = os.getenv("CORS_ORIGIN","http://localhost:5173")