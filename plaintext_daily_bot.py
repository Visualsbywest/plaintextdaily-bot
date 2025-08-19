"""
plaintext.daily Telegram Agent
--------------------------------
A minimal Telegram bot that acts as your marketing/social media assistant.

Features
- /idea → 3 post ideas (hook + angle) in the brand voice
- /caption → caption only in brand voice
- /post → generate an on-brand image (gpt-image-1) + caption, send back as PNG
- /style → prints the brand system (colors, type vibe, hashtags)

Quick start
1) pip install python-telegram-bot openai pillow python-dotenv requests
2) Create a Telegram bot via @BotFather and grab your token
3) Create a .env next to this file:
   TELEGRAM_BOT_TOKEN=xxxxxxxx
   OPENAI_API_KEY=sk-...
   BRAND_PRIMARY=#2F3435
   BRAND_CREAM=#F4EFE2
   LOGO_URL=https://your-logo.png   # optional; if absent we render a simple 'pd' roundel
4) Run:  python bot.py
   (This uses long polling for simplicity. You can switch to webhook later.)

Notes
- Image generation uses gpt-image-1 and returns a 1024x1024 PNG
- If LOGO_URL is set, the logo is composited bottom-right; else a simple 'pd' mark is drawn
- Keep prompts short and concrete: “practical > perfect”
"""

import io
import os
import base64
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- Load env
load_dotenv()
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
BRAND_PRIMARY = os.getenv("BRAND_PRIMARY", "#2F3435")  # charcoal
BRAND_CREAM = os.getenv("BRAND_CREAM", "#F4EFE2")      # warm cream
LOGO_URL = os.getenv("LOGO_URL", "").strip()

# --- OpenAI lightweight client
import json
import urllib.request

def openai_chat(prompt: str, model: str = "gpt-4o-mini") -> str:
    req = urllib.request.Request(
        url="https://api.openai.com/v1/chat/completions",
        data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    return out["choices"][0]["message"]["content"].strip()


def openai_image(prompt: str, size: str = "1024x1024"):
    req = urllib.request.Request(
        url="https://api.openai.com/v1/images/generations",
        data=json.dumps({
            "model": "gpt-image-1",
            "prompt": prompt,
            "size": size,
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    b64 = out["data"][0]["b64_json"]
    from PIL import Image
    return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")


# --- Brand helpers ---------------------------------------------------------

VOICE = (
    "You are the voice of 'plaintext.daily' — internet field notes, practical > perfect. "
    "Tone: minimal, direct, calm, anti-hype. One idea per post. Keep 12–18 words if possible."
)

HASHTAGS = "#plaintextdaily #internetfieldnotes #practicaloverperfect #makerhabits #shipdaily #minimaldesign"

STYLE_PROMPT = (
    "Minimal, type-forward square card. Warm cream background (#F4EFE2), charcoal text (#2F3435). "
    "Use whitespace, subtle grain, tiny geometric accent (dot or line). Optional small 'pd' roundel bottom-right. "
    "No photos, no gradients."
)


def add_logo_or_mark(img):
    img = img.copy()
    if LOGO_URL:
        try:
            logo = Image.open(io.BytesIO(requests.get(LOGO_URL, timeout=10).content)).convert("RGBA")
            w = int(img.width * 0.16)
            ratio = w / logo.width
            logo = logo.resize((w, int(logo.height * ratio)))
            img.alpha_composite(logo, (img.width - w - 40, img.height - logo.height - 40))
            return img
        except Exception:
            pass
    # draw a simple 'pd' circle mark if no logo
    draw = ImageDraw.Draw(img)
    r = int(img.width * 0.12)
    cx = img.width - r - 40
    cy = img.height - r - 40
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=BRAND_PRIMARY)
    # attempt to draw 'pd'
    try:
        font = ImageFont.load_default()
        text = "pd"
        tw, th = draw.textsize(text, font=font)
        draw.text((cx - tw/2, cy - th/2), text, fill=BRAND_CREAM, font=font)
    except Exception:
        pass
    return img


# --- Commands -------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "plaintext.daily assistant online. Try /idea, /caption, or /post"
    )


async def idea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = (
        f"{VOICE} Generate 3 distinct post ideas for today. "
        "Format each as: \n- Hook: <7-10 words>\n  Angle: <one line>."
    )
    text = openai_chat(prompt)
    await update.message.reply_text(text)


async def caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args) or "a tiny workflow habit that compounds"
    prompt = (
        f"{VOICE} Write one Instagram caption about: {topic}. "
        "1-2 short sentences. End with: 'practical > perfect'. No emojis."
    )
    text = openai_chat(prompt)
    await update.message.reply_text(f"{text}\n\n{HASHTAGS}")


async def post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args) or "one simple framework to ship daily"
    # 1) caption
    cap_prompt = (
        f"{VOICE} Write 1–2 short sentences for Instagram about: {topic}. "
        "Make it crisp, zero fluff. End with 'practical > perfect'."
    )
    caption_text = openai_chat(cap_prompt)

    # 2) image
    img_prompt = (
        f"{STYLE_PROMPT} Content text theme: {topic}. Render as a clean poster (no photo)."
    )
    img = openai_image(img_prompt)
    img = add_logo_or_mark(img)

    # 3) send
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    await update.message.reply_photo(photo=buf, caption=f"{caption_text}\n\n{HASHTAGS}")


async def style(update: Update, context: ContextTypes.DEFAULT_TYPE):
    spec = (
        "Brand quick-specs\n"
        f"Primary: {BRAND_PRIMARY}\nCream: {BRAND_CREAM}\nType vibe: monospaced, generous tracking, lowercase\n"
        "Imagery: minimal cards, whitespace, subtle grain, small 'pd' roundel\n"
        f"Hashtags: {HASHTAGS}"
    )
    await update.message.reply_text(spec)


def main():
    if not TG_TOKEN or not OPENAI_API_KEY:
        raise SystemExit("Missing TELEGRAM_BOT_TOKEN or OPENAI_API_KEY in .env")
    app = ApplicationBuilder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("idea", idea))
    app.add_handler(CommandHandler("caption", caption))
    app.add_handler(CommandHandler("post", post))
    app.add_handler(CommandHandler("style", style))
    print("Bot running… Ctrl+C to stop")
    app.run_polling()


if __name__ == "__main__":
    main()
