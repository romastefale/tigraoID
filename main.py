import os
import tempfile
import subprocess
from pathlib import Path

import telebot
from telebot import types

# VARIÁVEL DE AMBIENTE
TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    raise ValueError("Defina a variável de ambiente TELEGRAM_TOKEN")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# Armazenamento simples em memória
user_data = {}

def init_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "musica": None,
            "album": None,
            "artista": None,
            "capa": None,
            "modo": None,
        }

def reset_flow(chat_id):
    try:
        bot.clear_step_handler_by_chat_id(chat_id)
    except Exception:
        pass

def safe_text(value):
    return value if value else ""

# 🔥 INTERCEPTA /start EM QUALQUER MOMENTO
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    init_user(user_id)

    reset_flow(message.chat.id)

    user_data[user_id]["modo"] = "musica"
    user_data[user_id]["musica"] = None
    user_data[user_id]["album"] = None
    user_data[user_id]["artista"] = None
    user_data[user_id]["capa"] = None

    bot.send_message(
        message.chat.id,
        "🎶 <b>Esse é o feito pelo @tigrao para você mostrar aquela TRACK ID que não tem em lugar nenhum!</b>\n"
        "📝 <i>Só mandar os dados que deixo pronto para você enviar...</i>"
    )

    ask_musica(message.chat.id)

# 🔁 /convert: vídeo -> áudio como voice note
@bot.message_handler(commands=["convert"])
def convert(message):
    user_id = message.from_user.id
    init_user(user_id)

    reset_flow(message.chat.id)
    user_data[user_id]["modo"] = "convert"

    bot.send_message(
        message.chat.id,
        "📹 <b>Envie um vídeo</b> para eu converter em áudio de voz (OGG/OPUS)."
    )
    msg = bot.send_message(message.chat.id, "Aguardando o vídeo...")
    bot.register_next_step_handler(msg, get_video_convert)

def get_video_convert(message):
    user_id = message.from_user.id
    init_user(user_id)

    file_id = None
    if message.video:
        file_id = message.video.file_id
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("video/"):
        file_id = message.document.file_id
    elif message.animation:
        file_id = message.animation.file_id
    else:
        bot.send_message(message.chat.id, "Envie um vídeo válido.")
        ask_video_convert(message.chat.id)
        return

    try:
        file_info = bot.get_file(file_id)
        downloaded = bot.download_file(file_info.file_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            input_path = tmpdir / "input_video"
            output_path = tmpdir / "voice_note.ogg"

            input_path.write_bytes(downloaded)

            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(input_path),
                "-vn",
                "-ac", "1",
                "-c:a", "libopus",
                "-b:a", "48k",
                "-f", "ogg",
                str(output_path),
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if result.returncode != 0 or not output_path.exists():
                error_text = result.stderr[-1000:] if result.stderr else "erro desconhecido"
                bot.send_message(message.chat.id, f"Falha ao converter o vídeo em áudio.\n\n<code>{error_text}</code>")
                return

            with open(output_path, "rb") as audio:
                bot.send_voice(message.chat.id, audio, caption="✅ Áudio convertido.")

    except FileNotFoundError:
        bot.send_message(
            message.chat.id,
            "FFmpeg não encontrado no servidor. Adicione o FFmpeg no deploy do Railway."
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"Erro na conversão: <code>{e}</code>")

def ask_video_convert(chat_id):
    reset_flow(chat_id)
    msg = bot.send_message(chat_id, "📹 Envie o vídeo que você quer converter em áudio.")
    bot.register_next_step_handler(msg, get_video_convert)

# 🎧 Música (AGORA ACEITA LINK DO TELEGRAM)
def ask_musica(chat_id):
    reset_flow(chat_id)
    msg = bot.send_message(chat_id, "🎧 Música?")
    bot.register_next_step_handler(msg, get_musica)

def get_musica(message):
    text = message.text or ""

    # Converte links formatados do Telegram para HTML quando necessário
    if message.entities:
        new_text = ""
        last_index = 0
        for entity in message.entities:
            if entity.offset > last_index:
                new_text += text[last_index:entity.offset]

            chunk = text[entity.offset:entity.offset + entity.length]
            if entity.type == "text_link" and getattr(entity, "url", None):
                new_text += f'<a href="{entity.url}">{chunk}</a>'
            else:
                new_text += chunk

            last_index = entity.offset + entity.length

        new_text += text[last_index:]
        text = new_text

    init_user(message.from_user.id)
    user_data[message.from_user.id]["musica"] = text.strip()
    ask_album(message.chat.id)

# 🎹 Álbum
def ask_album(chat_id):
    reset_flow(chat_id)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❎", callback_data="skip_album"))

    msg = bot.send_message(chat_id, "🎹 Album?", reply_markup=markup)
    bot.register_next_step_handler(msg, get_album)

def get_album(message):
    init_user(message.from_user.id)
    user_data[message.from_user.id]["album"] = safe_text(message.text).strip() or None
    ask_artista(message.chat.id)

# 🙍 Artista
def ask_artista(chat_id):
    reset_flow(chat_id)
    msg = bot.send_message(chat_id, "🙍 Artista?")
    bot.register_next_step_handler(msg, get_artista)

def get_artista(message):
    init_user(message.from_user.id)
    user_data[message.from_user.id]["artista"] = safe_text(message.text).strip() or None
    ask_capa(message.chat.id)

# 📸 Capa (ACEITA FOTO, VÍDEO OU GIF/VÍDEO MUDO)
def ask_capa(chat_id):
    reset_flow(chat_id)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❎", callback_data="skip_capa"))

    msg = bot.send_message(chat_id, "📸 Envie a capa (imagem, vídeo ou GIF)?", reply_markup=markup)
    bot.register_next_step_handler(msg, get_capa)

def get_capa(message):
    init_user(message.from_user.id)

    if message.photo:
        file_id = message.photo[-1].file_id
        user_data[message.from_user.id]["capa"] = ("photo", file_id)
        gerar_preview(message)

    elif message.video:
        file_id = message.video.file_id
        user_data[message.from_user.id]["capa"] = ("video", file_id)
        gerar_preview(message)

    elif message.animation:
        file_id = message.animation.file_id
        user_data[message.from_user.id]["capa"] = ("animation", file_id)
        gerar_preview(message)

    else:
        ask_capa(message.chat.id)

# CALLBACKS
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    init_user(user_id)
    reset_flow(chat_id)

    if call.data == "skip_album":
        user_data[user_id]["album"] = None
        ask_artista(chat_id)

    elif call.data == "skip_capa":
        user_data[user_id]["capa"] = None
        gerar_preview(call.message)

    elif call.data == "confirmar":
        bot.send_message(chat_id, "🪗🎷🎼 Muito obrigado! quiser outra música mande /start")

    elif call.data == "editar":
        editar_menu(chat_id)

    elif call.data == "edit_musica":
        ask_musica(chat_id)

    elif call.data == "edit_album":
        ask_album(chat_id)

    elif call.data == "edit_artista":
        ask_artista(chat_id)

    bot.answer_callback_query(call.id)

# PREVIEW
def gerar_preview(message):
    user_id = message.from_user.id
    init_user(user_id)
    data = user_data[user_id]

    user = message.from_user.first_name or "Usuário"
    musica = data.get("musica") or "Sem música"

    album = f"- {data['album']}" if data.get("album") else ""
    artista = f"— {data['artista']}" if data.get("artista") else ""

    texto = (
        f"🎹<b>{user}</b> está ouvindo...\n\n"
        f"🎧<b>{musica}</b> "
        f"<i>{album} {artista}</i>"
    ).strip()

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✔️ Sim", callback_data="confirmar"),
        types.InlineKeyboardButton("✖️ Não", callback_data="editar"),
    )

    if data.get("capa"):
        tipo, file_id = data["capa"]

        if tipo == "photo":
            bot.send_photo(message.chat.id, file_id, caption=texto, reply_markup=markup)

        elif tipo == "video":
            bot.send_video(message.chat.id, file_id, caption=texto, reply_markup=markup)

        elif tipo == "animation":
            bot.send_animation(message.chat.id, file_id, caption=texto, reply_markup=markup)

    else:
        bot.send_message(message.chat.id, texto, reply_markup=markup)

# EDITAR
def editar_menu(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🎧 Música?", callback_data="edit_musica"),
        types.InlineKeyboardButton("🎹 Album?", callback_data="edit_album"),
        types.InlineKeyboardButton("🙍 Artista?", callback_data="edit_artista"),
    )

    bot.send_message(chat_id, "🔊 O que deseja corrigir?", reply_markup=markup)

# START
if __name__ == "__main__":
    bot.infinity_polling()
