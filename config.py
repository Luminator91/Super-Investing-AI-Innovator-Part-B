"""All tunable settings live here, so behaviour is easy to explain and change."""
import os
from datetime import date

TODAY = date(2026, 9, 23)   # the assignment says: assume today is 23 Sep 2026
STALE_DAYS = 180            # a document older than this is flagged as stale
MAX_WORDS = 450             # roughly one page
MAX_REPAIR_ROUNDS = 2       # how many times the verifier may send the draft back
MAX_DOC_CHARS = 12000       # per-document cap, keeps small local models in context

# Any OpenAI-compatible endpoint can be added here as one more dict entry.
PROVIDERS = {
    "groq": {      # free API key, no card, very fast, strong 70B model
        "kind": "openai",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "model_env": "GROQ_MODEL",
        "key_env": "GROQ_API_KEY",
    },
    "ollama": {    # fully local and offline, no key, slower on CPU
        "kind": "ollama",
        "base_url": "http://localhost:11434",
        "model": "qwen2.5:7b",
        "model_env": "OLLAMA_MODEL",
        "key_env": None,
    },
}


def provider_name() -> str:
    return os.getenv("LLM_PROVIDER", "groq")
