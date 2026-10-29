"""List models available to the OpenAI API key configured in this project."""

from pathlib import Path
import os

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv(Path(__file__).resolve().with_name(".env"))
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise SystemExit("OPENAI_API_KEY is missing. Add it to this project's .env file.")

try:
    models = OpenAI(api_key=api_key).models.list()
except Exception as exc:
    raise SystemExit(f"Could not list OpenAI models ({type(exc).__name__}). Check the key and network connection.") from None

print("Available OpenAI models:")
for model in sorted(models.data, key=lambda item: item.id):
    print(model.id)
