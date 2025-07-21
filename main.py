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
            item TEXT,
            quantity INTEGER
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

# --- Словарь товаров мерча (название: (цена, файл фото)) ---
MERCH_ITEMS = {
    "🛒 Шоперы":   (500, "shopper.jpg"),
    "☕ Кружки":    (300, "mug.jpg"),
    "👕 Футболки":  (800, "tshirt.jpg")
}

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

# --- Раздел: Мерч с фото и количеством ---
@bot.message_handler(func=lambda m: m.text and m.text.startswith("4️⃣ Мерч"))
def merch_menu(message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for name in MERCH_ITEMS:
        keyboard.add(types.KeyboardButton(name))
    keyboard.add(
        types.KeyboardButton("🛍️ Корзина"),
        types.KeyboardButton("🔙 Назад к меню")
    )
    bot.send_message(
        message.chat.id,
        "🛍️ Раздел Мерч: выберите товар, чтобы посмотреть детали и заказать.",
        reply_markup=keyboard
    )

# Показываем фото и кнопки для каждого товара
@bot.message_handler(func=lambda m: m.text in MERCH_ITEMS)
def show_merch_item(message):
    name = message.text
    price, photo_file = MERCH_ITEMS[name]
    try:
        with open(f"photos/{photo_file}", "rb") as photo:
            bot.send_photo(
                message.chat.id,
                photo,
                caption=f"{name[2:]} — {price}₽"
            )
    except FileNotFoundError:
        bot.send_message(message.chat.id, f"{name[2:]} — {price}₽")
    # Предлагаем заказать или вернуться
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        types.KeyboardButton("✅ Заказать"),
        types.KeyboardButton("🔙 Назад к Мерч")
    )
    msg = bot.send_message(message.chat.id, "Выберите действие:", reply_markup=keyboard)
    bot.register_next_step_handler(msg, lambda m: merch_order_choice(m, name))

# Обработка выбора заказать или назад
def merch_order_choice(message, item_name):
    if message.text == "✅ Заказать":
        msg = bot.send_message(message.chat.id, "Сколько штук добавить?")
        bot.register_next_step_handler(msg, lambda m: add_merch_quantity(m, item_name))
    else:
        merch_menu(message)

# Добавление в корзину с количеством
def add_merch_quantity(message, item_name):
    try:
        qty = int(message.text)
        if qty < 1:
            raise ValueError
    except ValueError:
        msg = bot.send_message(message.chat.id, "Введите корректное число (>0):")
        bot.register_next_step_handler(msg, lambda m: add_merch_quantity(m, item_name))
        return
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO merch_cart (user_id, item, quantity) VALUES (?, ?, ?)",
        (message.chat.id, item_name[2:], qty)
    )
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"✔️ Добавлено: {item_name[2:]} ×{qty}")
    merch_menu(message)

# Показ корзины
@bot.message_handler(func=lambda m: m.text == "🛍️ Корзина")
def show_merch_cart(message):
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("SELECT item, quantity FROM merch_cart WHERE user_id=?", (message.chat.id,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        bot.send_message(
            message.chat.id,
            "🛍️ Ваша корзина пуста.",
            reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("🔙 Назад к Мерч"))
        )
        return
    text = "🛍️ Корзина:\n" + "\n".join([f"- {item}: {qty}" for item, qty in rows])
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(types.KeyboardButton("✅ Оформить заказ"), types.KeyboardButton("🔙 Назад к Мерч"))
    bot.send_message(message.chat.id, text, reply_markup=keyboard)

# Оформление заказа
@bot.message_handler(func=lambda m: m.text == "✅ Оформить заказ")
def send_merch_order(message):
    conn = sqlite3.connect('bot_data.db')
    cur = conn.cursor()
    cur.execute("SELECT item, quantity FROM merch_cart WHERE user_id=?", (message.chat.id,))
    rows = cur.fetchall()
    cur.execute("DELETE FROM merch_cart WHERE user_id=?", (message.chat.id,))
    conn.commit()
    conn.close()
    order = f"Новый заказ мерча от @{message.from_user.username or message.chat.id}:\n"
    order += "\n".join([f"- {item} ×{qty}" for item, qty in rows])
    bot.send_message(OWNER_ID, order)
    bot.send_message(
        message.chat.id,
        "Спасибо, ваш заказ отправлен! 🎉",
        reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(types.KeyboardButton("🔙 Назад к Мерч"))
    )

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

@bot.message_handler(func=lambda m: m.text and m.text.startswith("2️⃣ Кундалини-йога"))
def yoga_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("🏢 Офлайн-мероприятия"), types.KeyboardButton("💻 Онлайн-йога"))
    kb.add(types.KeyboardButton("📅 Ближайшие мероприятия"), types.KeyboardButton("🔙 Назад к меню"))
    bot.send_message(message.chat.id,
                     "🧘 Кундалини-йога: офлайн, онлайн и ближайшие события.",
                     reply_markup=kb)

@bot.message_handler(func=lambda m: m.text and m.text.startswith("3️⃣ Медиа"))
def media_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("▶️ YouTube"), types.KeyboardButton("🔙 Назад к меню"))
    bot.send_message(message.chat.id,
                     "🎥 Медиа: наши видео на YouTube.",
                     reply_markup=kb)

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
