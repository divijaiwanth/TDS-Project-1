import json
import time
import os
from dotenv import load_dotenv
load_dotenv()
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# --- fill these in with your own values ---
GITHUB_REPO = "divijaiwanth/TDS-Project-1"
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
AIPIPE_TOKEN = os.environ["AIPIPE_TOKEN"]
LOG_URL = "https://raw.githubusercontent.com/divijaiwanth/TDS-Project-1/refs/heads/main/run.jsonl"  # see Step 5 — where run.jsonl will be hosted
# -------------------------------------------

client = OpenAI(base_url="https://aipipe.org/openai/v1", api_key=AIPIPE_TOKEN)
LOG_FILE = "run.jsonl"

# Keeps the last few messages per chat, so multi-turn questions work —
# "answer the LAST message" still needs the earlier ones for context.
conversation_history = {}
import requests
import base64

GITHUB_REPO = "divijaiwanth/TDS-Project-1"  # your username/repo
GITHUB_FILE_PATH = "run.jsonl"

def push_log():
    try:
        token = os.environ["GITHUB_TOKEN"]
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE_PATH}"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json"
        }

        # Read current local log file content
        with open(LOG_FILE, "r") as f:
            content = f.read()
        encoded_content = base64.b64encode(content.encode()).decode()

        # Get the current file's SHA (required by GitHub API to update an existing file)
        get_resp = requests.get(api_url, headers=headers)
        sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None

        payload = {
            "message": "log update",
            "content": encoded_content,
        }
        if sha:
            payload["sha"] = sha

        put_resp = requests.put(api_url, headers=headers, json=payload)
        if put_resp.status_code not in (200, 201):
            print(f"Push failed: {put_resp.status_code} {put_resp.text}")
    except Exception as e:
        print(f"Push failed: {e}")

def log_event(event: dict):
    event["timestamp"] = time.time()
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    log_event({"type": "incoming", "chat_id": chat_id, "text": user_text})

    history = conversation_history.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_text})

    # Ask the AI to work out the answer. The system prompt tells it exactly how to
    # format the final reply — this is the part that MUST match what the question asked.
    system_prompt = (
        "You are a careful data analyst. The user's LAST message asks a data-analysis "
        "question and tells you exactly what JSON shape to reply with. Work out the "
        "real answer (use any public data you know, e.g. MOSPI statistics, general "
        "world knowledge, or arithmetic on numbers given in the message). "
        "Reply with ONLY that exact JSON object and absolutely nothing else — no "
        "explanation, no markdown, no code fences, just the raw JSON."
    )
    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "system", "content": system_prompt}] + history[-6:],
    )
    reply_text = response.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": reply_text})

    # Make sure we actually reply with valid JSON containing "log_url" — if the model
    # forgot the log_url field or wrapped it in markdown, fix it up here so the grader
    # never sees a malformed reply.
    try:
        parsed = json.loads(reply_text)
    except json.JSONDecodeError:
        # Model added extra text — try to pull out just the {...} part.
        start, end = reply_text.find("{"), reply_text.rfind("}")
        parsed = json.loads(reply_text[start:end + 1])
    if "log_url" in user_text:
        parsed["log_url"] = LOG_URL
    final_reply = json.dumps(parsed)

    log_event({"type": "outgoing", "chat_id": chat_id, "text": final_reply})
    push_log()
    await update.message.reply_text(final_reply)
app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
print("Bot is running... (Ctrl+C to stop)")
app.run_polling()
