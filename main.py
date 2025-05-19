import os
import re
import sqlite3
import logging
import threading
import time
import datetime
from flask import Flask, request
import telebot
from telebot import types
import requests

# --- Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Константы ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("Переменная окружения TELEGRAM_BOT_TOKEN не установлена")
    raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

try:
    OWNER_ID = int(os.getenv("OWNER_TELEGRAM_ID"))
except (TypeError, ValueError):
    logger.error("Переменная окружения OWNER_TELEGRAM_ID не установлена или имеет неверный формат")
    raise RuntimeError("OWNER_TELEGRAM_ID must be set to a valid integer")

RENDER_URL = os.getenv("RENDER_URL", "https://barskiehoromi.onrender.com")

# --- Инициализация БД ---
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            dish TEXT,
            meal_type TEXT,
            price INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bike_rentals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            bike_type TEXT,
            rent_time DATETIME
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- Меню ---
FOOD_MENU = {
    "breakfast": {
        "Яичница (150г)": {"price": 500, "photo": "egg.jpg"},
        "Кофе": {"price": 200, "photo": None},
        "Блины (180г)": {"price": 450, "photo": "pancake.jpg"}
    },
    "dinner": {
        "Суп (300г)": {"price": 350, "photo": "soup.jpg"},
        "Рыба (250г)": {"price": 600, "photo": "fish.jpg"},
        "Чай": {"price": 150, "photo": None}
    }
}

BIKE_MENU = {
    "Велосипед 1": {"price_hour": 500, "price_day": 1000, "photo": "bike1.jpg"},
    "Велосипед 2": {"price_hour": 600, "price_day": 1200, "photo": "bike2.jpg"}
}

# --- Инициализация бота и Flask ---
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)
WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# ================= ОБРАБОТЧИКИ КНОПОК =================

@bot.message_handler(commands=["start"])
def start(message):
    main_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main_keyboard.add(
        types.KeyboardButton("🏠 О доме"),
        types.KeyboardButton("🌆 Город"),
        types.KeyboardButton("🛍️ Сувениры"),
        types.KeyboardButton("Обратная связь")
    )
    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать в наш дом! 🏡\nВыберите раздел:",
        reply_markup=main_keyboard
    )

@bot.message_handler(func=lambda m: m.text == "🏠 О доме")
def handle_home(message):
    try:
        with open("photos/main_photo.jpg", "rb") as photo:
            bot.send_photo(
                message.chat.id,
                photo,
                caption="🏡 Уютный дом с видом на лес. Все удобства включены."
            )
    except FileNotFoundError:
        logger.error("Файл photos/main_photo.jpg не найден")
        bot.send_message(message.chat.id, "🏡 Уютный дом с видом на лес. Все удобства включены.")
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🍽 Еда"),
        types.KeyboardButton("🚲 Прокат велосипедов"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🌆 Город")
def handle_city(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🏛️ Музей Карельского фронта"),
        types.KeyboardButton("🚖 Такси"),
        types.KeyboardButton("🏥 Больница"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(
        message.chat.id,
        "🌆 Г. Беломорск, Республика Карелия:\nНаселение: ~12 000 чел.",
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text == "🏛️ Музей Карельского фронта")
def handle_museum(message):
    try:
        with open("photos/museum.jpg", "rb") as photo:
            bot.send_photo(
                message.chat.id,
                photo,
                caption="🏛️ Музей Карельского фронта\n📍 Адрес: ул. Банковская, 26"
            )
    except FileNotFoundError:
        logger.error("Файл photos/museum.jpg не найден")
        bot.send_message(message.chat.id, "🏛️ Музей Карельского фронта\n📍 Адрес: ул. Банковская, 26")
    # Возврат к разделу «О доме»
    handle_home(message)

@bot.message_handler(func=lambda m: m.text == "🚖 Такси")
def handle_taxi(message):
    bot.send_message(message.chat.id, "🚖 Телефон такси: +7-999-999-99-99")

@bot.message_handler(func=lambda m: m.text == "🏥 Больница")
def handle_hospital(message):
    bot.send_message(message.chat.id, "🏥 Адрес больницы: ул. Больничная, 1")

@bot.message_handler(func=lambda m: m.text == "🛍️ Сувениры")
def handle_souvenirs(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🧲 Магнит на холодильник"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(message.chat.id, "🛍️ Сувениры:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🧲 Магнит на холодильник")
def handle_magnet(message):
    try:
        with open("photos/magnet.jpg", "rb") as photo:
            bot.send_photo(
                message.chat.id,
                photo,
                caption="🧲 Магнит на холодильник - 100₽"
            )
    except FileNotFoundError:
        logger.error("Файл photos/magnet.jpg не найден")
        bot.send_message(message.chat.id, "🧲 Магнит на холодильник - 100₽")
    # Возврат к старту
    start(message)

@bot.message_handler(func=lambda m: m.text == "Обратная связь")
def handle_feedback(message):
    msg = bot.send_message(message.chat.id, "💬 Напишите ваш отзыв:")
    bot.register_next_step_handler(msg, send_feedback)

def send_feedback(message):
    user_tag = message.from_user.username or str(message.from_user.id)
    try:
        bot.send_message(OWNER_ID, f"📬 Отзыв от @{user_tag}:\n{message.text}")
        bot.send_message(message.chat.id, "✅ Сообщение отправлено!", reply_markup=types.ReplyKeyboardRemove())
    except Exception as e:
        logger.error(f"Не удалось отправить отзыв владельцу: {e}")
        bot.send_message(message.chat.id, "❌ Не удалось отправить отзыв. Попробуйте позже.", reply_markup=types.ReplyKeyboardRemove())

# --- Прокат велосипедов ---
@bot.message_handler(func=lambda m: m.text == "🚲 Прокат велосипедов")
def bike_rental(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("Велосипед 1"),
        types.KeyboardButton("Велосипед 2"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(message.chat.id, "Выберите велосипед:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["Велосипед 1", "Велосипед 2"])
def show_bike_details(message):
    try:
        bike = BIKE_MENU[message.text]
        if bike["photo"]:
            try:
                with open(f"photos/{bike['photo']}", "rb") as photo:
                    bot.send_photo(
                        message.chat.id,
                        photo,
                        caption=(
                            f"🚲 {message.text}\n"
                            f"Цены:\n- 1 час: {bike['price_hour']}₽\n"
                            f"- Целый день: {bike['price_day']}₽"
                        )
                    )
            except FileNotFoundError:
                logger.error(f"Фото для {message.text} не найдено")
                bot.send_message(
                    message.chat.id,
                    f"🚲 {message.text}\nЦены:\n- 1 час: {bike['price_hour']}₽\n- Целый день: {bike['price_day']}₽"
                )
        else:
            bot.send_message(
                message.chat.id,
                f"🚲 {message.text}\nЦены:\n- 1 час: {bike['price_hour']}₽\n- Целый день: {bike['price_day']}₽"
            )
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(
            types.KeyboardButton("✅ Хочу кататься!"),
            types.KeyboardButton("🔙 Назад")
        )
        bot.send_message(message.chat.id, "Забронировать?", reply_markup=markup)
    except Exception as e:
        logger.error(f"Ошибка при загрузке велосипеда: {e}")
        bot.send_message(message.chat.id, "❌ Не удалось загрузить информацию о велосипеде.")

@bot.message_handler(func=lambda m: m.text == "✅ Хочу кататься!")
def confirm_bike_rental(message):
    # Сохраняем аренду в базу
    try:
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        # Найдем последний выбранный велосипед из предыдущего сообщения
        # Тут мы полагаемся на то, что handler show_bike_details сразу перед этим показал кнопку
        bike_type = None
        # Можно хранить временно выбор пользователя, но для простоты возьмем предыдущую строку чата
        # Предположим, что пользователь точно нажал кнопку "Велосипед 1" или "Велосипед 2" перед этим
        # Передаем bike_type через состояние или БД; в рамках данного примера просто возьмем текст из message.reply_to_message
        if message.reply_to_message and message.reply_to_message.text:
            # Ищем цифру "1" или "2" в тексте сообщения-ответа
            if "Велосипед 1" in message.reply_to_message.text:
                bike_type = "Велосипед 1"
            elif "Велосипед 2" in message.reply_to_message.text:
                bike_type = "Велосипед 2"
        if not bike_type:
            # Если не удалось определить, запишем generic
            bike_type = "Неизвестный велосипед"
        cursor.execute(
            "INSERT INTO bike_rentals (user_id, bike_type, rent_time) VALUES (?, ?, ?)",
            (message.chat.id, bike_type, datetime.datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка при записи проката велосипеда в БД: {e}")

    # Уведомляем владельца
    user_tag = message.from_user.username or str(message.from_user.id)
    try:
        bot.send_message(OWNER_ID, f"🚴 Новый прокат от @{user_tag}: {bike_type}")
    except Exception as e:
        logger.error(f"Не удалось отправить владельцу сообщение о прокате: {e}")

    bot.send_message(message.chat.id, "✅ Велосипед забронирован. Хозяин свяжется с вами.", reply_markup=types.ReplyKeyboardRemove())
    # Возврат к старту
    start(message)

# --- Еда и корзина ---
@bot.message_handler(func=lambda m: m.text == "🍽 Еда")
def handle_food(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🍳 Завтрак"),
        types.KeyboardButton("🍽 Ужин"),
        types.KeyboardButton("🛒 Корзина"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(message.chat.id, "Выберите категорию:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["🍳 Завтрак", "🍽 Ужин"])
def show_food_menu(message):
    meal_type = "breakfast" if message.text == "🍳 Завтрак" else "dinner"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for dish in FOOD_MENU[meal_type]:
        markup.add(types.KeyboardButton(dish))
    markup.add(types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "Выберите блюдо:", reply_markup=markup)

@bot.message_handler(func=lambda m: (m.text in FOOD_MENU.get("breakfast", {})) or (m.text in FOOD_MENU.get("dinner", {})))
def add_to_cart(message):
    meal_type = "breakfast" if message.text in FOOD_MENU["breakfast"] else "dinner"
    dish_info = FOOD_MENU[meal_type][message.text]

    # Отправка фото (если есть)
    if dish_info["photo"]:
        try:
            with open(f"photos/{dish_info['photo']}", "rb") as photo:
                bot.send_photo(message.chat.id, photo)
        except FileNotFoundError:
            logger.error(f"Фото для {message.text} не найдено")
            bot.send_message(message.chat.id, f"{message.text} - {dish_info['price']}₽")
    else:
        bot.send_message(message.chat.id, f"{message.text} - {dish_info['price']}₽")

    # Кнопки подтверждения
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("✅ Добавить в корзину"),
        types.KeyboardButton("🔙 Назад")
    )
    msg = bot.send_message(message.chat.id, f"{message.text} - {dish_info['price']}₽", reply_markup=markup)
    # Передаём meal_type и dish через lambda
    bot.register_next_step_handler(msg, lambda m, mt=meal_type, ds=message.text: confirm_add_to_cart(m, mt, ds))

def confirm_add_to_cart(message, meal_type, dish):
    if message.text == "✅ Добавить в корзину":
        try:
            conn = sqlite3.connect('bot_data.db')
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO cart (user_id, dish, meal_type, price) VALUES (?, ?, ?, ?)",
                (message.chat.id, dish, meal_type, FOOD_MENU[meal_type][dish]["price"])
            )
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, f"✅ {dish} добавлено в корзину!")
        except Exception as e:
            logger.error(f"Ошибка при добавлении в корзину: {e}")
            bot.send_message(message.chat.id, "❌ Не удалось добавить в корзину.")
    # Возврат к старту после добавления или если нажали «Назад»
    start(message)

@bot.message_handler(func=lambda m: m.text == "🛒 Корзина")
def show_cart(message):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT dish, meal_type, price FROM cart WHERE user_id=?", (message.chat.id,))
    items = cursor.fetchall()
    conn.close()

    if not items:
        bot.send_message(message.chat.id, "Корзина пуста.", reply_markup=types.ReplyKeyboardRemove())
        return

    total = sum(item[2] for item in items)
    cart_text = "🛒 Ваш заказ:\n" + "\n".join(
        [f"- {dish} ({meal_type}): {price}₽" for dish, meal_type, price in items]
    ) + f"\nИтого: {total}₽"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("✅ Подтвердить заказ"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(message.chat.id, cart_text, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "✅ Подтвердить заказ")
def confirm_cart(message):
    # Выдаем конкретные слоты времени
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("09:00"),
        types.KeyboardButton("18:00"),
        types.KeyboardButton("⏰ Другое время")
    )
    bot.send_message(message.chat.id, "Выберите время доставки (например, 09:00 или 18:00):", reply_markup=markup)

@bot.message_handler(func=lambda m: re.match(r"^(09:00|18:00|⏰ Другое время)$", m.text))
def handle_delivery_time(message):
    if message.text == "⏰ Другое время":
        prompt = bot.send_message(message.chat.id, "Укажите время в формате ЧЧ:ММ:")
        bot.register_next_step_handler(prompt, save_custom_time)
    else:
        # Пользователь выбрал "09:00" или "18:00"
        save_order(message, custom_time=message.text)

def save_custom_time(message):
    if not re.match(r"^\d{2}:\d{2}$", message.text):
        bot.send_message(message.chat.id, "❌ Некорректный формат времени! Попробуйте еще раз в формате ЧЧ:ММ:")
        bot.register_next_step_handler(message, save_custom_time)
        return
    save_order(message, custom_time=message.text)

def save_order(message, custom_time=None):
    user_id = message.chat.id
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT dish, meal_type FROM cart WHERE user_id=?", (user_id,))
    items = cursor.fetchall()

    if not items:
        bot.send_message(message.chat.id, "❌ Ваша корзина пуста.", reply_markup=types.ReplyKeyboardRemove())
        conn.close()
        return

    user_tag = message.from_user.username or str(message.from_user.id)
    order_text = f"Новый заказ от @{user_tag}:\n"
    for dish, meal_type in items:
        order_text += f"- {dish} ({meal_type.capitalize()})\n"

    if custom_time:
        order_text += f"⏰ Время: {custom_time}"
    else:
        # В случае, если save_order вызван напрямую без передачи custom_time,
        # допустим, message.text уже содержит нужное время
        order_text += f"⏰ Время: {message.text}"

    try:
        bot.send_message(OWNER_ID, order_text)
    except Exception as e:
        logger.error(f"Не удалось отправить заказ владельцу: {e}")
        bot.send_message(message.chat.id, "❌ Не удалось оформить заказ. Попробуйте позже.", reply_markup=types.ReplyKeyboardRemove())
        conn.close()
        return

    # Удаляем позиции из корзины после успешной отправки
    cursor.execute("DELETE FROM cart WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    bot.send_message(user_id, "✅ Заказ отправлен!", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
def go_back(message):
    # Возврат к стартовому меню
    start(message)

# --- Автопинг ---
def self_ping():
    while True:
        try:
            requests.get(f"{RENDER_URL}/ping", timeout=5)
            logger.info("Автопинг выполнен")
        except Exception as e:
            logger.error(f"Ошибка автопинга: {e}")
        time.sleep(300)

threading.Thread(target=self_ping, daemon=True).start()

# --- Flask-роуты ---
@app.route("/")
def index():
    return "Bot is running!", 200

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    if request.method == "POST":
        update = types.Update.de_json(request.get_json(force=True))
        bot.process_new_updates([update])
    return "", 200

@app.route("/ping")
def ping():
    return "OK", 200

if __name__ == "__main__":
    # Откроем на всех интерфейсах, порт по умолчанию или из окружения
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
