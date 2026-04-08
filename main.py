import os
import tempfile
import subprocess
from pathlib import Path

import telebot
from telebot import types

TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    raise ValueError("Defina a variável de ambiente TELEGRAM_TOKEN")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

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
    except:
        pass

def safe_text(value):
    return value if value else ""

# 🔥 START = RESET + APRESENTAÇÃO
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    init_user(user_id)

    reset_flow(message.chat.id)

    user_data[user_id] = {
        "musica": None,
        "album": None,
        "artista": None,
        "capa": None,
        "modo": None,
    }

    bot.send_message(
        message.chat.id,
        "🎧 <b>Fala! Eu sou o bot do @tigrao</b>\n\n"
        "Aqui você pode:\n"
        "• Criar <b>TRACK ID</b> de músicas que não existem no streaming\n"
        "• Converter vídeos em <b>áudio de voz</b> pra enviar pros amigos\n\n"
        "<b>Comandos disponíveis:</b>\n"
        "🎵 /trackid — Criar sua track\n"
        "🎙 /convert — Converter vídeo em áudio\n\n"
        "💡 Use /start a qualquer momento para recomeçar."
    )

# 🎵 TRACKID
@bot.message_handler(commands=["trackid"])
def trackid(message):
    user_id = message.from_user.id
    init_user(user_id)

    reset_flow(message.chat.id)
    user_data[user_id]["modo"] = "musica"

    bot.send_message(message.chat.id, "🎶 <b>Bora montar sua TRACK ID</b>\n\nMe manda o nome da música 👇")
    ask_musica(message.chat.id)

# 🔁 CONVERT
@bot.message_handler(commands=["convert"])
def convert(message):
    user_id = message.from_user.id
    init_user(user_id)

    reset_flow(message.chat.id)
    user_data[user_id]["modo"] = "convert"

    bot.send_message(message.chat.id, "📹 <b>Envie um vídeo</b>\nVou transformar em áudio 👇")
    msg = bot.send_message(message.chat.id, "⏳ Aguardando o vídeo...")
    bot.register_next_step_handler(msg, get_video_convert)

def get_video_convert(message):
    file_id = None

    if message.video:
        file_id = message.video.file_id
    elif message.document and message.document.mime_type and message.document.mime_type.startswith("video/"):
        file_id = message.document.file_id
    elif message.animation:
        file_id = message.animation.file_id
    else:
        bot.send_message(message.chat.id, "❌ Envie um vídeo válido.")
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

            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if result.returncode != 0 or not output_path.exists():
                bot.send_message(message.chat.id, "❌ Não consegui converter o vídeo.")
                return

            with open(output_path, "rb") as audio:
                bot.send_voice(message.chat.id, audio)

    except:
        bot.send_message(message.chat.id, "❌ Erro na conversão.")

def ask_video_convert(chat_id):
    reset_flow(chat_id)
    msg = bot.send_message(chat_id, "📹 Envie o vídeo novamente.")
    bot.register_next_step_handler(msg, get_video_convert)

# 🎧 MÚSICA
def ask_musica(chat_id):
    reset_flow(chat_id)
    msg = bot.send_message(chat_id, "🎧 Qual é a música?")
    bot.register_next_step_handler(msg, get_musica)

def get_musica(message):
    text = message.text or ""

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

    user_data[message.from_user.id]["musica"] = text.strip()
    ask_album(message.chat.id)

# 🖼️ ÁLBUM
def ask_album(chat_id):
    reset_flow(chat_id)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⏭️ Pular", callback_data="skip_album"))

    msg = bot.send_message(chat_id, "🖼️ Qual é o álbum?", reply_markup=markup)
    bot.register_next_step_handler(msg, get_album)

def get_album(message):
    user_data[message.from_user.id]["album"] = safe_text(message.text).strip() or None
    ask_artista(message.chat.id)

# 🙍 ARTISTA
def ask_artista(chat_id):
    reset_flow(chat_id)
    msg = bot.send_message(chat_id, "🙍 Quem é o artista?")
    bot.register_next_step_handler(msg, get_artista)

def get_artista(message):
    user_data[message.from_user.id]["artista"] = safe_text(message.text).strip() or None
    ask_capa(message.chat.id)

# 📸 CAPA
def ask_capa(chat_id):
    reset_flow(chat_id)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⏭️ Pular", callback_data="skip_capa"))

    msg = bot.send_message(chat_id, "📸 Envie a capa (imagem, vídeo ou GIF)", reply_markup=markup)
    bot.register_next_step_handler(msg, get_capa)

def get_capa(message):
    if message.photo:
        user_data[message.from_user.id]["capa"] = ("photo", message.photo[-1].file_id)
        gerar_preview(message)

    elif message.video:
        user_data[message.from_user.id]["capa"] = ("video", message.video.file_id)
        gerar_preview(message)

    elif message.animation:
        user_data[message.from_user.id]["capa"] = ("animation", message.animation.file_id)
        gerar_preview(message)

    else:
        ask_capa(message.chat.id)

# CALLBACKS
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id

    reset_flow(chat_id)

    if call.data == "skip_album":
        user_data[call.from_user.id]["album"] = None
        ask_artista(chat_id)

    elif call.data == "skip_capa":
        user_data[call.from_user.id]["capa"] = None
        gerar_preview(call.message)

    elif call.data == "confirmar":
        bot.send_message(chat_id, "🎉 Pronto! Se quiser outra, use /trackid")

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
    data = user_data[user_id]

    user = message.from_user.first_name or "Usuário"
    musica = data.get("musica") or "Sem música"

    album = f"- {data['album']}" if data.get("album") else ""
    artista = f"— {data['artista']}" if data.get("artista") else ""

    texto = (
        f"🎹<b>{user}</b> está ouvindo...\n\n"
        f"🎧<b>{musica}</b> "
        f"<i>{album} {artista}</i>"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ Enviar", callback_data="confirmar"))

    markup.add(
        types.InlineKeyboardButton("🎧 Editar Música", callback_data="edit_musica"),
        types.InlineKeyboardButton("🎹 Editar Álbum", callback_data="edit_album"),
    )

    markup.add(
        types.InlineKeyboardButton("🙍 Editar Artista", callback_data="edit_artista"),
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

# START
if __name__ == "__main__":
    bot.infinity_polling()
