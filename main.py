import os
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_TELEGRAM_ID")  # Telegram ID владельца

# Проверка переменных окружения
if not all([TOKEN, OWNER_ID]):
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
        "🍲 Борщ": "soup1",
        "🍲 Солянка": "soup2",
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

# ================= ОБРАБОТЧИКИ КОМАНД =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    main_keyboard = ReplyKeyboardMarkup(
        [
            ["🏠 О доме", "🌆 Город"],
            ["🛎 Помощь", "Обратная связь"]
        ],
        resize_keyboard=True
    )
    await update.message.reply_text(
        "👋 Добро пожаловать в наш дом! 🏡\n"
        "Правила использования:\n"
        "1) Выберите раздел из меню\n"
        "2) Следуйте инструкциям\n"
        "3) При заказе еды укажите удобное время\n"
        "4) Информация отправится хозяевам\n"
        "5) Они свяжутся для уточнения деталей",
        reply_markup=main_keyboard
    )
    context.user_data["current_menu"] = "main"

async def handle_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with open(PHOTO_PATHS["main"], "rb") as photo:
        await update.message.reply_photo(
            photo=photo,
            caption="🏡 О доме:\n"
                    "Наш дом расположен в живописном месте. Здесь вы найдете уют и комфорт.\n"
                    "Можно заказать еду или получить помощь."
        )
    home_submenu = ReplyKeyboardMarkup(
        [
            ["🍽 Еда"],
            ["🔙 Назад"]
        ],
        resize_keyboard=True
    )
    await update.message.reply_text("Выберите нужный раздел:", reply_markup=home_submenu)
    context.user_data["current_menu"] = "home"

async def handle_food(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["current_menu"] = "food"
    meal_keyboard = ReplyKeyboardMarkup(
        [
            ["🍳 Завтрак", "🍽 Ужин"],
            ["🔙 Назад"]
        ],
        resize_keyboard=True
    )
    await update.message.reply_text(
        "🍽 Меню на завтра:\n"
        "Здесь можно заказать еду на завтрак или ужин.\n"
        "Выберите один из пунктов, и информация будет отправлена хозяевам.",
        reply_markup=meal_keyboard
    )

async def choose_meal_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Назад":
        await go_back(update, context)
        return

    meal_type_map = {
        "🍳 Завтрак": "breakfast",
        "🍽 Ужин": "dinner"
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
    user_id = update.effective_user.id

    await update.message.reply_text("✅ Ваш заказ отправлен хозяевам дома!", reply_markup=ReplyKeyboardRemove())

    meal_type = context.user_data["meal_type"]
    food = next(k for k, v in FOOD_MENU[meal_type].items() if v == context.user_data["food_choice"])

    message = (
        f"🛎️ Новый заказ!\n"
        f"👤 Пользователь: {user_id}\n"
        f"🍽️ Тип: {meal_type.capitalize()}\n"
        f"🍲 Блюдо: {food}\n"
        f"⏰ Время: {time_choice}"
    )
    await update.effective_bot.send_message(chat_id=OWNER_ID, text=message)

async def handle_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["current_menu"] = "city"
    city_submenu = ReplyKeyboardMarkup(
        [
            ["🏛️ Достопримечательности"],
            ["🔙 Назад"]
        ],
        resize_keyboard=True
    )
    await update.message.reply_text(
        "🌆 Г. Беломорск, Республика Карелия:\n"
        "Население: ~12 000 чел.\n"
        "Штаб Карельского фронта во время ВОВ находился здесь.",
        reply_markup=city_submenu
    )

async def handle_attractions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["current_menu"] = "attractions"
    attractions_submenu = ReplyKeyboardMarkup(
        [
            ["🏛️ Музей Карельского фронта"],
            ["🔙 Назад"]
        ],
        resize_keyboard=True
    )
    await update.message.reply_text("🏛️ Выберите достопримечательность:", reply_markup=attractions_submenu)

async def handle_museum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with open(PHOTO_PATHS["museum"], "rb") as photo:
        await update.message.reply_photo(
            photo=photo,
            caption="🏛️ Музей Карельского фронта\n📍 Адрес: г. Беломорск, ул. Банковская, д. 26"
        )
    await update.message.reply_text("Выберите нужный раздел:", reply_markup=ReplyKeyboardMarkup(
        [["🏠 О доме", "🌆 Город", "Обратная связь", "🛎 Помощь"],
         ["🔙 Назад"]],
        resize_keyboard=True
    ))

async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["current_menu"] = "feedback"
    await update.message.reply_text(
        "💬 Здесь можно оставить обратную связь:\n"
        "Расскажите, что можно улучшить или что доставило дискомфорт.\n"
        "Напишите ваше сообщение и нажмите '✅ Отправить'."
    )

async def send_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "current_menu" not in context.user_data or context.user_data["current_menu"] != "feedback":
        await update.message.reply_text("❌ Сначала выберите 'Обратная связь'.")
        return

    user_message = update.message.text
    message = f"📬 Новая обратная связь:\n{user_message}"
    await update.effective_bot.send_message(chat_id=OWNER_ID, text=message)
    await update.message.reply_text("✅ Сообщение отправлено хозяевам!", reply_markup=ReplyKeyboardRemove())

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_submenu = ReplyKeyboardMarkup(
        [
            ["🚖 Такси", "🏥 Больница"],
            ["🔙 Назад"]
        ],
        resize_keyboard=True
    )
    await update.message.reply_text(
        "🛎️ Помощь:\n"
        "Здесь можно найти важную информацию о городе и услугах.",
        reply_markup=help_submenu
    )
    context.user_data["current_menu"] = "help"

async def handle_taxi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚖 Такси:\n"
        "Телефон такси: +7-999-999-99-99",
        reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True)
    )

async def handle_hospital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏥 Больница:\n"
        "Адрес: г. Беломорск, ул. Больничная, д. 1",
        reply_markup=ReplyKeyboardMarkup([["🔙 Назад"]], resize_keyboard=True)
    )

async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_menu = context.user_data.get("current_menu", "main")
    if current_menu == "main":
        return

    if current_menu == "home":
        main_keyboard = ReplyKeyboardMarkup(
            [
                ["🏠 О доме", "🌆 Город"],
                ["🛎 Помощь", "Обратная связь"]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text("Выберите нужный раздел:", reply_markup=main_keyboard)
    elif current_menu == "city":
        city_submenu = ReplyKeyboardMarkup(
            [
                ["🌆 Город", "🏠 О доме"],
                ["Обратная связь", "🛎 Помощь"]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text("🌆 Город:", reply_markup=city_submenu)
    elif current_menu == "food":
        meal_submenu = ReplyKeyboardMarkup(
            [
                ["🍳 Завтрак", "🍽 Ужин"],
                ["🔙 Назад"]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text("Выберите, что бы вы хотели:", reply_markup=meal_submenu)
    elif current_menu == "time":
        meal_type = context.user_data["meal_type"]
        menu = FOOD_MENU[meal_type]
        buttons = [[key] for key in menu.keys()]
        buttons.append(["🔙 Назад"])
        keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
        await update.message.reply_text("Выберите блюдо:", reply_markup=keyboard)
    elif current_menu == "help":
        help_submenu = ReplyKeyboardMarkup(
            [
                ["🚖 Такси", "🏥 Больница"],
                ["🔙 Назад"]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text("🛎️ Помощь:", reply_markup=help_submenu)
    elif current_menu == "feedback":
        main_keyboard = ReplyKeyboardMarkup(
            [
                ["🏠 О доме", "🌆 Город"],
                ["🛎 Помощь", "Обратная связь"]
            ],
            resize_keyboard=True
        )
        await update.message.reply_text("Выберите нужный раздел:", reply_markup=main_keyboard)
        context.user_data["current_menu"] = "main"

# ================= ЗАПУСК СЕРВИСА =================
async def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex(r"^🏠 О доме$"), handle_home))
    application.add_handler(MessageHandler(filters.Regex(r"^🍽 Еда$"), handle_food))
    application.add_handler(MessageHandler(filters.Regex(r"^🍳 Завтрак$|^🍽 Ужин$"), choose_meal_type))
    application.add_handler(MessageHandler(filters.Regex(r"^ pancakes|omelette|tea|soup1|soup2|meat_puree$"), choose_food))
    application.add_handler(MessageHandler(filters.Regex(r"^\d{2}:\d{2}$"), confirm_order))
    application.add_handler(MessageHandler(filters.Regex(r"^🌆 Город$"), handle_city))
    application.add_handler(MessageHandler(filters.Regex(r"^🏛️ Достопримечательности$"), handle_attractions))
    application.add_handler(MessageHandler(filters.Regex(r"^🏛️ Музей Карельского фронта$"), handle_museum))
    application.add_handler(MessageHandler(filters.Regex(r"^Обратная связь$"), handle_feedback))
    application.add_handler(MessageHandler(filters.Regex(r"^✅ Отправить$"), send_feedback))
    application.add_handler(MessageHandler(filters.Regex(r"^🛎 Помощь$"), handle_help))
    application.add_handler(MessageHandler(filters.Regex(r"^🚖 Такси$"), handle_taxi))
    application.add_handler(MessageHandler(filters.Regex(r"^🏥 Больница$"), handle_hospital))
    application.add_handler(MessageHandler(filters.Regex(r"^🔙 Назад$"), go_back))

    # Запуск вебхука
    PORT = int(os.getenv("PORT", 8000))  # Используем порт 8000
    WEBHOOK_URL = f"https://barskiehoromi.onrender.com :{PORT}/{TOKEN}"

    # Установка вебхука
    try:
        await application.bot.set_webhook(WEBHOOK_URL)
    except Exception as e:
        logger.error(f"Ошибка установки вебхука: {e}")
        return

    # Запуск вебхука
    await application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    asyncio.run(main())
