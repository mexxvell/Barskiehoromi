import os
import logging
import requests
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
RENDER_URL = os.getenv("RENDER_URL", "https://barskiehoromi.onrender.com")

# Проверка переменных окружения
if not all([TOKEN, OWNER_ID, RENDER_URL]):
    raise EnvironmentError("Не заданы обязательные переменные окружения!")

# Флэш-приложение
app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)

# Установка вебхука (программно)
WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# ================= ОБРАБОТЧИКИ КОМАНД =================
@bot.message_handler(commands=["start"])
def start(message):
    logger.info(f"Пользователь {message.chat.id} начал работу с ботом.")
    main_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main_keyboard.add(
        types.KeyboardButton("🏠 О доме"),
        types.KeyboardButton("🌆 Город"),
        types.KeyboardButton("🛍️ Сувениры"),
        types.KeyboardButton("Обратная связь"),
        types.KeyboardButton("🛎 Помощь")
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
def choose_food(message):
    meal_type = "breakfast" if message.text in FOOD_MENU["breakfast"] else "dinner"
    logger.info(f"Пользователь {message.chat.id} выбрал блюдо {message.text}.")
    time_slots = TIME_SLOTS[meal_type]
    buttons = [types.KeyboardButton(slot) for slot in time_slots]
    buttons.append(types.KeyboardButton("🔙 Назад"))
    bot.send_message(message.chat.id, "Выберите удобное время:", reply_markup=types.ReplyKeyboardMarkup(keyboard=[buttons], resize_keyboard=True))

@bot.message_handler(func=lambda m: m.text in TIME_SLOTS["breakfast"] or m.text in TIME_SLOTS["dinner"])
def confirm_order(message):
    user_id = message.chat.id
    meal_type = "breakfast" if message.text in TIME_SLOTS["breakfast"] else "dinner"
    food = next(k for k, v in FOOD_MENU[meal_type].items() if k == message.text)
    logger.info(f"Пользователь {user_id} подтвердил заказ: {food}, {message.text}.")
    bot.send_message(
        user_id,
        "✅ Ваш заказ отправлен хозяевам дома!",
        reply_markup=types.ReplyKeyboardRemove()
    )
    message_text = (
        f"🛎️ Новый заказ!\n"
        f"👤 Пользователь: {user_id}\n"
        f"🍽️ Тип: {meal_type.capitalize()}\n"
        f"🍲 Блюдо: {food}\n"
        f"⏰ Время: {message.text}"
    )
    bot.send_message(OWNER_ID, message_text)

@bot.message_handler(func=lambda m: m.text == "🌆 Город")
def handle_city(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'Город'.")
    city_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    city_submenu.add(types.KeyboardButton("🏛️ Достопримечательности"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(
        message.chat.id,
        "🌆 Г. Беломорск, Республика Карелия:\n"
        "Население: ~12 000 чел.\n"
        "Штаб Карельского фронта во время ВОВ находился здесь.",
        reply_markup=city_submenu
    )

@bot.message_handler(func=lambda m: m.text == "🏛️ Достопримечательности")
def handle_attractions(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'Достопримечательности'.")
    attractions_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    attractions_submenu.add(types.KeyboardButton("🏛️ Музей Карельского фронта"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(
        message.chat.id,
        "🏛️ Выберите достопримечательность:",
        reply_markup=attractions_submenu
    )

@bot.message_handler(func=lambda m: m.text == "🏛️ Музей Карельского фронта")
def handle_museum(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'Музей'.")
    with open("photos/museum_carpathian_front.jpg", "rb") as photo:
        bot.send_photo(
            message.chat.id,
            photo,
            caption="🏛️ Музей Карельского фронта\n📍 Адрес: г. Беломорск, ул. Банковская, д. 26"
        )
    main_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main_keyboard.add(
        types.KeyboardButton("🏠 О доме"),
        types.KeyboardButton("🛍️ Сувениры"),
        types.KeyboardButton("Обратная связь"),
        types.KeyboardButton("🛎 Помощь")
    )
    bot.send_message(message.chat.id, "Выберите нужный раздел:", reply_markup=main_keyboard)

@bot.message_handler(func=lambda m: m.text == "🛍️ Сувениры")
def handle_souvenirs(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'Сувениры'.")
    souvenir_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    souvenir_submenu.add(types.KeyboardButton("🧲 Магнит на холодильник"), types.KeyboardButton("🔙 Назад"))
    bot.send_message(
        message.chat.id,
        "🛍️ Сувениры:",
        reply_markup=souvenir_submenu
    )

@bot.message_handler(func=lambda m: m.text == "🧲 Магнит на холодильник")
def handle_magnet(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'Магнит'.")
    with open("photos/souvenir_magnet.jpg", "rb") as photo:
        bot.send_photo(
            message.chat.id,
            photo,
            caption="🧲 Магнит на холодильник (50 гр) - 100р"
        )
    main_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main_keyboard.add(
        types.KeyboardButton("🏠 О доме"),
        types.KeyboardButton("🛍️ Сувениры"),
        types.KeyboardButton("Обратная связь"),
        types.KeyboardButton("🛎 Помощь")
    )
    bot.send_message(message.chat.id, "Выберите нужный раздел:", reply_markup=main_keyboard)

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

@bot.message_handler(func=lambda m: m.text == "🛎 Помощь")
def handle_help(message):
    logger.info(f"Пользователь {message.chat.id} выбрал 'Помощь'.")
    help_submenu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    help_submenu.add(
        types.KeyboardButton("🚖 Такси"),
        types.KeyboardButton("🏥 Больница"),
        types.KeyboardButton("🔙 Назад")
    )
    bot.send_message(
        message.chat.id,
        "🛎️ Помощь:\n"
        "Здесь можно найти важную информацию о городе и услугах.",
        reply_markup=help_submenu
    )

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

@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
def go_back(message):
    logger.info(f"Пользователь {message.chat.id} вернулся в главное меню.")
    main_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    main_keyboard.add(
        types.KeyboardButton("🏠 О доме"),
        types.KeyboardButton("🌆 Город"),
        types.KeyboardButton("🛍️ Сувениры"),
        types.KeyboardButton("Обратная связь"),
        types.KeyboardButton("🛎 Помощь")
    )
    bot.send_message(message.chat.id, "Выберите нужный раздел:", reply_markup=main_keyboard)

# ================= ФЛЭШ-МАРШРУТЫ =================
@app.route("/")
def index():
    return "Telegram-бот работает!", 200

@app.route(f"/{TOKEN}", methods=["POST", "HEAD"])
def webhook():
    if request.method == "POST":
        try:
            update = types.Update.de_json(request.get_data(as_text=True))
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
    port = int(os.getenv("PORT", 8000))  # Используйте порт, который назначает Render
    app.run(host="0.0.0.0", port=port)
    
    # Запуск автопинга
    ping_thread = threading.Thread(target=self_ping, daemon=True)
    ping_thread.start()
