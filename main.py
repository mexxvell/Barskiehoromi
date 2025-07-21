import os
import logging
import sqlite3
import threading
import time
import requests
from flask import Flask, request
import telebot
from telebot import types

# --- Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Константы ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("Переменная TELEGRAM_BOT_TOKEN не установлена")
    raise RuntimeError("TOKEN is required")
OWNER_ID = int(os.getenv("OWNER_TELEGRAM_ID", "0")) or None
if not OWNER_ID:
    logger.error("Переменная OWNER_TELEGRAM_ID не установлена или некорректна")
    raise RuntimeError("OWNER_TELEGRAM_ID is required")
RENDER_URL = os.getenv("RENDER_URL", "https://your-app.onrender.com")
WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"

# --- Инициализация БД ---

def init_db():
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS merch_cart (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            item TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- Инициализация бота и Flask ---
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# ================= ОБРАБОТЧИКИ =================

@bot.message_handler(commands=["start"])
def start(message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        types.KeyboardButton("1️⃣ Путешествия"),
        types.KeyboardButton("2️⃣ Кундалини-йога"),
        types.KeyboardButton("3️⃣ Медиа"),
        types.KeyboardButton("4️⃣ Мерч"),
        types.KeyboardButton("5️⃣ Доп. услуги")
    )
    text = (
        "👋 Добро пожаловать! Выберите раздел:\n"
        "1️⃣ Путешествия\n"
        "2️⃣ Кундалини-йога\n"
        "3️⃣ Медиа\n"
        "4️⃣ Мерч\n"
        "5️⃣ Доп. услуги"
    )
    bot.send_message(message.chat.id, text, reply_markup=keyboard)

# --- Раздел: Мерч с корзиной ---
@bot.message_handler(func=lambda m: m.text and m.text.startswith("4️⃣ Мерч"))
def merch_menu(message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        types.KeyboardButton("🛒 Шоперы"),
        types.KeyboardButton("☕ Кружки"),
        types.KeyboardButton("👕 Футболки"),
        types.KeyboardButton("🛍️ Корзина")
    )
    keyboard.add(types.KeyboardButton("🔙 Назад к меню"))
    info = (
        "🛍️ Раздел Мерч:\n"
        "Выберите товар для добавления в корзину или перейдите к оформлению заказа."
    )
    bot.send_message(message.chat.id, info, reply_markup=keyboard)

for item, label in [("🛒 Шоперы", "Шопер — 500₽"), ("☕ Кружки", "Кружка — 300₽"), ("👕 Футболки", "Футболка — 800₽")]:
    @bot.message_handler(func=lambda m, itm=item: m.text == itm)
    def add_merch(m, item=item):
        conn = sqlite3.connect('bot_data.db')
        cur = conn.cursor()
        cur.execute("INSERT INTO merch_cart (user_id, item) VALUES (?, ?)", (m.chat.id, label))
        conn.commit()
        conn.close()
        bot.send_message(m.chat.id, f"✔️ {label} добавлено в корзину.")
        merch_menu(m)

@bot.message_handler(func=lambda m: m.text == "🛍️ Корзина")
def show_merch_cart(message):
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("SELECT item FROM merch_cart WHERE user_id=?", (message.chat.id,))
    items = [row[0] for row in cur.fetchall()]
    conn.close()
    if not items:
        bot.send_message(message.chat.id, "🛍️ Ваша корзина пуста.", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("🔙 Назад к меню")))
        return
    text = "🛍️ Ваша корзина:\n" + "\n".join([f"- {i}" for i in items])
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("✅ Оформить"), types.KeyboardButton("🔙 Назад к меню"))
    bot.send_message(message.chat.id, text, reply_markup=keyboard)

@bot.message_handler(func=lambda m: m.text == "✅ Оформить")
def send_merch_order(message):
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("SELECT item FROM merch_cart WHERE user_id=?", (message.chat.id,))
    items = [row[0] for row in cur.fetchall()]
    cur.execute("DELETE FROM merch_cart WHERE user_id=?", (message.chat.id,))
    conn.commit()
    conn.close()
    order_text = f"Новый заказ мерча от @{message.from_user.username or message.chat.id}:\n" + "\n".join(items)
    bot.send_message(OWNER_ID, order_text)
    bot.send_message(message.chat.id, "Спасибо за заказ! 🎉", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("🔙 Назад к меню")))

# --- Автопинг для поддержания работы ---
def self_ping():
    while True:
        try:
            requests.get(f"{RENDER_URL}/ping", timeout=5)
            logger.info("Пинг выполнен")
        except Exception as e:
            logger.error(f"Ошибка пинга: {e}")
        time.sleep(300)

threading.Thread(target=self_ping, daemon=True).start()

# --- Прочие разделы (каркас) ---
@bot.message_handler(func=lambda m: m.text and m.text.startswith("1️⃣ Путешествия"))
def travels_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("📂 Архив путешествий"), types.KeyboardButton("🌍 Где мы сейчас"))
    kb.add(types.KeyboardButton("🔙 Назад к меню"))
    bot.send_message(message.chat.id,
                     "✈️ Путешествия: архив и текущее местоположение.",
                     reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "📂 Архив путешествий")
def travels_archive(message):
    bot.send_message(message.chat.id, "Здесь будет архив наших путешествий 🗺️")

@bot.message_handler(func=lambda m: m.text == "🌍 Где мы сейчас")
def travels_now(message):
    bot.send_message(message.chat.id, "Мы сейчас в: ... 📍")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("2️⃣ Кундалини-йога"))
def yoga_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("🏢 Офлайн-мероприятия"), types.KeyboardButton("💻 Онлайн-йога"))
    kb.add(types.KeyboardButton("📅 Ближайшие мероприятия"), types.KeyboardButton("🔙 Назад к меню"))
    bot.send_message(message.chat.id,
                     "🧘 Кундалини-йога: офлайн, онлайн и ближайшие события.",
                     reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ["🏢 Офлайн-мероприятия","💻 Онлайн-йога","📅 Ближайшие мероприятия"] )
def yoga_handlers(message):
    bot.send_message(message.chat.id, "Информация скоро появится.")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("3️⃣ Медиа"))
def media_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("▶️ YouTube"), types.KeyboardButton("🔙 Назад к меню"))
    bot.send_message(message.chat.id,
                     "🎥 Медиа: наши видео на YouTube.",
                     reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "▶️ YouTube")
def media_youtube(message):
    bot.send_message(message.chat.id, "Смотрите нас: https://www.youtube.com/your_channel")

@bot.message_handler(func=lambda m: m.text == "5️⃣ Доп. услуги")
def services_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("🔙 Назад к меню"))
    bot.send_message(message.chat.id,
                     "🔧 Дополнительные услуги: детали по запросу.",
                     reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🔙 Назад к меню")
def back_to_start(message):
    start(message)

# --- Flask-роуты ---
@app.route("/", methods=["GET"])
def index():
    return "Bot is running!", 200

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = types.Update.de_json(request.get_json(force=True))
    bot.process_new_updates([update])
    return "", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
