import os
import logging
import threading
import requests
import sqlite3
from flask import Flask, request
import telebot
from telebot import types

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_TELEGRAM_ID")  # Telegram ID владельца
RENDER_URL = os.getenv("RENDER_URL", "https://barskiehoromi.onrender.com ")

# Проверка переменных окружения
if not all([TOKEN, OWNER_ID, RENDER_URL]):
    raise EnvironmentError("Не заданы обязательные переменные окружения!")

# Флэш-приложение
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    # Таблица для хранения заказов еды
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            user_id INTEGER,
            meal_type TEXT,
            dish TEXT,
            time TEXT
        )
    ''')
    # Таблица для хранения заказов на прокат велосипедов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bike_rentals (
            user_id INTEGER,
            bike_type TEXT,
            rent_time TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Меню блюд
FOOD_MENU = {
    "breakfast": {
        "🥞 Яичница": {"price": 500, "photo": "egg.jpg"},
        "🧇 Блины": {"price": 450, "photo": "pancake.jpg"},
        "🍵 Чай": {"price": 200, "photo": None}
    },
    "dinner": {
        "🍲 Суп": {"price": 350, "photo": "soup.jpg"},
        "🐟 Рыба": {"price": 600, "photo": "fish.jpg"},
        "🍵 Чай": {"price": 150, "photo": None}
    }
}

# Время доставки
TIME_SLOTS = {
    "breakfast": ["08:00", "09:00", "10:00"],
    "dinner": ["18:00", "19:00", "20:00"]
}

# Меню велосипедов
BIKE_MENU = {
    "🚲 Велосипед 1": {"price_hour": 500, "price_day": 1000, "photo": "bike1.jpg"},
    "🚲 Велосипед 2": {"price_hour": 600, "price_day": 1200, "photo": "bike2.jpg"}
}

# Установка вебхука (программно)
WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# ================= ОБРАБОТЧИКИ КНОПОК =================
@bot.message_handler(commands=["start"])
def start(message):
    logger.info(f"Пользователь {message.chat.id} начал работу с ботом.")
    main_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main_keyboard.add(
        types.KeyboardButton("🏠 О доме"),
        types.KeyboardButton("🌆 Город"),
        types.KeyboardButton("🛍️ Сувениры"),
        types.KeyboardButton("🚴 Прокат велосипедов"),
        types.KeyboardButton("Обратная связь")
    )
    bot.send_message(
        message.chat.id,
        "👋 Добро пожаловать в наш дом! 🏡\n"
        "Правила использования:\n"
        "1) Выберите раздел из меню\n"
        "2) Следуйте инструкциям\n"
        "3) При заказе еды укажите удобное время\n"
        "4) Информация отправится хозяевам\n"
        "5) Они свяжутся для уточнения деталей",
        reply_markup=main_keyboard
    )

@bot.message_handler(func=lambda m: m.text == "🏠 О доме")
def handle_home(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'О доме'.")
    with open("photos/main_photo.jpg", "rb") as photo:
        bot.send_photo(
            message.chat.id,
            photo,
            caption="🏡 О доме:\n"
                    "Наш дом расположен в живописном месте. Здесь вы найдете уют и комфорт.\n"
                    "Можно заказать еду или получить помощь."
        )
    home_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    home_submenu.add(types.KeyboardButton("🍽 Еда"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "Выберите нужный раздел:", reply_markup=home_submenu)

@bot.message_handler(func=lambda m: m.text == "🍽 Еда")
def handle_food(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'Еда'.")
    meal_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    meal_keyboard.add(
        types.KeyboardButton("🍳 Завтрак"),
        types.KeyboardButton("🍽 Ужин"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(
        message.chat.id,
        "🍽 Меню на завтра:\n"
        "Здесь можно заказать еду на завтрак или ужин.\n"
        "Выберите один из пунктов, и информация будет отправлена хозяевам.",
        reply_markup=meal_keyboard
    )

@bot.message_handler(func=lambda m: m.text in ["🍳 Завтрак", "🍽 Ужин"])
def choose_meal_type(message):
    meal_type = "breakfast" if message.text == "🍳 Завтрак" else "dinner"
    logger.info(f"Пользователь {message.chat.id} выбрал {meal_type}.")
    buttons = [types.KeyboardButton(food) for food in FOOD_MENU[meal_type]]
    buttons.append(types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "Выберите блюдо:", reply_markup=types.ReplyKeyboardMarkup(keyboard=[buttons], resize_keyboard=True))

@bot.message_handler(func=lambda m: m.text in FOOD_MENU["breakfast"] or m.text in FOOD_MENU["dinner"])
def add_to_cart(message):
    meal_type = "breakfast" if message.text in FOOD_MENU["breakfast"] else "dinner"
    dish_info = FOOD_MENU[meal_type][message.text]
    logger.info(f"Пользователь {message.chat.id} добавил '{message.text}' в корзину.")
    # Отправка фото (если есть)
    if dish_info["photo"]:
        try:
            with open(f"photos/{dish_info['photo']}", "rb") as photo:
                bot.send_photo(message.chat.id, photo, caption=f"{message.text} - {dish_info['price']}₽")
        except FileNotFoundError:
            bot.send_message(message.chat.id, f"{message.text} - {dish_info['price']}₽")
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("✅ Добавить в корзину"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "Добавить это блюдо в корзину?", reply_markup=markup)
    bot.register_next_step_handler(message, lambda m: confirm_add_to_cart(m, meal_type, message.text))

def confirm_add_to_cart(message, meal_type, dish):
    if message.text == "✅ Добавить в корзину":
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (user_id, meal_type, dish, time) VALUES (?, ?, ?, ?)",
            (message.chat.id, meal_type, dish, "Не указано")
        )
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ '{dish}' добавлено в корзину!")
    go_back_to_food(message)

def go_back_to_food(message):
    meal_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    meal_keyboard.add(
        types.KeyboardButton("🍳 Завтрак"),
        types.KeyboardButton("🍽 Ужин"),
        types.KeyboardButton("🛒 Корзина"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=meal_keyboard)

@bot.message_handler(func=lambda m: m.text == "🛒 Корзина")
def show_cart(message):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT dish, meal_type FROM orders WHERE user_id=?", (message.chat.id,))
    items = cursor.fetchall()
    conn.close()
    if not items:
        bot.send_message(message.chat.id, "Корзина пуста.", reply_markup=types.ReplyKeyboardRemove())
        return
    total = sum(FOOD_MENU[meal_type][dish]["price"] for dish, meal_type in items)
    cart_text = "🛒 Ваш заказ:\n" + "\n".join([f"- {dish} ({meal_type.capitalize()}) - {FOOD_MENU[meal_type][dish]['price']}₽" for dish, meal_type in items])
    cart_text += f"\n\n💰 Итого: {total}₽"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("✅ Подтвердить заказ"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, cart_text, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "✅ Подтвердить заказ")
def confirm_order(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(*[types.KeyboardButton(time) for time in TIME_SLOTS["breakfast"] + TIME_SLOTS["dinner"]])
    markup.add(types.KeyboardButton("⏰ Другое время"))
    bot.send_message(message.chat.id, "Выберите время доставки:", reply_markup=markup)
    bot.register_next_step_handler(message, handle_delivery_time)

def handle_delivery_time(message):
    if message.text == "⏰ Другое время":
        bot.send_message(message.chat.id, "Укажите время в формате ЧЧ:ММ:")
        bot.register_next_step_handler(message, save_custom_time)
    else:
        save_order(message)

def save_custom_time(message):
    if not re.match(r"^\d{2}:\d{2}$", message.text):
        bot.send_message(message.chat.id, "❌ Некорректный формат времени!")
        return
    save_order(message, custom_time=message.text)

def save_order(message, custom_time=None):
    user_id = message.chat.id
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT dish, meal_type FROM orders WHERE user_id=?", (user_id,))
    items = cursor.fetchall()
    order_text = f"🛎️ Новый заказ!\n👤 Пользователь: {user_id}\n"
    for dish, meal_type in items:
        order_text += f"🍽️ {meal_type.capitalize()} - {dish}\n"
    if custom_time:
        order_text += f"⏰ Время: {custom_time}\n"
    else:
        order_text += f"⏰ Время: {message.text}\n"
    bot.send_message(OWNER_ID, order_text)
    cursor.execute("DELETE FROM orders WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    bot.send_message(user_id, "✅ Заказ отправлен хозяевам!", reply_markup=types.ReplyKeyboardRemove())
    start(message)

@bot.message_handler(func=lambda m: m.text == "🌆 Город")
def handle_city(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'Город'.")
    city_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    city_submenu.add(
        types.KeyboardButton("🏛️ Музей Карельского фронта"),
        types.KeyboardButton("🚖 Такси"),
        types.KeyboardButton("🏥 Больница"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(
        message.chat.id,
        "🌆 Г. Беломорск, Республика Карелия:\n"
        "Население: ~12 000 чел.\n"
        "Штаб Карельского фронта во время ВОВ находился здесь.",
        reply_markup=city_submenu
    )

@bot.message_handler(func=lambda m: m.text == "🏛️ Музей Карельского фронта")
def handle_museum(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'Музей'.")
    try:
        with open("photos/museum_carpathian_front.jpg", "rb") as photo:
            bot.send_photo(
                message.chat.id,
                photo,
                caption="🏛️ Музей Карельского фронта\n📍 Адрес: г. Беломорск, ул. Банковская, д. 26"
            )
    except FileNotFoundError:
        bot.send_message(message.chat.id, "❌ Фото музея не найдено.")
    go_back_to_city(message)

@bot.message_handler(func=lambda m: m.text == "🚖 Такси")
def handle_taxi(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'Такси'.")
    bot.send_message(
        message.chat.id,
        "🚖 Такси:\n"
        "Телефон такси: +7-999-999-99-99",
        reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[[types.KeyboardButton("🔙 Назад")]])
    )

@bot.message_handler(func=lambda m: m.text == "🏥 Больница")
def handle_hospital(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'Больница'.")
    bot.send_message(
        message.chat.id,
        "🏥 Больница:\n"
        "Адрес: г. Беломорск, ул. Больничная, д. 1",
        reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[[types.KeyboardButton("🔙 Назад")]])
    )

@bot.message_handler(func=lambda m: m.text == "🛍️ Сувениры")
def handle_souvenirs(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'Сувениры'.")
    souvenir_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    souvenir_submenu.add(
        types.KeyboardButton("🧲 Магнит на холодильник"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(
        message.chat.id,
        "🛍️ Сувениры:",
        reply_markup=souvenir_submenu
    )

@bot.message_handler(func=lambda m: m.text == "🧲 Магнит на холодильник")
def handle_magnet(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'Магнит'.")
    try:
        with open("photos/souvenir_magnet.jpg", "rb") as photo:
            bot.send_photo(
                message.chat.id,
                photo,
                caption="🧲 Магнит на холодильник (50 гр) - 100р"
            )
    except FileNotFoundError:
        bot.send_message(message.chat.id, "❌ Фото магнита не найдено.")
    go_back_to_city(message)

@bot.message_handler(func=lambda m: m.text == "🚴 Прокат велосипедов")
def bike_rental(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'Прокат велосипедов'.")
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🚲 Велосипед 1"),
        types.KeyboardButton("🚲 Велосипед 2"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(message.chat.id, "Выберите велосипед:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in BIKE_MENU)
def show_bike_details(message):
    logger.info(f"Пользователь {message.chat.id} выбрал '{message.text}'.")
    bike = BIKE_MENU[message.text]
    try:
        with open(f"photos/{bike['photo']}", "rb") as photo:
            bot.send_photo(
                message.chat.id,
                photo,
                caption=f"🚲 {message.text}\n"
                        f"Цены:\n"
                        f"- 1 час: {bike['price_hour']}₽\n"
                        f"- Целый день: {bike['price_day']}₽"
            )
    except FileNotFoundError:
        bot.send_message(message.chat.id, f"🚲 {message.text}\n"
                                        f"Цены:\n"
                                        f"- 1 час: {bike['price_hour']}₽\n"
                                        f"- Целый день: {bike['price_day']}₽")
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("✅ Забронировать"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "Забронировать?", reply_markup=markup)
    bot.register_next_step_handler(message, confirm_bike_rental)

def confirm_bike_rental(message):
    if message.text == "✅ Забронировать":
        conn = sqlite3.connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO bike_rentals (user_id, bike_type, rent_time) VALUES (?, ?, ?)",
            (message.chat.id, message.text, "Не указано")
        )
        conn.commit()
        conn.close()
        bot.send_message(OWNER_ID, f"🚴 Новый прокат от @{message.from_user.username}!")
        bot.send_message(message.chat.id, "✅ Велосипед забронирован. Хозяин свяжется с вами.", reply_markup=types.ReplyKeyboardRemove())
    start(message)

@bot.message_handler(func=lambda m: m.text == "Обратная связь")
def handle_feedback(message):
    logger.info(f"Пользователь {message.chat.id} начал обратную связь.")
    bot.send_message(
        message.chat.id,
        "💬 Здесь можно оставить обратную связь:\n"
        "Расскажите, что можно улучшить или что доставило дискомфорт.\n"
        "Напишите ваше сообщение и нажмите '✅ Отправить'."
    )
    bot.register_next_step_handler(message, send_feedback)

def send_feedback(message):
    user_message = message.text
    logger.info(f"Пользователь {message.chat.id} отправил обратную связь: {user_message}")
    message_text = f"📬 Новая обратная связь:\n{user_message}"
    bot.send_message(OWNER_ID, message_text)
    bot.send_message(
        message.chat.id,
        "✅ Сообщение отправлено хозяевам!",
        reply_markup=types.ReplyKeyboardRemove()
    )
    start(message)

@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
def go_back(message):
    logger.info(f"Пользователь {message.chat.id} вернулся в главное меню.")
    main_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main_keyboard.add(
        types.KeyboardButton("🏠 О доме"),
        types.KeyboardButton("🌆 Город"),
        types.KeyboardButton("🛍️ Сувениры"),
        types.KeyboardButton("🚴 Прокат велосипедов"),
        types.KeyboardButton("Обратная связь")
    )
    bot.send_message(message.chat.id, "Выберите нужный раздел:", reply_markup=main_keyboard)

def go_back_to_city(message):
    city_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    city_submenu.add(
        types.KeyboardButton("🌆 Город"),
        types.KeyboardButton("🏛️ Музей Карельского фронта"),
        types.KeyboardButton("🚖 Такси"),
        types.KeyboardButton("🏥 Больница"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(message.chat.id, "Выберите раздел:", reply_markup=city_submenu)

# ================= ФЛЭШ-МАРШРУТЫ =================
@app.route("/")
def index():
    return "Telegram-бот работает!", 200

@app.route(f"/{TOKEN}", methods=["POST", "HEAD"])
def webhook():
    if request.method == "POST":
        try:
            update = types.Update.de_json(request.get_json(force=True))  # Используем force=True для надежного парсинга
            bot.process_new_updates([update])
            logger.info("Вебхук получил обновление и обработал его.")
        except Exception as e:
            logger.error(f"Ошибка обработки вебхука: {str(e)}")
    return "", 200

@app.route("/ping")
def ping():
    logger.info("Получен ping-запрос.")
    return "OK", 200

# ================= ЗАПУСК СЕРВИСА =================
def self_ping():
    while True:
        try:
            response = requests.get(f"{RENDER_URL}/ping")
            logger.info(f"Self-ping: Status {response.status_code}")
        except Exception as e:
            logger.error(f"Ошибка self-ping: {str(e)}")
        threading.Event().wait(300)

if __name__ == "__main__":
    # Запуск Flask-сервера
    port = int(os.getenv("PORT", 8000))  # Используем порт, который назначает Render
    app.run(host="0.0.0.0", port=port)
    
    # Запуск автопинга
    ping_thread = threading.Thread(target=self_ping, daemon=True)
    ping_thread.start()
