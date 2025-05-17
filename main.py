import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# Константы
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OWNER_ID = os.getenv('OWNER_TELEGRAM_ID')  # Telegram ID владельца

# Словари
TIME_SLOTS = {
    'breakfast': ['08:00', '09:00', '10:00'],
    'dinner': ['18:00', '19:00', '20:00']
}

FOOD_MENU = {
    'breakfast': {
        '🥞 Яичница': 'omelette',
        '🧇 Блины': 'pancakes',
        '🍵 Чай': 'tea'
    },
    'dinner': {
        '🍲 Суп 1': 'soup1',
        '🍲 Суп 2': 'soup2',
        '🍖 Пюре с мясом': 'meat_puree'
    }
}

PHOTO_PATHS = {
    'main': 'photos/main_photo.jpg',
    'room1': 'photos/room1.jpg',
    'room2': 'photos/room2.jpg'
}

# Стартовая команда
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏛️ Достопримечательности", callback_data='attractions')],
        [InlineKeyboardButton("🛏️ Комната 1", callback_data='room1')],
        [InlineKeyboardButton("🛏️ Комната 2", callback_data='room2')],
        [InlineKeyboardButton("🛍️ Купить сувениры", callback_data='souvenirs')]
    ])

    with open(PHOTO_PATHS['main'], 'rb') as photo:
        await update.message.reply_photo(
            photo=photo,
            caption="👋 Добро пожаловать в наш дом! 🏡\nВыберите нужный раздел:",
            reply_markup=keyboard
        )

# Обработчик выбора комнаты
async def choose_room(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    room_number = query.data[-1]
    context.user_data['room'] = room_number

    with open(PHOTO_PATHS[f'room{room_number}'], 'rb') as photo:
        await query.message.reply_photo(photo=photo)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🍳 Завтрак", callback_data='breakfast')],
        [InlineKeyboardButton("🍽️ Ужин", callback_data='dinner')]
    ])
    await query.message.reply_text("Выберите, что бы вы хотели:", reply_markup=keyboard)

# Обработчик выбора типа еды
async def choose_meal_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    meal_type = query.data
    context.user_data['meal_type'] = meal_type

    menu = FOOD_MENU[meal_type]
    buttons = [[InlineKeyboardButton(text, callback_data=value)] for text, value in menu.items()]
    keyboard = InlineKeyboardMarkup(buttons)
    await query.message.reply_text("Выберите блюдо:", reply_markup=keyboard)

# Обработчик выбора блюда
async def choose_food(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    food_choice = query.data
    meal_type = context.user_data['meal_type']
    context.user_data['food_choice'] = food_choice

    time_slots = TIME_SLOTS[meal_type]
    buttons = [[InlineKeyboardButton(slot, callback_data=slot)] for slot in time_slots]
    keyboard = InlineKeyboardMarkup(buttons)
    await query.message.reply_text("Выберите удобное время:", reply_markup=keyboard)

# Обработчик выбора времени
async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    time_choice = query.data

    # Сообщение клиенту
    await query.message.reply_text("✅ Ваш заказ отправлен хозяевам дома!")

    # Сообщение владельцу
    room = context.user_data['room']
    meal_type = context.user_data['meal_type']
    food = next(k for k, v in FOOD_MENU[meal_type].items() if v == context.user_data['food_choice'])

    message = (
        f"🛎️ Новый заказ!\n"
        f"🛏️ Комната: {room}\n"
        f"🍽️ Тип: {meal_type.capitalize()}\n"
        f"🍲 Блюдо: {food}\n"
        f"⏰ Время: {time_choice}"
    )
    await context.bot.send_message(chat_id=OWNER_ID, text=message)

# Основной запуск
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(choose_room, pattern=r'room[12]'))
    app.add_handler(CallbackQueryHandler(choose_meal_type, pattern=r'(breakfast|dinner)'))
    app.add_handler(CallbackQueryHandler(choose_food, pattern=r'(omelette|pancakes|tea|soup1|soup2|meat_puree)'))
    app.add_handler(CallbackQueryHandler(confirm_order, pattern=r'\d{2}:\d{2}'))

    app.run_polling()

if __name__ == '__main__':
    main()