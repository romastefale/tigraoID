import os
import sys
import subprocess
import tempfile
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from PIL import Image, ImageOps, ImageDraw

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
MAX_FILE_SIZE_MB = 20
MAX_DURATION_SEC = 120

def criar_mascara_arredondada(tamanho, raio):
    """Gera uma máscara com fundo preto e quadrado central branco com bordas arredondadas."""
    mascara = Image.new('L', tamanho, 0)
    draw = ImageDraw.Draw(mascara)
    draw.rounded_rectangle((0, 0, tamanho[0], tamanho[1]), raio, fill=255)
    return mascara

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    instrucoes = (
        "Sistema de conversão de Mídia.\n\n"
        "Envie um vídeo ou uma foto. O sistema exibirá botões para escolher a formatação desejada."
    )
    await update.message.reply_text(instrucoes)

async def receber_midia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Interceta vídeos e fotos e apresenta os botões de ação."""
    mensagem = update.message
    file_id = None
    file_type = None

    if mensagem.video:
        file_obj = mensagem.video
        file_type = 'video'
    elif mensagem.document and mensagem.document.mime_type and mensagem.document.mime_type.startswith('video/'):
        file_obj = mensagem.document
        file_type = 'video'
    elif mensagem.photo:
        file_obj = mensagem.photo[-1] # Obtém a maior resolução
        file_type = 'photo'
    else:
        return

    if getattr(file_obj, 'file_size', 0) > MAX_FILE_SIZE_MB * 1024 * 1024:
        await mensagem.reply_text(f"Erro restritivo: Ficheiro excede {MAX_FILE_SIZE_MB} MB.")
        return

    file_id = file_obj.file_id

    # Construção do Teclado Dinâmico
    teclado = []
    if file_type == 'video':
        teclado = [
            [InlineKeyboardButton("Extrair Voz (Telegram Audio)", callback_data="processar_voz")],
            [InlineKeyboardButton("Criar Figurinha Animada (Arredondada)", callback_data="processar_sticker_video")]
        ]
    elif file_type == 'photo':
        teclado = [
            [InlineKeyboardButton("Criar Figurinha Estática (Arredondada)", callback_data="processar_sticker_foto")]
        ]

    reply_markup = InlineKeyboardMarkup(teclado)
    resposta = await mensagem.reply_text("Escolha a ação pretendida para este ficheiro:", reply_markup=reply_markup)
    
    # Armazena os dados vinculados ao ID da mensagem com os botões para evitar conflitos se o utilizador enviar vários ficheiros
    context.user_data[resposta.message_id] = {'file_id': file_id, 'file_type': file_type}

async def botao_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa o clique no botão e executa a conversão."""
    query = update.callback_query
    await query.answer() # Fecha o estado de "carregando" no botão do Telegram

    msg_id = query.message.message_id
    dados_ficheiro = context.user_data.get(msg_id)

    if not dados_ficheiro:
        await query.edit_message_text("Sessão expirada ou ficheiro perdido. Envie novamente.")
        return

    acao = query.data
    file_id = dados_ficheiro['file_id']
    
    await query.edit_message_text("A descarregar dados...")
    
    try:
        telegram_file = await context.bot.get_file(file_id)
        
        if acao == "processar_voz":
            await executar_conversao_voz(telegram_file, query)
        elif acao == "processar_sticker_video":
            await executar_sticker_video(telegram_file, query)
        elif acao == "processar_sticker_foto":
            await executar_sticker_foto(telegram_file, query)
            
    except Exception as e:
        logger.error(f"Erro no processamento principal: {e}")
        await query.edit_message_text("Exceção técnica durante a operação.")
    finally:
        # Limpa a memória após o uso
        if msg_id in context.user_data:
            del context.user_data[msg_id]

async def executar_conversao_voz(telegram_file, query):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video, \
         tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_audio:
        video_path = temp_video.name
        audio_path = temp_audio.name

    try:
        await telegram_file.download_to_drive(video_path)
        await query.edit_message_text("A processar FFmpeg (Voz)...")

        comando = ["ffmpeg", "-y", "-i", video_path, "-t", str(MAX_DURATION_SEC), "-vn", "-c:a", "libopus", "-b:a", "32k", audio_path]
        subprocess.run(comando, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        await query.edit_message_text("A transmitir...")
        with open(audio_path, 'rb') as audio_file:
            await query.message.reply_voice(voice=audio_file)
        await query.message.delete()
    finally:
        for p in [video_path, audio_path]:
            if os.path.exists(p): os.remove(p)

async def executar_sticker_video(telegram_file, query):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video, \
         tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_mask, \
         tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_sticker:
        
        video_path = temp_video.name
        mask_path = temp_mask.name
        sticker_path = temp_sticker.name

    try:
        await telegram_file.download_to_drive(video_path)
        await query.edit_message_text("A gerar máscara geométrica e a codificar VP9 (Pode demorar)...")

        # Cria a máscara estática de cantos arredondados usando Pillow
        mascara = criar_mascara_arredondada((512, 512), 60)
        mascara.save(mask_path, "PNG")

        # Comando FFmpeg: Corta o vídeo para 512x512, aplica a máscara como canal Alpha e converte para WEBM VP9 (Máx 3 segundos)
        comando = [
            "ffmpeg", "-y", 
            "-i", video_path, 
            "-i", mask_path, 
            "-filter_complex", "[0:v]scale=512:512:force_original_aspect_ratio=increase,crop=512:512[v];[v][1:v]alphamerge", 
            "-c:v", "libvpx-vp9", 
            "-t", "3", 
            "-an", 
            "-auto-alt-ref", "0",
            sticker_path
        ]
        subprocess.run(comando, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # O Telegram exige um arquivo estrito de Sticker
        await query.edit_message_text("A transmitir figurinha animada...")
        with open(sticker_path, 'rb') as sticker_file:
            await query.message.reply_sticker(sticker=sticker_file)
        await query.message.delete()
    finally:
        for p in [video_path, mask_path, sticker_path]:
            if os.path.exists(p): os.remove(p)

async def executar_sticker_foto(telegram_file, query):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_input, \
         tempfile.NamedTemporaryFile(delete=False, suffix=".webp") as temp_output:
        input_path = temp_input.name
        output_path = temp_output.name

    try:
        await telegram_file.download_to_drive(input_path)
        await query.edit_message_text("A processar imagem (Pillow)...")

        # Lógica de manipulação de imagem
        img = Image.open(input_path).convert("RGBA")
        img = ImageOps.fit(img, (512, 512), method=Image.Resampling.LANCZOS)
        mascara = criar_mascara_arredondada((512, 512), 60)
        img.putalpha(mascara)
        img.save(output_path, "WEBP", quality=90)

        await query.edit_message_text("A transmitir figurinha estática...")
        with open(output_path, 'rb') as sticker_file:
            await query.message.reply_sticker(sticker=sticker_file)
        await query.message.delete()
    finally:
        for p in [input_path, output_path]:
            if os.path.exists(p): os.remove(p)

def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN ausente.")
        sys.exit(1)

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    # Escuta vídeos, documentos de vídeo e fotos
    application.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO | filters.PHOTO, receber_midia))
    
    # Escuta os cliques nos botões
    application.add_handler(CallbackQueryHandler(botao_callback))

    logger.info("Sistema ativo.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
