import os
import time
import logging
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
import processor
import words

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_filters = {}


def scrape_from_url(url: str):
    options = Options()
    options.add_argument("--headless")
    options.set_preference(
        "general.useragent.override",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    )
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)

    service = Service(executable_path="/usr/local/bin/geckodriver")
    driver = webdriver.Firefox(service=service, options=options)
    results = []

    try:
        driver.get(url)
        time.sleep(5)

        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(30):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.8)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        items = driver.find_elements(
            By.CSS_SELECTOR,
            "[class*='Item'], [class*='Nft'], [class*='Card'], tr, [data-testid*='item'], [class*='nft']",
        )

        seen = set()
        for item in items:
            try:
                text = item.text
                if not text or "@" not in text:
                    continue

                lines = [l.strip() for l in text.split("\n") if l.strip()]
                username = None
                price = None

                for line in lines:
                    if line.startswith("@") and len(line) > 1 and " " not in line:
                        username = line
                    if any(c.isdigit() for c in line) and (
                        "TON" in line.upper()
                        or "₮" in line
                        or "·" in line
                        or "GRAM" in line.upper()
                    ):
                        price = line.replace("\n", " ").strip()

                if username and username not in seen:
                    seen.add(username)
                    results.append(f"{username}, {price or '?'}")
            except Exception:
                continue

    finally:
        driver.quit()

    return results


def build_keyboard(selected: dict):
    def mark(key, label):
        return f"✅ {label}" if selected.get(key) else label

    keyboard = [
        [
            InlineKeyboardButton(mark("sem_preco", "Sem preço"), callback_data="f:sem_preco"),
            InlineKeyboardButton(mark("ordenar", "Ordenar A-Z"), callback_data="f:ordenar"),
        ],
        [
            InlineKeyboardButton(mark("preco_menor", "Preço ↑"), callback_data="f:preco_menor"),
            InlineKeyboardButton(mark("preco_maior", "Preço ↓"), callback_data="f:preco_maior"),
        ],
        [
            InlineKeyboardButton(mark("com_numero", "Com número"), callback_data="f:com_numero"),
            InlineKeyboardButton(mark("sem_numero", "Sem número"), callback_data="f:sem_numero"),
        ],
        [
            InlineKeyboardButton(mark("tamanho", "Tamanho 5-12"), callback_data="f:tamanho"),
        ],
        [
            InlineKeyboardButton(mark("palavra_exata", "Palavra exata"), callback_data="f:palavra_exata"),
            InlineKeyboardButton(mark("palavra_proxima", "Parece palavra"), callback_data="f:palavra_proxima"),
        ],
        [
            InlineKeyboardButton("🟢 Gerar resultado", callback_data="f:gerar"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Manda o link da busca do Getgems.\n"
        "Eu abro, extraio os @ + preço e te devolvo um .txt.\n"
        "Depois você escolhe os filtros pelos botões."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if "getgems.io" not in url:
        await update.message.reply_text("Manda um link
