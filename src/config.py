import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# File Paths
DATA_DIR = BASE_DIR / "data"
EXCEL_PATH = DATA_DIR / "Symax_AI_Stock_Assessment_100plus.xlsx"

# Location Normalization Mapping
LOCATION_MAPPING = {
    "hyd": "Hyderabad",
    "hyd.": "Hyderabad",
    "hyderabad": "Hyderabad",
    "hyderbad": "Hyderabad",
    "blr": "Bangalore",
    "bangalore": "Bangalore",
    "banglore": "Bangalore",
    "bengaluru": "Bangalore",
}

STANDARD_LOCATIONS = ["Hyderabad", "Bangalore"]

# LLM Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")  # 'groq', 'gemini', 'openai'
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")  # default groq model
