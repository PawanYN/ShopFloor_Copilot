import os

DATABASE_PATH = os.getenv("DATABASE_PATH", "/data/audit.db")
CHROMA_PATH = os.getenv("CHROMA_PATH", "/data/chroma")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL") or "bge-m3"
ANSWER_MODEL = os.getenv("ANSWER_MODEL") or "llama3.1"
JUDGE_MODEL = os.getenv("JUDGE_MODEL") or "gemma3:12b"
MODEL_CONTEXT_TOKENS = int(os.getenv("MODEL_CONTEXT_TOKENS", "8192"))

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "5"))
# Whole-request time limit before the ready-made reply. 300 suits a local machine; 10 is the value meant for a plant.
LATENCY_CEILING_SECONDS = float(os.getenv("LATENCY_CEILING_SECONDS", "300"))
# After this long without a decision, a proposed action is shown as overdue (SOP-03 section 3.4).
APPROVAL_DUE_MINUTES = float(os.getenv("APPROVAL_DUE_MINUTES", "30"))

# Learning loop: how many passages to choose between, how often to try another, and how fast scores follow new results.
TOP_K_CHOICES = tuple(int(value) for value in os.getenv("TOP_K_CHOICES", "1,3,5").split(","))
EXPLORE_RATE = float(os.getenv("EXPLORE_RATE", "0.1"))
LEARNING_STEP = float(os.getenv("LEARNING_STEP", "0.1"))

SOP_DIR = os.getenv("SOP_DIR", "data/sops")
EVAL_DIR = os.getenv("EVAL_DIR", "data/eval")
PLANT = os.getenv("PLANT", "PN-01")
