import os
import sys
import subprocess
import tempfile
import logging
import io
import math
import asyncio
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
MAX_FILA = 100
DEBOUNCE_SEC = 1.0
PAUSA_ENTRE_ITENS = 0.4

MENU_ACAO, MENU_PACOTE, NOVO_TITULO, NOVO_NOME, NOVO_EMOJI, ADD_EMOJI, ADD_NOME = range(7)
MEDIA_FILTER = filters.VIDEO | filters.Document.VIDEO | filters.PHOTO

SQUIRCLE_N = 5.0

_debounce = {}


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


def cancelar_debounce(user_id: int) -> None:
    tarefa = _debounce.pop(user_id, None)
    if tarefa and not tarefa.done():
        tarefa.cancel()


def extrair_item(mensagem):
    if mensagem.video:
        file_obj, ftype = mensagem.video, "video"
    elif mensagem.document and mensagem.document.mime_type and mensagem.document.mime_type.startswith("video/"):
        file_obj, ftype = mensagem.document, "video"
    elif mensagem.photo:
        file_obj, ftype = mensagem.photo[-1], "photo"
    else:
        return None
    return {
        "file_id": file_obj.file_id,
        "ftype": ftype,
        "message_id": mensagem.message_id,
        "file_size": getattr(file_obj, "file_size", 0) or 0,
    }


def enfileirar_item(context, item) -> str:
    fila = context.user_data.setdefault("fila", [])
    if any(x["message_id"] == item["message_id"] for x in fila):
        return "dup"
    if item["file_size"] > MAX_FILE_SIZE_MB * 1024 * 1024:
        return "size"
    if len(fila) >= MAX_FILA:
        return "full"
    fila.append(item)
    fila.sort(key=lambda x: x["message_id"])
    context.user_data["fila"] = fila
    return "ok"


def teclado_acao(fila):
    tem_video = any(i["ftype"] == "video" for i in fila)
    tem_foto = any(i["ftype"] == "photo" for i in fila)
    rows = []
    if tem_video:
        rows.append([InlineKeyboardButton("Extrair Voz (Nativo Telegram)", callback_data="voz")])
        rows.append([InlineKeyboardButton("Extrair Áudio (Para WhatsApp / M4A)", callback_data="audio_whatsapp")])
    if tem_video and tem_foto:
        rows.append([InlineKeyboardButton("Criar Figurinhas (um a um)", callback_data="sticker_fila")])
    elif tem_video:
        rows.append([InlineKeyboardButton("Criar Figurinha Animada", callback_data="sticker_video")])
    else:
        rows.append([InlineKeyboardButton("Criar Figurinha Estática", callback_data="sticker_foto")])
    return InlineKeyboardMarkup(rows)


def texto_menu_fila(fila) -> str:
    n = len(fila)
    return (
        f"{n} arquivo(s) na fila, em ordem cronológica (máx. {MAX_FILA}).\n"
        "Escolha a ação — a fila será executada um a um:"
    )


async def mostrar_menu_acao(context, chat_id: int) -> None:
    if context.user_data.get("acao"):
        return
    fila = context.user_data.get("fila") or []
    if not fila:
        return
    text = texto_menu_fila(fila)
    markup = teclado_acao(fila)
    mid = context.user_data.get("menu_msg_id")
    if mid:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=mid, text=text, reply_markup=markup
            )
            return
        except Exception:
            pass
    msg = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    context.user_data["menu_msg_id"] = msg.message_id


async def agendar_menu_acao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    chat_id = update.effective_chat.id
    cancelar_debounce(uid)

    async def later():
        try:
            await asyncio.sleep(DEBOUNCE_SEC)
            await mostrar_menu_acao(context, chat_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Falha ao mostrar menu da fila")

    _debounce[uid] = asyncio.create_task(later())


async def avisar_fila(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    n = len(context.user_data.get("fila") or [])
    if n <= 0:
        return
    await update.effective_chat.send_message(f"Na fila: {n}/{MAX_FILA} (ordem cronológica, um a um).")


async def aceitar_midia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    item = extrair_item(update.message)
    if not item:
        return MENU_ACAO

    reason = enfileirar_item(context, item)
    if reason == "size":
        await update.message.reply_text(f"Ficheiro ignorado: excede {MAX_FILE_SIZE_MB} MB.")
        if context.user_data.get("fila"):
            await agendar_menu_acao(update, context)
            return MENU_ACAO
        return ConversationHandler.END
    if reason == "full":
        if not context.user_data.get("fila_cheia_avisada"):
            context.user_data["fila_cheia_avisada"] = True
            await update.message.reply_text(f"Fila cheia ({MAX_FILA}). Os extras foram ignorados.")
        if context.user_data.get("fila"):
            return MENU_ACAO
        return ConversationHandler.END
    if reason == "dup":
        return MENU_ACAO

    if not context.user_data.get("menu_msg_id"):
        msg = await update.message.reply_text("A receber arquivos…")
        context.user_data["menu_msg_id"] = msg.message_id

    await agendar_menu_acao(update, context)
    return MENU_ACAO


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cancelar_debounce(update.effective_user.id)
    context.user_data.clear()
    await update.message.reply_text(
        "Envie vídeo ou foto para iniciar. Pode mandar vários de uma vez "
        f"(álbum ou um atrás do outro), até {MAX_FILA}, na ordem em que chegarem.\n"
        "A fila executa um a um. Envie /cancelar a qualquer momento para abortar."
    )
    return ConversationHandler.END


async def repetir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    partes = update.message.text.split(" ", 1)
    if len(partes) > 1:
        mensagem = partes[1]
        await context.bot.send_message(chat_id=update.effective_chat.id, text=mensagem)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Formato incorreto. Uso: /repetir <sua mensagem>")


async def receber_midia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cancelar_debounce(update.effective_user.id)
    context.user_data.clear()
    context.user_data["fila"] = []
    return await aceitar_midia(update, context)


async def enfileirar_durante(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item = extrair_item(update.message)
    if not item:
        return None

    reason = enfileirar_item(context, item)
    if reason == "size":
        await update.message.reply_text(f"Ficheiro ignorado: excede {MAX_FILE_SIZE_MB} MB.")
    elif reason == "full":
        if not context.user_data.get("fila_cheia_avisada"):
            context.user_data["fila_cheia_avisada"] = True
            await update.message.reply_text(f"Fila cheia ({MAX_FILA}). Os extras foram ignorados.")
    elif reason == "ok" and not context.user_data.get("acao"):
        await agendar_menu_acao(update, context)
    elif reason == "ok" and context.user_data.get("acao"):
        n = len(context.user_data.get("fila") or [])
        if n == 1 or n % 10 == 0 or n == MAX_FILA:
            await avisar_fila(update, context)
    return None


async def converter_sticker(context, item) -> tuple[bytes, str]:
    telegram_file = await context.bot.get_file(item["file_id"])
    if item["ftype"] == "video":
        dados = await executar_sticker_video(telegram_file)
        return dados, StickerFormat.VIDEO
    dados = await executar_sticker_foto(telegram_file)
    return dados, StickerFormat.STATIC


async def processar_acao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    cancelar_debounce(query.from_user.id)
    acao = query.data
    fila = context.user_data.get("fila") or []

    if not fila:
        await query.edit_message_text("Fila vazia. Envie o ficheiro novamente.")
        return ConversationHandler.END

    context.user_data["acao"] = acao
    total = len(fila)

    try:
        if acao in ("voz", "audio_whatsapp"):
            plataforma = "telegram" if acao == "voz" else "whatsapp"
            await query.edit_message_text(f"A processar a fila de áudio (1/{total})…")
            await processar_fila_audio(query.message, context, plataforma)
            context.user_data.clear()
            return ConversationHandler.END

        atual = fila.pop(0)
        context.user_data["fila"] = fila
        await query.edit_message_text(f"A processar 1/{total}…")
        dados, fmt = await converter_sticker(context, atual)
        context.user_data["sticker_bytes"] = dados
        context.user_data["sticker_format"] = fmt
        context.user_data["total_lote"] = total

        resto = len(fila)
        extra = f" Restam {resto} na fila — entram no mesmo pacote, um a um." if resto else ""
        teclado = [
            [InlineKeyboardButton("Criar Novo Pacote", callback_data="pacote_novo")],
            [InlineKeyboardButton("Adicionar a Pacote Existente", callback_data="pacote_add")],
        ]
        await query.edit_message_text(
            f"Figurinha 1/{total} pronta.{extra}\nOnde deseja guardar?",
            reply_markup=InlineKeyboardMarkup(teclado),
        )
        return MENU_PACOTE

    except Exception as e:
        logger.error(f"Erro: {e}")
        await query.edit_message_text("Falha de processamento.")
        context.user_data.clear()
        return ConversationHandler.END


async def processar_fila_audio(dest_message, context, plataforma) -> None:
    fila = list(context.user_data.get("fila") or [])
    total = len(fila)
    ok = fail = skip = 0
    for i, item in enumerate(fila, 1):
        try:
            await dest_message.edit_text(f"A processar {i}/{total}…")
        except Exception:
            pass
        if item["ftype"] != "video":
            skip += 1
            continue
        try:
            telegram_file = await context.bot.get_file(item["file_id"])
            await executar_conversao_voz(telegram_file, dest_message, plataforma)
            ok += 1
        except Exception as e:
            logger.error(f"Áudio item {i}: {e}")
            fail += 1
        await asyncio.sleep(PAUSA_ENTRE_ITENS)
    partes = [f"{ok} ok"]
    if skip:
        partes.append(f"{skip} foto(s) ignorada(s)")
    if fail:
        partes.append(f"{fail} falha(s)")
    await dest_message.reply_text("Fila de áudio concluída: " + ", ".join(partes) + ".")


async def drenar_fila_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pack_name = context.user_data["pack_name"]
    emoji = context.user_data["pack_emoji"]
    user_id = update.effective_user.id
    ok = 1
    fail = 0
    n = 1
    status = await update.message.reply_text("A processar o resto da fila…")
    while context.user_data.get("fila"):
        item = context.user_data["fila"].pop(0)
        n += 1
        rest = len(context.user_data.get("fila") or [])
        try:
            await status.edit_text(f"A processar figurinha {n} ({rest} à espera)…")
        except Exception:
            pass
        try:
            dados, fmt = await converter_sticker(context, item)
            await context.bot.add_sticker_to_set(
                user_id=user_id,
                name=pack_name,
                sticker=InputSticker(dados, emoji_list=[emoji], format=fmt),
            )
            ok += 1
        except Exception as e:
            logger.error(f"Sticker item {n}: {e}")
            fail += 1
        await asyncio.sleep(PAUSA_ENTRE_ITENS)
    resumo = f"Fila concluída: {ok} ok"
    if fail:
        resumo += f", {fail} falha(s)"
    await status.edit_text(f"{resumo}.\n t.me/addstickers/{pack_name}")


async def executar_conversao_voz(telegram_file, dest_message, plataforma):
    if plataforma == "telegram":
        extensao = ".ogg"
        parametros_ffmpeg = ["-c:a", "libopus", "-b:a", "32k"]
    else:
        extensao = ".m4a"
        parametros_ffmpeg = ["-c:a", "aac", "-b:a", "128k"]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tv, tempfile.NamedTemporaryFile(delete=False, suffix=extensao) as ta:
        v_path, a_path = tv.name, ta.name

    try:
        await telegram_file.download_to_drive(v_path)
        comando = ["ffmpeg", "-y", "-i", v_path, "-t", str(MAX_DURATION_SEC), "-vn"] + parametros_ffmpeg + [a_path]
        subprocess.run(comando, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with open(a_path, "rb") as f:
            if plataforma == "telegram":
                await dest_message.reply_voice(voice=f)
            else:
                await dest_message.reply_audio(audio=f, title="Áudio Extraído", performer="Bot")
    finally:
        for p in [v_path, a_path]:
            if os.path.exists(p):
                os.remove(p)


async def executar_sticker_video(telegram_file) -> bytes:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tv, tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tm, tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as ts:
        v_path, m_path, s_path = tv.name, tm.name, ts.name
    try:
        await telegram_file.download_to_drive(v_path)
        criar_mascara_arredondada((512, 512), 60).save(m_path, "PNG")
        subprocess.run(["ffmpeg", "-y", "-i", v_path, "-i", m_path, "-filter_complex", "[0:v]scale=512:512:force_original_aspect_ratio=increase,crop=512:512[v];[v][1:v]alphamerge", "-c:v", "libvpx-vp9", "-t", "3", "-an", "-auto-alt-ref", "0", s_path], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(s_path, "rb") as f:
            return f.read()
    finally:
        for p in [v_path, m_path, s_path]:
            if os.path.exists(p):
                os.remove(p)


async def executar_sticker_foto(telegram_file) -> bytes:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as ti, tempfile.NamedTemporaryFile(delete=False, suffix=".webp") as to:
        i_path, o_path = ti.name, to.name
    try:
        await telegram_file.download_to_drive(i_path)
        img = ImageOps.fit(Image.open(i_path).convert("RGBA"), (512, 512), method=Image.Resampling.LANCZOS)
        img.putalpha(criar_mascara_arredondada((512, 512), 60))
        img.save(o_path, "WEBP", quality=90)
        with open(o_path, "rb") as f:
            return f.read()
    finally:
        for p in [i_path, o_path]:
            if os.path.exists(p):
                os.remove(p)


async def escolha_pacote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    resto = len(context.user_data.get("fila") or [])
    nota_emoji = " Este emoji vale para todas as figurinhas da fila." if resto else ""
    if query.data == "pacote_novo":
        await query.edit_message_text("Digite o TÍTULO do novo pacote (O nome visível na galeria):")
        return NOVO_TITULO
    await query.edit_message_text(f"Envie UM EMOJI para vincular.{nota_emoji}")
    return ADD_EMOJI


async def novo_titulo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["pack_title"] = update.message.text
    bot_info = await context.bot.get_me()
    await update.message.reply_text(f"Digite o NOME CURTO do pacote (usado na URL). O sistema adicionará automaticamente '_by_{bot_info.username}' ao final.")
    return NOVO_NOME


async def novo_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    bot_info = await context.bot.get_me()
    nome_curto = update.message.text.replace(" ", "_")
    nome_final = f"{nome_curto}_by_{bot_info.username}"
    context.user_data["pack_name"] = nome_final
    resto = len(context.user_data.get("fila") or [])
    nota = " Ele será usado em todas as da fila." if resto else ""
    await update.message.reply_text(f"O identificador será {nome_final}.\nAgora, envie UM EMOJI para vincular.{nota}")
    return NOVO_EMOJI


async def concluir_novo_pacote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    emoji = update.message.text
    context.user_data["pack_emoji"] = emoji
    user_id = update.effective_user.id
    try:
        await context.bot.create_new_sticker_set(
            user_id=user_id,
            name=context.user_data["pack_name"],
            title=context.user_data["pack_title"],
            stickers=[InputSticker(context.user_data["sticker_bytes"], emoji_list=[emoji], format=context.user_data["sticker_format"])],
        )
    except Exception as e:
        await update.message.reply_text(f"Falha na API do Telegram: {e}")
        context.user_data.clear()
        return ConversationHandler.END

    if context.user_data.get("fila"):
        await drenar_fila_stickers(update, context)
    else:
        await update.message.reply_text(f"Pacote criado! Aceda aqui: t.me/addstickers/{context.user_data['pack_name']}")
    context.user_data.clear()
    return ConversationHandler.END


async def add_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["pack_emoji"] = update.message.text
    bot_info = await context.bot.get_me()
    await update.message.reply_text(f"Digite o NOME CURTO do pacote existente (deve terminar em _by_{bot_info.username}):")
    return ADD_NOME


async def concluir_add_pacote(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    nome_pacote = update.message.text
    context.user_data["pack_name"] = nome_pacote
    user_id = update.effective_user.id
    try:
        await context.bot.add_sticker_to_set(
            user_id=user_id,
            name=nome_pacote,
            sticker=InputSticker(context.user_data["sticker_bytes"], emoji_list=[context.user_data["pack_emoji"]], format=context.user_data["sticker_format"]),
        )
    except Exception as e:
        await update.message.reply_text(f"Falha na API: {e}\nNota: O bot só pode adicionar a pacotes que ele próprio criou.")
        context.user_data.clear()
        return ConversationHandler.END

    if context.user_data.get("fila"):
        await drenar_fila_stickers(update, context)
    else:
        await update.message.reply_text(f"Figurinha adicionada ao pacote {nome_pacote} com sucesso.")
    context.user_data.clear()
    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cancelar_debounce(update.effective_user.id)
    n = len(context.user_data.get("fila") or [])
    extra = f" Fila de {n} arquivo(s) descartada." if n else ""
    await update.message.reply_text("Operação abortada." + extra)
    context.user_data.clear()
    return ConversationHandler.END


def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN ausente.")
        sys.exit(1)

    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(MEDIA_FILTER, receber_midia)],
        states={
            MENU_ACAO: [
                CallbackQueryHandler(processar_acao),
                MessageHandler(MEDIA_FILTER, enfileirar_durante),
            ],
            MENU_PACOTE: [
                CallbackQueryHandler(escolha_pacote),
                MessageHandler(MEDIA_FILTER, enfileirar_durante),
            ],
            NOVO_TITULO: [
                MessageHandler(MEDIA_FILTER, enfileirar_durante),
                MessageHandler(filters.TEXT & ~filters.COMMAND, novo_titulo),
            ],
            NOVO_NOME: [
                MessageHandler(MEDIA_FILTER, enfileirar_durante),
                MessageHandler(filters.TEXT & ~filters.COMMAND, novo_nome),
            ],
            NOVO_EMOJI: [
                MessageHandler(MEDIA_FILTER, enfileirar_durante),
                MessageHandler(filters.TEXT & ~filters.COMMAND, concluir_novo_pacote),
            ],
            ADD_EMOJI: [
                MessageHandler(MEDIA_FILTER, enfileirar_durante),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_emoji),
            ],
            ADD_NOME: [
                MessageHandler(MEDIA_FILTER, enfileirar_durante),
                MessageHandler(filters.TEXT & ~filters.COMMAND, concluir_add_pacote),
            ],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        per_message=False,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("repetir", repetir))
    application.add_handler(conv_handler)

    logger.info("Sistema ativo de processamento de media e pacotes.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
