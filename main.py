import os
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, TypeHandler, CallbackQueryHandler

# Принудительная загрузка .env из папки со скриптом
env_path = Path(__file__).resolve().parent / '.env'
if not env_path.exists():
    raise FileNotFoundError(f".env not found at {env_path}")
load_dotenv(env_path)


# Импорт хендлеров
from handlers.business import (
    handle_business_connection,
    handle_business_message,
    handle_deleted_business_messages,
    handle_edited_business_message,
    handle_regular_message,
    handle_regular_edited_message
)
from handlers.admin import (
    history_command,
    deleted_command,
    connections_command,
    edits_command,
    diff_command,
    start_command,
    help_callback_handler,
    stats_command
)
from database.models import init_db

# Переменные окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///database.db')

print(f"DEBUG: loading .env at {env_path}")
print('DEBUG: BOT_TOKEN', 'SET' if os.getenv('BOT_TOKEN') else 'NOT SET')
print('DEBUG: DATABASE_URL', os.getenv('DATABASE_URL'))

if not BOT_TOKEN:
    raise RuntimeError('BOT_TOKEN is required. Add it to .env or as an environment variable.')

def main():
    # Инициализация БД
    init_db()

    # Создание приложения
    app = Application.builder().token(BOT_TOKEN).build()

    # Регистрация хендлеров для бизнес-сообщений
    async def handle_all_business(update, context):
        # Диагностика: что за update приходит
        try:
            print('DEBUG update:', update)
            # для удобного .to_dict() - может быть тяжело большой, но полезно
            print('DEBUG update as dict:', update.to_dict() if hasattr(update, 'to_dict') else None)
        except Exception as e:
            print('DEBUG print update failed:', e)

        if getattr(update, 'business_connection', None):
            await handle_business_connection(update, context)
        if getattr(update, 'business_message', None):
            await handle_business_message(update, context)
        if getattr(update, 'deleted_business_messages', None):
            await handle_deleted_business_messages(update, context)
        if getattr(update, 'edited_business_message', None):
            await handle_edited_business_message(update, context)

        # Обработчики для обычных сообщений (fallback)
        if update.message:
            await handle_regular_message(update, context)
        if update.edited_message:
            await handle_regular_edited_message(update, context)

    # Регистрация команд администратора
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(help_callback_handler, pattern='^help_instruction$'))
    app.add_handler(CommandHandler("history", history_command))
    app.add_handler(CommandHandler("deleted", deleted_command))
    app.add_handler(CommandHandler("connections", connections_command))
    app.add_handler(CommandHandler("edits", edits_command))
    app.add_handler(CommandHandler("diff", diff_command))
    app.add_handler(CommandHandler("stats", stats_command))

    # Глобальный обработчик всех событий (бизнес-сообщения, удаления, правки).
    # Добавляем В КОНЦЕ, чтобы он не перехватывал команды админа.
    app.add_handler(TypeHandler(Update, handle_all_business))

    # Запуск в polling (локальная отладка)
    print("Бот запущен в режиме polling.")

    app.run_polling()

    # Для webhook-режима используйте код ниже, вместо run_polling():
    # print("Бот запущен в режиме webhook.")
    # await app.run_webhook(
    #     listen="0.0.0.0",
    #     port=8443,
    #     url_path=BOT_TOKEN,
    #     webhook_url=f"https://yourdomain.com/{BOT_TOKEN}"
    # )

if __name__ == '__main__':
    main()