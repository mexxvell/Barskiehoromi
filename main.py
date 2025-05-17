import os
import logging
import asyncio
import aiohttp
import threading
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from flask import Flask
from waitress import serve

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_TELEGRAM_ID")
RENDER_URL = os.getenv("RENDER_URL", "https://barskiehoromi.onrender.com")

# Проверка переменных окружения
if not all([TOKEN, RENDER_URL]):
    raise EnvironmentError("Не заданы обязательные переменные окружения!")

# Конфигурации
TIME_SLOTS = {
    "breakfast": ["08:00", "09:00", "10:00"],
    "dinner": ["18:00", "19:00", "20:00"]
}

FOOD_MENU = {
    "breakfast": {
        "🥞 Яичница": "omelette",
        "🧇 Блины": "pancakes",
        "🍵 Чай": "tea"
    },
    "dinner": {
        "🍲 Суп 1": "soup1",
        "🍲 Суп 2": "soup2",
        "🍖 Пюре с мясом": "meat_puree"
    }
}

PHOTO_PATHS = {
    "main": "photos/main_photo.jpg",
    "room1": "photos/room1.jpg",
    "room2": "photos/room2.jpg",
    "museum": "photos/museum_carpathian_front.jpg",
    "souvenir": "photos/souvenir_magnet.jpg"
}

app = Flask(__name__)

@app.route("/ping")
def ping():
    return "OK", 200

# ================= ОБРАБОТЧИКИ КОМАНД =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    main_keyboard = ReplyKeyboardMarkup(
        [
            ["🏛️ Достопримечательности", "🛏️ Комната 1"],
            ["🛏️ Комната 2", "🛍️ Сувенир"]
        ],
        resize_keyboard=True
    )

    with open(PHOTO_PATHS["main"], "rb") as photo:
        await update.message.reply_photo(
            photo=photo,
            caption="👋 Добро пожаловать в наш дом! 🏡\nВыберите нужный раздел:",
            reply_markup=main_keyboard
        )
    context.user_data["current_menu"] = "main"

async def choose_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    room_number = text[-1]
    context.user_data["room"] = room_number
    context.user_data["current_menu"] = "meal"

    with open(PHOTO_PATHS[f"room{room_number}"], "rb") as photo:
        await update.message.reply_photo(photo=photo)

    meal_keyboard = ReplyKeyboardMarkup(
        [
            ["🍳 Завтрак", "🍽️ Ужин"],
            ["🔙 Назад"]
        ],
        resize_keyboard=True
    )
    await update.message.reply_text("Выберите, что бы вы хотели:", reply_markup=meal_keyboard)

async def choose_meal_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Назад":
        await go_back(update, context)
        return

    meal_type_map = {
        "🍳 Завтрак": "breakfast",
        "🍽️ Ужин": "dinner"
    }

    meal_type = meal_type_map.get(text)
    if not meal_type:
        await update.message.reply_text("Неизвестный выбор. Попробуйте ещё раз.")
        return

    context.user_data["meal_type"] = meal_type
    context.user_data["current_menu"] = "food"

    menu = FOOD_MENU[meal_type]
    buttons = [[key] for key in menu.keys()]
    buttons.append(["🔙 Назад"])
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text("Выберите блюдо:", reply_markup=keyboard)

async def choose_food(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Назад":
        await go_back(update, context)
        return

    meal_type = context.user_data["meal_type"]
    food_choice = next(k for k, v in FOOD_MENU[meal_type].items() if k == text)
    context.user_data["food_choice"] = food_choice
    context.user_data["current_menu"] = "time"

    time_slots = TIME_SLOTS[meal_type]
    buttons = [[slot] for slot in time_slots]
    buttons.append(["🔙 Назад"])
    keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text("Выберите удобное время:", reply_markup=keyboard)

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Назад":
        await go_back(update, context)
        return

    time_choice = text.strip()

    await update.message.reply_text("✅ Ваш заказ отправлен хозяевам дома!", reply_markup=ReplyKeyboardRemove())

    room = context.user_data["room"]
    meal_type = context.user_data["meal_type"]
    food = next(k for k, v in FOOD_MENU[meal_type].items() if v == context.user_data["food_choice"])

    message = (
        f"🛎️ Новый заказ!\n"
        f"🛏️ Комната: {room}\n"
        f"🍽️ Тип: {meal_type.capitalize()}\n"
        f"🍲 Блюдо: {food}\n"
        f"⏰ Время: {time_choice}"
    )
    await context.bot.send_message(chat_id=OWNER_ID, text=message)

async def handle_attractions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["current_menu"] = "attractions"
    attractions_keyboard = ReplyKeyboardMarkup(
        [
            ["🏛️ Музей Карельского фронта"],
            ["🔙 Назад"]
        ],
        resize_keyboard=True
    )
    await update.message.reply_text("🏛️ Выберите достопримечательность:", reply_markup=attractions_keyboard)

async def handle_museum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with open(PHOTO_PATHS["museum"], "rb") as photo:
        await update.message.reply_photo(
            photo=photo,
            caption="🏛️ Музей Карельского фронта\n📍 Адрес: г. Беломорск, ул. Банковская, д. 26"
        )
    await update.message.reply_text("Выберите нужный раздел:", reply_markup=ReplyKeyboardMarkup(
        [["🏛️ Достопримечательности", "🛏️ Комната 1"], ["🛏️ Комната 2", "🛍️ Сувенир"]],
        resize_keyboard=True
    ))

async def handle_souvenirs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["current_menu"] = "souvenirs"
    souvenir_keyboard = ReplyKeyboardMarkup(
        [
            ["🧲 Магнит на холодильник"],
            ["🔙 Назад"]
        ],
        resize_keyboard=True
    )
    await update.message.reply_text("🛍️ Выберите сувенир:", reply_markup=souvenir_keyboard)

async def handle_magnet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with open(PHOTO_PATHS["souvenir"], "rb") as photo:
        await update.message.reply_photo(
            photo=photo,
            caption="🧲 Магнит на холодильник"
        )
    await update.message.reply_text("Выберите нужный раздел:", reply_markup=ReplyKeyboardMarkup(
        [["🏛️ Достопримечательности", "🛏️ Комната 1"], ["🛏️ Комната 2", "🛍️ Сувенир"]],
        resize_keyboard=True
    ))

async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_menu = context.user_data.get("current_menu", "main")
    
    if current_menu == "meal":
        main_keyboard = ReplyKeyboardMarkup(
            [
                ["🏛️ Достопримечательности", "🛏️ Комната 1"],
                ["🛏️ Комната 2", "🛍️ Сувенир"]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text("Выберите нужный раздел:", reply_markup=main_keyboard)
        context.user_data["current_menu"] = "main"
    
    elif current_menu in ["attractions", "souvenirs"]:
        main_keyboard = ReplyKeyboardMarkup(
            [
                ["🏛️ Достопримечательности", "🛏️ Комната 1"],
                ["🛏️ Комната 2", "🛍️ Сувенир"]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text("Выберите нужный раздел:", reply_markup=main_keyboard)
        context.user_data["current_menu"] = "main"
    
    elif current_menu == "food":
        meal_keyboard = ReplyKeyboardMarkup(
            [
                ["🍳 Завтрак", "🍽️ Ужин"],
                ["🔙 Назад"]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text("Выберите, что бы вы хотели:", reply_markup=meal_keyboard)
        context.user_data["current_menu"] = "meal"
    
    elif current_menu == "time":
        meal_type = context.user_data["meal_type"]
        menu = FOOD_MENU[meal_type]
        buttons = [[key] for key in menu.keys()]
        buttons.append(["🔙 Назад"])
        keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
        await update.message.reply_text("Выберите блюдо:", reply_markup=keyboard)
        context.user_data["current_menu"] = "food"

# ================= ЗАПУСК СЕРВИСА =================

async def self_ping():
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{RENDER_URL}/ping") as response:
                    logger.info(f"Self-ping: Status {response.status}")
        except Exception as e:
            logger.error(f"Self-ping error: {str(e)}")
        await asyncio.sleep(300)

def run_flask():
    serve(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

async def main():
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex(r"^🛏️ Комната [12]$"), choose_room))
    application.add_handler(MessageHandler(filters.Regex(r"^🍳 Завтрак$|^🍽️ Ужин$"), choose_meal_type))
    application.add_handler(MessageHandler(filters.Regex(r"^🥞 Яичница$|^🧇 Блины$|^🍵 Чай$|^🍲 Суп 1$|^🍲 Суп 2$|^🍖 Пюре с мясом$"), choose_food))
    application.add_handler(MessageHandler(filters.Regex(r"^\d{2}:\d{2}$"), confirm_order))
    application.add_handler(MessageHandler(filters.Regex(r"^🏛️ Достопримечательности$"), handle_attractions))
    application.add_handler(MessageHandler(filters.Regex(r"^🏛️ Музей Карельского фронта$"), handle_museum))
    application.add_handler(MessageHandler(filters.Regex(r"^🛍️ Сувенир$"), handle_souvenirs))
    application.add_handler(MessageHandler(filters.Regex(r"^🧲 Магнит на холодильник$"), handle_magnet))
    application.add_handler(MessageHandler(filters.Regex(r"^🔙 Назад$"), go_back))

    # Настройка вебхука
    WEBHOOK_URL = f"{RENDER_URL}/{TOKEN}"
    await application.bot.set_webhook(WEBHOOK_URL)

    # Запуск задач
    asyncio.create_task(self_ping())
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Запуск бота
    await application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        webhook_url=WEBHOOK_URL,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    asyncio.run(main())