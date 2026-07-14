"""Central configuration. Loads secrets from .env, never hardcodes them."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Paths ---
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
KB_DIR = ROOT_DIR / "knowledge-base"
TICKETS_PATH = DATA_DIR / "tickets.json"
ACCOUNTS_PATH = DATA_DIR / "accounts.json"

# --- Provider selection: "gemini" or "groq" ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# --- Generation settings ---
# Determinism: temperature 0 => same input produces the same output (Task 2 requirement)
TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 2048

# --- Enums from DATA_SCHEMA.md (used to constrain LLM output) ---
CATEGORIES = [
    "Bug", "Feature Request", "How-To", "Performance",
    "Billing", "Integration", "Onboarding", "Data Loss",
]
URGENCIES = ["P1", "P2", "P3", "P4"]
PRODUCTS = [
    "DataBridge Pro", "CloudSync", "AnalyticsHub",
    "SecureVault", "WorkflowEngine",
]
RESPONDER_TEAMS = [
    "Tier-1 Support", "Tier-2 Support", "Integrations Team",
    "Billing Team", "Data Recovery Team", "Product Team",
    "Onboarding Team",
]