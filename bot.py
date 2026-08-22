import os
import sys
import subprocess
import tempfile
import logging
import io
import math
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputSticker
from telegram.constants import StickerFormat
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from PIL import Image, ImageOps, ImageDraw

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
MAX_FILE_SIZE_MB = 20
MAX_DURATION_SEC = 120

MENU_ACAO, MENU_PACOTE, NOVO_TITULO, NOVO_NOME, NOVO_EMOJI, ADD_EMOJI, ADD_NOME = range(7)

# Superelipse n=5 ≈ squircle iOS — o shape da moldura enviado para a branch rounded.
SQUIRCLE_N = 5.0


def criar_mascara_arredondada(tamanho, raio=None):
    """Máscara squircle (superelipse n=5): cantos contínuos, sem o raio fixo do rounded_rectangle."""
    largura, altura = tamanho
    expoente = 2.0 / SQUIRCLE_N
    escala = 4
    sw, sh = largura * escala, altura * escala
    mascara = Image.new("L", (sw, sh), 0)
    draw = ImageDraw.Draw(mascara)
    cx = (sw - 1) / 2.0
    cy = (sh - 1) / 2.0
    ax = sw / 2.0
    ay = sh / 2.0
    pontos = []
    passos = 512
    for i in range(passos):
        theta = (2.0 * math.pi * i) / passos
        cosseno = math.cos(theta)
        seno = math.sin(theta)
        x = cx + ax * math.copysign(abs(cosseno) ** expoente, cosseno)
        y = cy + ay * math.copysign(abs(seno) ** expoente, seno)
        pontos.append((x, y))
    draw.polygon(pontos, fill=255)
    return mascara.resize((largura, altura), Image.Resampling.LANCZOS)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Envie um vídeo ou foto para iniciar a extração ou criação de pacote. Envie /cancelar a qualquer momento para abortar.")
    return MENU_ACAO

async def repetir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    partes = update.message.text.split(' ', 1)
    if len(partes) > 1:
        mensagem = partes[1]
        await context.bot.send_message(chat_id=update.effective_chat.id, text=mensagem)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Formato incorreto. Uso: /repetir <sua mensagem>")

async def receber_midia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    mensagem = update.message
    if mensagem.video: file_obj, ftype = mensagem.video, 'video'
    elif mensagem.document and mensagem.document.mime_type and mensagem.document.mime_type.startswith('video/'):
        file_obj, ftype = mensagem.document, 'video'
    elif mensagem.photo: file_obj, ftype = mensagem.photo[-1], 'photo'
    else: return MENU_ACAO

    if getattr(file_obj, 'file_size', 0) > MAX_FILE_SIZE_MB * 1024 * 1024:
        await mensagem.reply_text(f"Limite excedido ({MAX_FILE_SIZE_MB} MB).")
        return MENU_ACAO

    context.user_data['file_id'] = file_obj.file_id
    
    if ftype == 'video':
        teclado = [
            [InlineKeyboardButton("Extrair Voz (Nativo Telegram)", callback_data="voz")],
            [InlineKeyboardButton("Extrair Áudio (Para WhatsApp / M4A)", callback_data="audio_whatsapp")],
            [InlineKeyboardButton("Criar Figurinha Animada", callback_data="sticker_video")]
        ]
    else:
        teclado = [[InlineKeyboardButton("Criar Figurinha Estática", callback_data="sticker_foto")]]

    await mensagem.reply_text("Escolha a ação de processamento:", reply_markup=InlineKeyboardMarkup(teclado))
    return MENU_ACAO

async def processar_acao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    acao = query.data
    file_id = context.user_data.get('file_id')

    if not file_id:
        await query.edit_message_text("Falha de memória. Envie o ficheiro novamente.")
        return ConversationHandler.END

    telegram_file = await context.bot.get_file(file_id)
    await query.edit_message_text("A processar ficheiro no servidor...")

    try:
        if acao == "voz":
            await executar_conversao_voz(telegram_file, query, "telegram")
            context.user_data.clear()
            return ConversationHandler.END
        elif acao == "audio_whatsapp":
            await executar_conversao_voz(telegram_file, query, "whatsapp")
            context.user_data.clear()
            return ConversationHandler.END
        elif acao == "sticker_video":
            dados_sticker = await executar_sticker_video(telegram_file, query)
            context.user_data['sticker_bytes'] = dados_sticker
            context.user_data['sticker_format'] = StickerFormat.VIDEO
        elif acao == "sticker_foto":
            dados_sticker = await executar_sticker_foto(telegram_file, query)
            context.user_data['sticker_bytes'] = dados_sticker
            context.user_data['sticker_format'] = StickerFormat.STATIC

        teclado = [
            [InlineKeyboardButton("Criar Novo Pacote", callback_data="pacote_novo")],
            [InlineKeyboardButton("Adicionar a Pacote Existente", callback_data="pacote_add")]
        ]
        await query.edit_message_text("Processamento de figurinha concluído. Onde deseja guardar?", reply_markup=InlineKeyboardMarkup(teclado))
        return MENU_PACOTE

    except Exception as e:
        logger.error(f"Erro: {e}")
        await query.edit_message_text("Falha de processamento.")
        context.user_data.clear()
        return ConversationHandler.END

async def executar_conversao_voz(telegram_file, query, plataforma):
    if plataforma == "telegram":
        extensao = ".ogg"
        parametros_ffmpeg = ["-c:a", "libopus", "-b:a", "32k"]
    else:
        extensao = ".m4a"
        parametros_ffmpeg = ["-c:a", "aac", "-b:a", "128k"]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tv,          tempfile.NamedTemporaryFile(delete=False, suffix=extensao) as ta:
        v_path, a_path = tv.name, ta.name
        
    try:
        await telegram_file.download_to_drive(v_path)
        comando = ["ffmpeg", "-y", "-i", v_path, "-t", str(MAX_DURATION_SEC), "-vn"] + parametros_ffmpeg + [a_path]
        subprocess.run(comando, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        with open(a_path, 'rb') as f:
            if plataforma == "telegram":
                await query.message.reply_voice(voice=f)
            else:
                await query.message.reply_audio(audio=f, title="Áudio Extraído", performer="Bot")
    finally:
        for p in [v_path, a_path]:
            if os.path.exists(p): os.remove(p)

async def executar_sticker_video(telegram_file, query) -> bytes:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tv, tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tm, tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as ts:
        v_path, m_path, s_path = tv.name, tm.name, ts.name
    try:
        await telegram_file.download_to_drive(v_path)
        criar_mascara_arredondada((512, 512), 60).save(m_path, "PNG")
        subprocess.run(["ffmpeg", "-y", "-i", v_path, "-i", m_path, "-filter_complex", "[0:v]scale=512:512:force_original_aspect_ratio=increase,crop=512:512[v];[v][1:v]alphamerge", "-c:v", "libvpx-vp9", "-t", "3", "-an", "-auto-alt-ref", "0", s_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(s_path, 'rb') as f: return f.read()
    finally:
        for p in [v_path, m_path, s_path]:
            if os.path.exists(p): os.remove(p)

async def executar_sticker_foto(telegram_file, query) -> bytes:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as ti, tempfile.NamedTemporaryFile(delete=False, suffix=".webp") as to:
        i_path, o_path = ti.name, to.name
    try:
        await telegram_file.download_to_drive(i_path)
        img = ImageOps.fit(Image.open(i_path).convert("RGBA"), (512, 512), method=Image.Resampling.LANCZOS)
        img.putalpha(criar_mascara_arredondada((512, 512), 60))
        img.save(o_path, "WEBP", quality=90)
        with open(o_path, 'rb') as f: return f.read()
    finally:
        for p in [i_path, o_path]:
            if os.path.exists(p): os.remove(p)

async def escolha_pacote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "pacote_novo":
        await query.edit_message_text("Digite o TÍTULO do novo pacote (O nome visível na galeria):")
        return NOVO_TITULO
    else:
        await query.edit_message_text("Envie UM EMOJI para vincular a esta figurinha:")
        return ADD_EMOJI

async def novo_titulo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['pack_title'] = update.message.text
    bot_info = await context.bot.get_me()
    await update.message.reply_text(f"Digite o NOME CURTO do pacote (usado na URL). O sistema adicionará automaticamente '_by_{bot_info.username}' ao final.")
    return NOVO_NOME

async def novo_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    bot_info = await context.bot.get_me()
    nome_curto = update.message.text.replace(" ", "_")
    nome_final = f"{nome_curto}_by_{bot_info.username}"
    context.user_data['pack_name'] = nome_final
    await update.message.reply_text(f"O identificador será {nome_final}.\nAgora, envie UM EMOJI para vincular a esta figurinha inicial:")
    return NOVO_EMOJI

async def concluir_novo_pacote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    emoji = update.message.text
    user_id = update.effective_user.id
    try:
        await context.bot.create_new_sticker_set(
            user_id=user_id,
            name=context.user_data['pack_name'],
            title=context.user_data['pack_title'],
            stickers=[InputSticker(context.user_data['sticker_bytes'], emoji_list=[emoji], format=context.user_data['sticker_format'])]
        )
        await update.message.reply_text(f"Pacote criado! Aceda aqui: t.me/addstickers/{context.user_data['pack_name']}")
    except Exception as e:
        await update.message.reply_text(f"Falha na API do Telegram: {e}")
    context.user_data.clear()
    return ConversationHandler.END

async def add_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['pack_emoji'] = update.message.text
    bot_info = await context.bot.get_me()
    await update.message.reply_text(f"Digite o NOME CURTO do pacote existente (deve terminar em _by_{bot_info.username}):")
    return ADD_NOME

async def concluir_add_pacote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nome_pacote = update.message.text
    user_id = update.effective_user.id
    try:
        await context.bot.add_sticker_to_set(
            user_id=user_id,
            name=nome_pacote,
            sticker=InputSticker(context.user_data['sticker_bytes'], emoji_list=[context.user_data['pack_emoji']], format=context.user_data['sticker_format'])
        )
        await update.message.reply_text(f"Figurinha adicionada ao pacote {nome_pacote} com sucesso.")
    except Exception as e:
        await update.message.reply_text(f"Falha na API: {e}\nNota: O bot só pode adicionar a pacotes que ele próprio criou.")
    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operação abortada.")
    context.user_data.clear()
    return ConversationHandler.END

def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN ausente.")
        sys.exit(1)

    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.VIDEO | filters.Document.VIDEO | filters.PHOTO, receber_midia)],
        states={
            MENU_ACAO: [CallbackQueryHandler(processar_acao)],
            MENU_PACOTE: [CallbackQueryHandler(escolha_pacote)],
            NOVO_TITULO: [MessageHandler(filters.TEXT & ~filters.COMMAND, novo_titulo)],
            NOVO_NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, novo_nome)],
            NOVO_EMOJI: [MessageHandler(filters.TEXT & ~filters.COMMAND, concluir_novo_pacote)],
            ADD_EMOJI: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_emoji)],
            ADD_NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, concluir_add_pacote)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        per_message=False
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("repetir", repetir))
    application.add_handler(conv_handler)

    logger.info("Sistema ativo de processamento de media e pacotes.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
