import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Groq API Configuration
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

# Unsplash API key for assistant image cards
UNSPLASH_API_KEY = os.environ.get("UNSPLASH_API_KEY", "")

# Timeout settings (in seconds)
TIMEOUT = int(os.environ.get("TIMEOUT", "30"))
