import os
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
    user_data[user_id] = {
        "musica": None,
        "album": None,
        "artista": None,
        "capa": None
    }

def reset_flow(chat_id):
    try:
        bot.clear_step_handler_by_chat_id(chat_id)
    except:
        pass

# 🔥 INTERCEPTA /start EM QUALQUER MOMENTO
@bot.message_handler(commands=['start'], func=lambda message: True)
def start(message):
    user_id = message.from_user.id

    reset_flow(message.chat.id)
    init_user(user_id)

    bot.send_message(
        message.chat.id,
        "🎶 Esse bot é para você mostrar aquela música que está ouvindo, mas não tem em lugar nenhum!\n"
        "📝 Só mandar os dados que deixo pronto para você enviar..."
    )

    ask_musica(message.chat.id)

# 🎧 Música (AGORA ACEITA LINK DO TELEGRAM)
def ask_musica(chat_id):
    reset_flow(chat_id)
    msg = bot.send_message(chat_id, "🎧 Música?")
    bot.register_next_step_handler(msg, get_musica)

def get_musica(message):
    text = message.text or ""

    # 🔥 CONVERTE ENTIDADES (links do Telegram) PARA HTML
    if message.entities:
        offset_correction = 0
        for entity in message.entities:
            if entity.type == "text_link":
                start = entity.offset + offset_correction
                end = start + entity.length
                original = text[start:end]

                link = f'<a href="{entity.url}">{original}</a>'
                text = text[:start] + link + text[end:]

                offset_correction += len(link) - len(original)

    user_data[message.from_user.id]["musica"] = text
    ask_album(message.chat.id)

# 🎹 Álbum
def ask_album(chat_id):
    reset_flow(chat_id)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❎", callback_data="skip_album"))

    msg = bot.send_message(chat_id, "🎹 Album?", reply_markup=markup)
    bot.register_next_step_handler(msg, get_album)

def get_album(message):
    user_data[message.from_user.id]["album"] = message.text
    ask_artista(message.chat.id)

# 🙍 Artista
def ask_artista(chat_id):
    reset_flow(chat_id)
    msg = bot.send_message(chat_id, "🙍 Artista?")
    bot.register_next_step_handler(msg, get_artista)

def get_artista(message):
    user_data[message.from_user.id]["artista"] = message.text
    ask_capa(message.chat.id)

# 📸 Capa (ACEITA FOTO OU VÍDEO)
def ask_capa(chat_id):
    reset_flow(chat_id)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❎", callback_data="skip_capa"))

    msg = bot.send_message(chat_id, "📸 Envie a capa (imagem ou vídeo)?", reply_markup=markup)
    bot.register_next_step_handler(msg, get_capa)

def get_capa(message):
    if message.photo:
        file_id = message.photo[-1].file_id
        user_data[message.from_user.id]["capa"] = ("photo", file_id)
        gerar_preview(message)

    elif message.video:
        file_id = message.video.file_id
        user_data[message.from_user.id]["capa"] = ("video", file_id)
        gerar_preview(message)

    else:
        ask_capa(message.chat.id)

# CALLBACKS
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    reset_flow(chat_id)

    if call.data == "skip_album":
        user_data[user_id]["album"] = None
        ask_artista(chat_id)

    elif call.data == "skip_capa":
        user_data[user_id]["capa"] = None
        gerar_preview(call.message)

    elif call.data == "confirmar":
        bot.send_message(chat_id,
                         "🪗🎷🎼 Muito obrigado! quiser outra música mande /start")

    elif call.data == "editar":
        editar_menu(chat_id)

    elif call.data == "edit_musica":
        ask_musica(chat_id)

    elif call.data == "edit_album":
        ask_album(chat_id)

    elif call.data == "edit_artista":
        ask_artista(chat_id)

# PREVIEW
def gerar_preview(message):
    user_id = message.from_user.id
    data = user_data[user_id]

    user = message.from_user.first_name
    musica = data["musica"]

    album = f"- {data['album']}" if data["album"] else ""
    artista = f"— {data['artista']}" if data["artista"] else ""

    texto = (
        f"🎹<b>{user}</b> está ouvindo...\n\n"
        f"🎧<b>{musica}</b> "
        f"<i>{album} {artista}</i>"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✔️ Sim", callback_data="confirmar"),
        types.InlineKeyboardButton("✖️ Não", callback_data="editar")
    )

    if data["capa"]:
        tipo, file_id = data["capa"]

        if tipo == "photo":
            bot.send_photo(message.chat.id, file_id, caption=texto, reply_markup=markup)

        elif tipo == "video":
            bot.send_video(message.chat.id, file_id, caption=texto, reply_markup=markup)

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
bot.infinity_polling()
