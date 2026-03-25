import telebot
from telebot import types

TOKEN = "SEU_TELEGRAM_TOKEN_AQUI"
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

# /start
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    init_user(user_id)

    bot.send_message(
        message.chat.id,
        "🎶 Esse bot é para você mostrar aquela música ques está ouvindo, mas não tem em lugar nenhum!\n"
        "📝 Só mandar os dados que deixo pronto para você enviar..."
    )

    ask_musica(message)

# 🎧 Música
def ask_musica(message):
    bot.send_message(message.chat.id, "🎧 Música?")
    bot.register_next_step_handler(message, get_musica)

def get_musica(message):
    user_data[message.from_user.id]["musica"] = message.text
    ask_album(message)

# 🎹 Álbum
def ask_album(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❎", callback_data="skip_album"))

    bot.send_message(message.chat.id, "🎹 Album?", reply_markup=markup)
    bot.register_next_step_handler(message, get_album)

def get_album(message):
    user_data[message.from_user.id]["album"] = message.text
    ask_artista(message)

# 🙍 Artista
def ask_artista(message):
    bot.send_message(message.chat.id, "🙍 Artista?")
    bot.register_next_step_handler(message, get_artista)

def get_artista(message):
    user_data[message.from_user.id]["artista"] = message.text
    ask_capa(message)

# 📸 Capa
def ask_capa(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❎", callback_data="skip_capa"))

    bot.send_message(message.chat.id, "📸 Capa?", reply_markup=markup)
    bot.register_next_step_handler(message, get_capa)

def get_capa(message):
    if message.photo:
        file_id = message.photo[-1].file_id
        user_data[message.from_user.id]["capa"] = file_id

    gerar_preview(message)

# CALLBACKS (❎)
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    user_id = call.from_user.id

    if call.data == "skip_album":
        user_data[user_id]["album"] = None
        ask_artista(call.message)

    elif call.data == "skip_capa":
        user_data[user_id]["capa"] = None
        gerar_preview(call.message)

    elif call.data == "confirmar":
        bot.send_message(call.message.chat.id,
                         "🪗🎷🎼 Muito obrigado! quiser outra música mande /start")

    elif call.data == "editar":
        editar_menu(call.message)

    elif call.data == "edit_musica":
        ask_musica(call.message)

    elif call.data == "edit_album":
        ask_album(call.message)

    elif call.data == "edit_artista":
        ask_artista(call.message)

# PREVIEW FINAL
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
        bot.send_photo(message.chat.id, data["capa"], caption=texto, reply_markup=markup)
    else:
        bot.send_message(message.chat.id, texto, reply_markup=markup)

# MENU DE EDIÇÃO
def editar_menu(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🎧 Música?", callback_data="edit_musica"),
        types.InlineKeyboardButton("🎹 Album?", callback_data="edit_album"),
        types.InlineKeyboardButton("🙍 Artisa?", callback_data="edit_artista"),
    )

    bot.send_message(message.chat.id, "🔊 O que deseja corrigir?", reply_markup=markup)

# START
bot.infinity_polling()