import os
import sys
import subprocess
import tempfile
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")

MAX_FILE_SIZE_MB = 20
MAX_DURATION_SEC = 120

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    instrucoes = (
        "Sistema operacional de conversão de Vídeo para Voz.\n\n"
        "Envie um ficheiro de vídeo diretamente neste chat.\n"
        f"- Limite de tamanho: {MAX_FILE_SIZE_MB} MB\n"
        f"- Limite de tempo de extração: {MAX_DURATION_SEC} segundos."
    )
    await update.message.reply_text(instrucoes)

async def processar_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mensagem = update.message
    
    if mensagem.video:
        file_obj = mensagem.video
    elif mensagem.document and mensagem.document.mime_type and mensagem.document.mime_type.startswith('video/'):
        file_obj = mensagem.document
    else:
        return

    if file_obj.file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await mensagem.reply_text(f"Erro restritivo: Ficheiro excede {MAX_FILE_SIZE_MB} MB.")
        return

    aviso = await mensagem.reply_text("A descarregar dados...")

    try:
        telegram_file = await context.bot.get_file(file_obj.file_id)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video,              tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_audio:
            
            video_path = temp_video.name
            audio_path = temp_audio.name

        await telegram_file.download_to_drive(video_path)
        await aviso.edit_text("A processar FFmpeg...")

        comando_ffmpeg = [
            "ffmpeg", "-y", 
            "-i", video_path, 
            "-t", str(MAX_DURATION_SEC), 
            "-vn", 
            "-c:a", "libopus", 
            "-b:a", "32k", 
            audio_path
        ]
        
        subprocess.run(comando_ffmpeg, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await aviso.edit_text("A transmitir ficheiro resultante...")

        with open(audio_path, 'rb') as audio_file:
            await mensagem.reply_voice(voice=audio_file)

        await aviso.delete()

    except subprocess.CalledProcessError:
        await aviso.edit_text("Falha FFmpeg: Formato incompatível ou ficheiro corrompido.")
    except Exception as e:
        logger.error(f"Erro interno: {e}")
        await aviso.edit_text("Exceção não tratada durante a operação.")
    finally:
        if 'video_path' in locals() and os.path.exists(video_path):
            os.remove(video_path)
        if 'audio_path' in locals() and os.path.exists(audio_path):
            os.remove(audio_path)

def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN não definido nas variáveis de ambiente.")
        sys.exit(1)

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, processar_video))

    logger.info("Sistema em execução e a escutar eventos do Telegram.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
