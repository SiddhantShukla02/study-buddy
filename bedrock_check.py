"""Quick Amazon Bedrock check. Reads settings from .env, makes one tiny model call, prints the result.

Usage:  python bedrock_check.py
Never prints your key. Safe to commit.
"""
import envfile

loaded = envfile.load_env()

import llm  # noqa: E402  (after load_env so it sees the .env values)

print("Loaded from .env:", ", ".join(loaded) if loaded else "(nothing: using terminal variables, or .env is missing/empty)")
print("Model:", llm.model_id() or "(BEDROCK_MODEL_ID is not set)", "| Region:", llm.region())
if not llm.enabled():
    raise SystemExit("BEDROCK_MODEL_ID is empty. Fill it in .env (see .env.example).")
reply = llm.converse([{"role": "user", "content": [{"text": "Say hi in five words."}]}], "Be brief.")
print("Model replied:", llm.text_of(reply))
print("SUCCESS: Bedrock is working.")
