import os
import time
import logging
import tempfile
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def scrape_from_url(url: str):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=options)
    results = []
    
    try:
        driver.get(url)
        time.sleep(4)
        
        # Scroll infinito
        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(30):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.7)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        
        items = driver.find_elements(By.CSS_SELECTOR, "[class*='Item'], [class*='Nft'], [class*='Card'], tr, [data-testid*='item']")
        
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
                    if any(c.isdigit() for c in line) and ("TON" in line.upper() or "₮" in line or "·" in line or "GRAM" in line.upper()):
                        price = line.replace("\n", " ").strip()
                
                if username and username not in seen:
                    seen.add(username)
                    results.append(f"{username}, {price or '?'}")
            except:
                continue
                
    finally:
        driver.quit()
    
    return results

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Manda o link da busca do Getgems.\n"
        "Eu abro, extraio os @ + preço e te devolvo um .txt."
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
            await msg.edit_text("Nada encontrado. Site pode ter bloqueado ou a estrutura mudou.")
            return
        
        # Cria o arquivo txt
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("\n".join(data))
            temp_path = f.name
        
        await update.message.reply_document(
            document=open(temp_path, "rb"),
            filename="usernames.txt",
            caption=f"{len(data)} usernames encontrados"
        )
        
        os.unlink(temp_path)
        await msg.delete()
        
    except Exception as e:
        logger.exception("Erro")
        await msg.edit_text(f"Erro: {str(e)[:250]}")

def main():
    if not BOT_TOKEN:
        raise ValueError("Defina BOT_TOKEN")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    print("Bot rodando...")
    app.run_polling()

if __name__ == "__main__":
    main()
