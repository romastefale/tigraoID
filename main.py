import os
import time
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # única variável que você precisa setar
URL = "https://getgems.io/collection/EQCA14o1-VWhS2efqoh_9M1b_A9DtKTuoqfmkn83AbJzwnPi?categoryId=109&filter=%7B%22sort%22%3A%22PriceAsc%22%2C%22priceRange%22%3A%5B11%2C25%5D%2C%22saleType%22%3A%22fix_price%22%2C%22q%22%3A%22%22%2C%22attributes%22%3A%7B%7D%2C%22collections%22%3A%5B%5D%2C%22ownership%22%3A%7B%7D%2C%22priceCurrency%22%3A%5B%5D%2C%22kind%22%3A%5B%5D%2C%22stickerMarketplaceIds%22%3A%5B%5D%7D"
# ============================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def scrape_usernames():
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
        driver.get(URL)
        time.sleep(4)
        
        # Scroll infinito pra carregar a lista
        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(25):  # ajusta conforme necessário
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.8)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        
        # Tenta vários seletores comuns do Getgems
        items = driver.find_elements(By.CSS_SELECTOR, "[class*='Item'], [class*='Nft'], [class*='Card'], tr, [data-testid*='item']")
        
        for item in items:
            try:
                text = item.text
                if not text or "@" not in text:
                    continue
                
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                username = None
                price = None
                
                for line in lines:
                    if line.startswith("@") and len(line) > 1:
                        username = line
                    if any(c.isdigit() for c in line) and ("TON" in line.upper() or "₮" in line or "·" in line):
                        price = line
                
                if username and username not in [r[0] for r in results]:
                    results.append((username, price or "?"))
            except:
                continue
                
    finally:
        driver.quit()
    
    return results

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot de usernames Getgems.\n\n"
        "Comandos:\n"
        "/scrape - busca os @ na faixa 11-25 TON\n"
        "/ping - testa se está vivo"
    )

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong")

async def scrape(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Buscando... isso pode levar 30-60 segundos.")
    
    try:
        data = scrape_usernames()
        
        if not data:
            await msg.edit_text("Nenhum username encontrado (site pode ter bloqueado ou a estrutura mudou).")
            return
        
        # Manda em pedaços pra não estourar limite do Telegram
        text = f"Encontrados {len(data)} usernames:\n\n"
        for user, price in data:
            text += f"{user}  —  {price}\n"
            
            if len(text) > 3500:
                await update.message.reply_text(text)
                text = ""
        
        if text:
            await update.message.reply_text(text)
            
        await msg.delete()
        
    except Exception as e:
        logger.exception("Erro no scrape")
        await msg.edit_text(f"Erro: {str(e)[:200]}")

def main():
    if not BOT_TOKEN:
        raise ValueError("Defina a variável de ambiente BOT_TOKEN")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("scrape", scrape))
    
    print("Bot rodando...")
    app.run_polling()

if __name__ == "__main__":
    main()
