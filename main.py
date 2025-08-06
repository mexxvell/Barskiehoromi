import telebot
from telebot import types
from flask import Flask, request
import os
from dotenv import load_dotenv
from datetime import datetime
import json

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
bot = telebot.TeleBot(BOT_TOKEN)

app = Flask(__name__)

# Хранилище данных
users = set()
cart = {}

# Главное меню
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("👥 Команда", "🌍 Путешествия")
    markup.row("🧘 Кундалини‑йога", "📸 Медиа")
    markup.row("🛍 Мерч", "🎁 Доп. услуги")
    return markup

# Назад кнопка
def back_button():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔙 Назад")
    return markup

# Старт
@bot.message_handler(commands=["start"])
def start_message(message):
    users.add(message.chat.id)
    bot.send_message(message.chat.id, "👋 Добро пожаловать!", reply_markup=main_menu())

# Обработчик текстовых сообщений
@bot.message_handler(func=lambda msg: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text

    if text == "🔙 Назад":
        bot.send_message(chat_id, "Главное меню:", reply_markup=main_menu())

    elif text == "👥 Команда":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("📌 О Бренде", "🌐 Источники")
        markup.add("🔙 Назад")
        msg = (
            "Нас зовут Алексей Бабенко — учитель кундалини-йоги, визионер, путешественник, кинематографист, медиа продюсер. "
            "Более 20 лет личной практики кундалини-йоги, 18 лет ведения занятий. Преподаватель учительского тренинга школы "
            "Амрит Нам Саровар (Франция) в России. Создатель проекта авторских путешествий Йога-кемп, организатор йога-туров, "
            "ретритов и путешествий по Карелии, Северной Осетии, Грузии, Армении и Турции.\n\n"
            "Анастасия Голик — сертифицированный инструктор хатха-йоги, аромапрактик, идейный вдохновитель, "
            "а также кормилеца групп на выездах и ретритах кемпа."
        )
        bot.send_message(chat_id, msg, reply_markup=markup)

    elif text == "📌 О Бренде":
        msg = (
            "ScanDream - https://t.me/scandream - зарегистрированный товарный знак, основная идея которого — осознанные творческие коммуникации.\n\n"
            "ScanDream — это место, где мы пересобираем конструкт Мира, рассматривая и восхищаясь его строением. Быть #scandream — это сканировать своё "
            "жизненное предназначение действием и мечтой.\n\n"
            "Проект йога-кемп — это творческая интеграция опыта и пользы. Пользы через новые знания и умения. Умения через новые формы."
        )
        bot.send_message(chat_id, msg)

    elif text == "🌐 Источники":
        msg = (
            "ОФИЦИАЛЬНЫЕ ИСТОЧНИКИ взаимодействия с командой ScanDream:\n"
            "1. Алексей ВК — https://vk.ru/scandream\n"
            "2. Анастасия ВК — https://vk.ru/yoga.golik\n"
            "3. ScanDream•Live ТГ — https://t.me/scandream\n"
            "4. Алексей ТГ — https://t.me/scandreamlife\n"
            "5. Анастасия ТГ — https://t.me/yogagolik_dnevnik\n"
            "6. Йога с Алексеем ВК — https://vk.ru/kyogababenko"
        )
        bot.send_message(chat_id, msg)

    elif text == "🌍 Путешествия":
        bot.send_message(chat_id, "🧭 Авторские туры и ретриты по разным уголкам мира.", reply_markup=back_button())

    elif text == "🧘 Кундалини‑йога":
        bot.send_message(chat_id, "🕉 Практика кундалини-йоги, трансформация через дыхание и движение.", reply_markup=back_button())

    elif text == "📸 Медиа":
        bot.send_message(chat_id, "📷 Вдохновляющие фото и видео с наших мероприятий.", reply_markup=back_button())

    elif text == "🎁 Доп. услуги":
        bot.send_message(chat_id, "🎒 Всё для вашего комфорта во время путешествий и ретритов.", reply_markup=back_button())

    elif text == "🛍 Мерч":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("👕 Футболка", "🧢 Кепка")
        markup.row("🎽 Майка", "🛒 Корзина")
        markup.add("🔙 Назад")
        bot.send_message(chat_id, "Выберите товар:", reply_markup=markup)

    elif text in ["👕 Футболка", "🧢 Кепка", "🎽 Майка"]:
        item = text.split(" ")[1]
        photo_path = f"images/{item.lower()}.jpg"
        try:
            with open(photo_path, 'rb') as photo:
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.row(f"🛒 Заказать {item}")
                markup.add("🔙 Назад")
                bot.send_photo(chat_id, photo, caption=f"{item} от ScanDream", reply_markup=markup)
        except:
            bot.send_message(chat_id, "Фото временно недоступно.", reply_markup=back_button())

    elif text.startswith("🛒 Заказать"):
        item = text.split(" ")[2]
        msg = bot.send_message(chat_id, f"Сколько {item} вы хотите заказать?")
        bot.register_next_step_handler(msg, lambda m: add_to_cart(m, item))

    elif text == "🛒 Корзина":
        user_cart = cart.get(chat_id, {})
        if not user_cart:
            bot.send_message(chat_id, "🧺 Ваша корзина пуста.", reply_markup=back_button())
        else:
            items = [f"{k}: {v} шт." for k, v in user_cart.items()]
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("📩 Отправить заказ", "🔙 Назад")
            bot.send_message(chat_id, "🛍 Ваша корзина:\n" + "\n".join(items), reply_markup=markup)

    elif text == "📩 Отправить заказ":
        user_cart = cart.get(chat_id, {})
        if not user_cart:
            bot.send_message(chat_id, "Корзина пуста.")
        else:
            items = "\n".join(f"{k}: {v} шт." for k, v in user_cart.items())
            bot.send_message(chat_id, "✅ Спасибо за ваш заказ!")
            bot.send_message(ADMIN_ID, f"🛒 Новый заказ от @{message.from_user.username or message.from_user.id}:\n{items}")
            cart[chat_id] = {}

    else:
        bot.send_message(chat_id, "Выберите раздел из меню 👇", reply_markup=main_menu())

# Добавление товара в корзину
def add_to_cart(message, item):
    try:
        qty = int(message.text)
        if qty <= 0:
            raise ValueError
        user_cart = cart.setdefault(message.chat.id, {})
        user_cart[item] = user_cart.get(item, 0) + qty
        bot.send_message(message.chat.id, f"✅ Добавлено в корзину: {item} — {qty} шт.", reply_markup=main_menu())
    except:
        bot.send_message(message.chat.id, "Введите корректное количество.")

# Ежедневная статистика
@app.route("/daily_stats", methods=["GET"])
def daily_stats():
    if ADMIN_ID:
        bot.send_message(ADMIN_ID, f"📊 Уникальных пользователей за всё время: {len(users)}")
    return "OK", 200

# Вебхук/пуллинг
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    bot.process_new_messages([telebot.types.Update.de_json(request.stream.read().decode("utf-8")).message])
    return "OK", 200

@app.route("/")
def index():
    return "Бот работает", 200

if __name__ == "__main__":
    bot.polling(none_stop=True)
