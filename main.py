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

        # Scroll infinito
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
        await update.message.reply_text("Manda um link válido do getgems.io")
        return

    msg = await update.message.reply_text("Processando... pode levar 30-60s")

    try:
        data = scrape_from_url(url)

        if not data:
            await msg.edit_text(
                "Nada encontrado. Site pode ter bloqueado ou a estrutura mudou."
            )
            return

        content = "\n".join(data)
        context.user_data["last_txt"] = content
        user_filters[update.effective_user.id] = {}

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            temp_path = f.name

        await update.message.reply_document(
            document=open(temp_path, "rb"),
            filename="usernames.txt",
            caption=f"{len(data)} usernames encontrados",
        )
        os.unlink(temp_path)

        await update.message.reply_text(
            "Escolha os filtros (pode marcar vários) e clique em Gerar:",
            reply_markup=build_keyboard({}),
        )
        await msg.delete()

    except Exception as e:
        logger.exception("Erro")
        await msg.edit_text(f"Erro: {str(e)[:250]}")


async def filter_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if user_id not in user_filters:
        user_filters[user_id] = {}

    if data == "f:gerar":
        content = context.user_data.get("last_txt")
        if not content:
            await query.edit_message_text(
                "Nenhum arquivo carregado. Manda um link primeiro."
            )
            return

        options = user_filters[user_id]
        items = processor.parse_lines(content)
        result = processor.apply_filters(items, options)
        txt = processor.to_txt(result, sem_preco=options.get("sem_preco", False))

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(txt)
            path = f.name

        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=open(path, "rb"),
            filename="filtrado.txt",
            caption=f"{len(result)} usernames após filtros",
        )
        os.unlink(path)
        return

    # toggle da opção
    key = data.replace("f:", "")
    user_filters[user_id][key] = not user_filters[user_id].get(key, False)

    # desmarca opções opostas
    if key == "com_numero" and user_filters[user_id][key]:
        user_filters[user_id]["sem_numero"] = False
    if key == "sem_numero" and user_filters[user_id][key]:
        user_filters[user_id]["com_numero"] = False
    if key == "preco_menor" and user_filters[user_id][key]:
        user_filters[user_id]["preco_maior"] = False
    if key == "preco_maior" and user_filters[user_id][key]:
        user_filters[user_id]["preco_menor"] = False

    await query.edit_message_reply_markup(
        reply_markup=build_keyboard(user_filters[user_id])
    )


def main():
    if not BOT_TOKEN:
        raise ValueError("Defina BOT_TOKEN")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(filter_callback, pattern="^f:"))

    print("Bot rodando...")
    app.run_polling()


if __name__ == "__main__":
    main()
