import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CallbackContext,
    ConversationHandler,
)

from config import TOKEN, TG_ID_DEVELOPER
from states import *
from questions import *

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

user_data = {}


async def start(update: Update, context: CallbackContext) -> int:
    """Начало опроса."""
    user_id = update.message.from_user.id
    user_data[user_id] = {"answers": {}}  

    welcome_message = (
        "🌟 Добро пожаловать в мой опрос! 🌟\n\n"
        "В некоторых вопросах можно выбрать несколько вариантов ответа.\n\n"
        "Если вы не нашли подходящий ответ, выберите <b>«Свой вариант»</b> и отправьте текст или голосовое сообщение.\n\n"
        "Нажмите кнопку ниже, чтобы начать!"
    )

    keyboard = [
        [InlineKeyboardButton("🚀 Начать опрос 🚀", callback_data="start_poll")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        welcome_message, reply_markup=reply_markup, parse_mode="HTML"
    )
    return WAITING_FOR_START


async def handle_start_button(update: Update, context: CallbackContext) -> int:
    """Обработка нажатия кнопки 'Начать опрос'."""
    query = update.callback_query
    await query.answer()

    # Начинаем опрос с первого вопроса
    await ask_question(update, context, QUESTION_0)
    return QUESTION_0


async def ask_question(update: Update, context: CallbackContext, question_id: int):
    """Задать вопрос в зависимости от его типа."""
    question_data = QUESTIONS[question_id]
    context.user_data["current_question_id"] = question_id
    chat_id = update.effective_chat.id

    if question_data["type"] == "choice":
        options = question_data["options"]
        keyboard = [
            [InlineKeyboardButton(options[i], callback_data=f"{question_id}_{i}")]
            for i in range(0, len(options))
        ]

        if question_id != QUESTION_3:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "✅ Ответить ✅", callback_data=f"{question_id}_done"
                    )
                ]
            )

        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=chat_id, text=question_data["text"], reply_markup=reply_markup
        )
    else:
        await context.bot.send_message(chat_id=chat_id, text=question_data["text"])


async def handle_choice(update: Update, context: CallbackContext) -> int:
    """Обработка выбора пользователя (для вопросов с вариантами)."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    current_callback = query.data
    last_callback = context.user_data.get("last_callback")

    if current_callback == last_callback:
        return

    context.user_data["last_callback"] = current_callback
    question_id, option_id = query.data.split("_")
    question_id = int(question_id)

    context.user_data["current_question_id"] = question_id

    if option_id == "done":
        next_question_id = question_id + 1
        if next_question_id in QUESTIONS:
            await ask_question(update, context, next_question_id)
            return next_question_id  # Возвращаем новое состояние
        else:
            await send_results_to_admin(update, context)
            return ConversationHandler.END
    else:
        # Пользователь выбрал вариант ответа
        option_id = int(option_id)
        selected_option = QUESTIONS[question_id]["options"][option_id]

        if selected_option == "Свой вариант ответа":
            await query.message.reply_text(
                "Пожалуйста, введите ваш вариант ответа текстом или отправьте голосовое сообщение."
            )
            return question_id

        if f"question_{question_id}" not in user_data[user_id]["answers"]:
            user_data[user_id]["answers"][f"question_{question_id}"] = []

        if question_id == QUESTION_3:
            user_data[user_id]["answers"][f"question_{question_id}"] = [selected_option]
        else:
            if (
                selected_option
                not in user_data[user_id]["answers"][f"question_{question_id}"]
            ):
                user_data[user_id]["answers"][f"question_{question_id}"].append(
                    selected_option
                )

        options = QUESTIONS[question_id]["options"]
        keyboard = [
            [
                InlineKeyboardButton(
                    f"{'✔ ' if option in user_data[user_id]['answers'][f'question_{question_id}'] else ''}{option}",
                    callback_data=f"{question_id}_{i}",
                )
            ]
            for i, option in enumerate(options)
        ]

        if question_id != QUESTION_3:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "✅ Ответить ✅", callback_data=f"{question_id}_done"
                    )
                ]
            )

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=f"{QUESTIONS[question_id]['text']}\n\nВы выбрали: {', '.join(user_data[user_id]['answers'][f'question_{question_id}'])}",
            reply_markup=reply_markup,
        )

        if question_id == QUESTION_3:
            next_question_id = question_id + 1
            if next_question_id in QUESTIONS:
                await ask_question(update, context, next_question_id)
                return next_question_id  # Возвращаем новое состояние
            else:
                await send_results_to_admin(update, context)
                return ConversationHandler.END

        return question_id


async def handle_text_or_voice(update: Update, context: CallbackContext) -> int:
    """Обработка текстового или голосового ответа."""
    user_id = update.message.from_user.id
    current_question_id = context.user_data.get("current_question_id")

    if current_question_id is None:
        await update.message.reply_text(
            "Что-то пошло не так. Пожалуйста, начните опрос заново с помощью /start."
        )
        return ConversationHandler.END

    if update.message.text:
        user_response = update.message.text
    elif update.message.voice:
        user_response = (
            f"[Голосовое сообщение] (file_id: {update.message.voice.file_id})"
        )

        question_text = QUESTIONS[current_question_id]["text"]
        await context.bot.send_message(
            chat_id=TG_ID_DEVELOPER,
            text=f"Голосовое сообщение к вопросу:\n\n{question_text}",
        )
        await context.bot.forward_message(
            chat_id=TG_ID_DEVELOPER,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id,
        )
    else:
        await update.message.reply_text(
            "Пожалуйста, отправьте текстовое или голосовое сообщение."
        )
        return current_question_id

    if f"question_{current_question_id}" not in user_data[user_id]["answers"]:
        user_data[user_id]["answers"][f"question_{current_question_id}"] = []

    user_data[user_id]["answers"][f"question_{current_question_id}"].append(
        f"{user_response}"
    )

    next_question_id = current_question_id + 1
    if next_question_id in QUESTIONS:
        await ask_question(update, context, next_question_id)
        return next_question_id
    else:
        await send_results_to_admin(update, context)
        return ConversationHandler.END


async def send_results_to_admin(update: Update, context: CallbackContext):
    """Отправка результатов админу."""
    user_id = (
        update.message.from_user.id
        if update.message
        else update.callback_query.from_user.id
    )
    user = (
        update.message.from_user if update.message else update.callback_query.from_user
    )

    user_info = (
        f"ID пользователя: {user.id}\n"
        f"Username: @{user.username if user.username else 'не указан'}\n"
        f"Имя: {user.first_name if user.first_name else 'не указано'}\n\n"
    )

    results = "Результаты опроса:\n\n"
    for question_id in QUESTIONS:
        question_text = QUESTIONS[question_id]["text"]
        answer = user_data[user_id]["answers"].get(
            f"question_{question_id}", "Нет ответа"
        )
        if isinstance(answer, list):
            answer = ", ".join(answer)  
        results += f"{question_text}\nОтвет: {answer}\n\n"

    await context.bot.send_message(chat_id=TG_ID_DEVELOPER, text=user_info + results)

    for question_id in QUESTIONS:
        answer = user_data[user_id]["answers"].get(f"question_{question_id}")
        if isinstance(answer, str) and "Голосовое сообщение" in answer:
            file_id = answer.split("file_id: ")[1].strip(")")
            question_text = QUESTIONS[question_id]["text"]
            await context.bot.send_message(
                chat_id=TG_ID_DEVELOPER,
                text=f"Голосовое сообщение к вопросу:\n\n{question_text}",
            )
            await context.bot.forward_message(
                chat_id=TG_ID_DEVELOPER,
                from_chat_id=user_id,
                message_id=update.message.message_id,
            )

    thank_you_message = "Спасибо за ваше время! Вы просто космос! 🚀"

    chat_id = update.effective_chat.id
    await context.bot.send_message(chat_id=chat_id, text=thank_you_message)


async def cancel(update: Update, context: CallbackContext) -> int:
    """Отмена опроса."""
    await update.message.reply_text("Опрос отменен.")
    return ConversationHandler.END


def get_current_question_id(user_id):
    """Получить текущий вопрос для пользователя."""
    for question_id in QUESTIONS:
        if f"question_{question_id}" not in user_data[user_id]["answers"]:
            return question_id
    return None

async def handle_start_during_conversation(update: Update, context: CallbackContext):
    """Обработка команды /start во время опроса."""
    user_id = update.message.from_user.id
    if user_id in user_data:
        del user_data[user_id] 
    return await start(update, context)


def main():
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_START: [CallbackQueryHandler(handle_start_button)],
            QUESTION_0: [
                CallbackQueryHandler(handle_choice),
                MessageHandler(filters.TEXT | filters.VOICE, handle_text_or_voice),
            ],
            QUESTION_1: [
                CallbackQueryHandler(handle_choice),
                MessageHandler(filters.TEXT | filters.VOICE, handle_text_or_voice),
            ],
            QUESTION_2: [
                CallbackQueryHandler(handle_choice),
                MessageHandler(filters.TEXT | filters.VOICE, handle_text_or_voice),
            ],
            QUESTION_3: [
                CallbackQueryHandler(handle_choice),
                MessageHandler(filters.TEXT | filters.VOICE, handle_text_or_voice),
            ],
            QUESTION_4: [
                MessageHandler(filters.TEXT | filters.VOICE, handle_text_or_voice)
            ],
            QUESTION_5: [
                MessageHandler(filters.TEXT | filters.VOICE, handle_text_or_voice)
            ],
            QUESTION_6: [
                MessageHandler(filters.TEXT | filters.VOICE, handle_text_or_voice)
            ],
            QUESTION_7: [
                MessageHandler(filters.TEXT | filters.VOICE, handle_text_or_voice)
            ],
            QUESTION_8: [
                MessageHandler(filters.TEXT | filters.VOICE, handle_text_or_voice)
            ],
            QUESTION_9: [
                CallbackQueryHandler(handle_choice),
                MessageHandler(filters.TEXT | filters.VOICE, handle_text_or_voice),
            ],
            QUESTION_10: [
                MessageHandler(filters.TEXT | filters.VOICE, handle_text_or_voice)
            ],
            QUESTION_11: [
                MessageHandler(filters.TEXT | filters.VOICE, handle_text_or_voice)
            ],
            QUESTION_12: [
                MessageHandler(filters.TEXT | filters.VOICE, handle_text_or_voice)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", handle_start_during_conversation),
        ],
    )

    application.add_handler(conv_handler)
    application.run_polling()


if __name__ == "__main__":
    main()
