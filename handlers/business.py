import asyncio
import os
import sqlite3
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

PHOTO_TTL_SECONDS = int(os.getenv('PHOTO_TTL_SECONDS', '10'))

def get_owner_user_id(conn, business_connection_id):
    if not business_connection_id:
        return None
    c = conn.cursor()
    c.execute("SELECT user_id FROM business_connections WHERE connection_id = ?", (business_connection_id,))
    row = c.fetchone()
    return row[0] if row else None


async def delete_message_after_delay(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay: int) -> None:
    """Удаляет сообщение бота через заданное число секунд."""
    try:
        await asyncio.sleep(delay)
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        print(f"Can't auto-delete message {message_id} in chat {chat_id}: {e}")


async def send_self_destructing_photo(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    photo_path: str,
    caption: str | None = None,
    ttl_seconds: int = PHOTO_TTL_SECONDS,
) -> None:
    """Отправляет фото и планирует его автоудаление."""
    with open(photo_path, 'rb') as photo:
        sent_message = await context.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
        )

    if ttl_seconds > 0:
        asyncio.create_task(
            delete_message_after_delay(
                context=context,
                chat_id=chat_id,
                message_id=sent_message.message_id,
                delay=ttl_seconds,
            )
        )

async def handle_regular_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    owner_chat = update.message.chat_id
    text = update.message.text or '<не текст>'
    await context.bot.send_message(
        chat_id=owner_chat,
        text=f"🟢 Новое сообщение от собеседника:\n{text}"
    )

async def handle_regular_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.edited_message:
        return

    owner_chat = update.edited_message.chat_id
    new_text = update.edited_message.text or '<не текст>'
    await context.bot.send_message(
        chat_id=owner_chat,
        text=f"✏️ Сообщение отредактировано:\n{new_text}"
    )

async def handle_business_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для business_connection: сохранение нового соединения в БД."""
    business_connection = update.business_connection
    if not business_connection:
        return

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO business_connections (connection_id, user_id, connected_at) VALUES (?, ?, ?)",
                  (business_connection.id, business_connection.user.id, business_connection.date))
        conn.commit()
    except Exception as e:
        print(f"Error saving business connection: {e}")
    finally:
        conn.close()

async def handle_business_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для business_message: сохранение сообщения и скачивание медиафайлов."""
    business_message = update.business_message
    if not business_message:
        return

    # бизнес-подключение может прийти в update.business_connection или только в message.business_connection_id
    business_connection_id = None
    if update.business_connection:
        business_connection_id = update.business_connection.id
    elif getattr(business_message, 'business_connection_id', None):
        business_connection_id = business_message.business_connection_id
    else:
        print('Warning: business_message received without business_connection, skipping')
        return

    # Определение типа контента и file_id
    content_type = 'text'
    file_id = None
    text = business_message.text or business_message.caption

    if business_message.photo:
        content_type = 'photo'
        file_id = business_message.photo[-1].file_id  # Последнее фото (наивысшее качество)
    elif business_message.document:
        content_type = 'document'
        file_id = business_message.document.file_id
    elif business_message.audio:
        content_type = 'audio'
        file_id = business_message.audio.file_id
    elif business_message.video:
        content_type = 'video'
        file_id = business_message.video.file_id
    elif business_message.voice:
        content_type = 'voice'
        file_id = business_message.voice.file_id
    elif business_message.video_note:
        content_type = 'video_note'
        file_id = business_message.video_note.file_id
    elif business_message.sticker:
        content_type = 'sticker'
        file_id = business_message.sticker.file_id
    # Добавьте другие типы по необходимости

    file_path = None
    if file_id:
        try:
            file = await context.bot.get_file(file_id)
            # Генерация пути для сохранения
            file_extension = os.path.splitext(file.file_path)[1] if file.file_path else ''
            file_path = f"storage/{file_id}{file_extension}"
            os.makedirs('storage', exist_ok=True)
            await file.download_to_drive(file_path)
        except Exception as e:
            print(f"Error downloading file {file_id}: {e}")
            file_path = None

    # Сохранение в БД
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO messages (
            business_connection_id, message_id, chat_id, from_user_id, content_type, text, file_id, file_path, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            business_connection_id, business_message.message_id, business_message.chat.id,
            business_message.from_user.id if business_message.from_user else None,
            content_type, text, file_id, file_path, business_message.date
        ))
        conn.commit()
    except Exception as e:
        print(f"Error saving message: {e}")
    finally:
        conn.close()

async def handle_deleted_business_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для deleted_business_messages: отправка содержимого удалённых сообщений администратору."""
    deleted_event = update.deleted_business_messages
    if not deleted_event:
        return

    business_connection_id = None
    if update.business_connection:
        business_connection_id = update.business_connection.id
    elif hasattr(update, 'business_message') and update.business_message and getattr(update.business_message, 'business_connection_id', None):
        business_connection_id = update.business_message.business_connection_id
    else:
        print('Warning: deleted_business_messages received without business_connection, will try fallback by message_id')
    business_connection_id = deleted_event.business_connection_id
    message_ids = deleted_event.message_ids

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        for msg_id in message_ids:
            if business_connection_id:
                c.execute("SELECT content_type, text, file_path, chat_id FROM messages WHERE business_connection_id = ? AND message_id = ?",
                          (business_connection_id, msg_id))
            else:
                c.execute("SELECT content_type, text, file_path, chat_id, business_connection_id FROM messages WHERE message_id = ?",
                          (msg_id,))
            row = c.fetchone()
            if row:
                if business_connection_id:
                    content_type, text, file_path, chat_id = row
                else:
                    content_type, text, file_path, chat_id, business_connection_id = row

                owner_id = get_owner_user_id(conn, business_connection_id)
                target_chat = owner_id or chat_id

                text_to_send = f"🗑 Удалено\nID: {msg_id}\nТип: {content_type}\nТекст: {text or 'Нет текста'}"

                # Отправка пользователю, под чей бизнес-аккаунт подключён бот
                try:
                    if file_path and os.path.exists(file_path):
                        if content_type == 'photo':
                            await send_self_destructing_photo(
                                context=context,
                                chat_id=target_chat,
                                photo_path=file_path,
                                caption=text_to_send,
                            )
                        else:
                            with open(file_path, 'rb') as f:
                                await context.bot.send_document(chat_id=target_chat, document=f, caption=text_to_send)
                    else:
                        await context.bot.send_message(chat_id=target_chat, text=text_to_send)
                except Exception as e:
                    print(f"Can't notify owner {target_chat}: {e}")

                if business_connection_id:
                    c.execute("UPDATE messages SET is_deleted = 1 WHERE business_connection_id = ? AND message_id = ?", (business_connection_id, msg_id))
                else:
                    c.execute("UPDATE messages SET is_deleted = 1 WHERE message_id = ?", (msg_id,))
            else:
                missing_text = f"🗑 Удалено сообщение {msg_id}, но запись не найдена в БД"
                target_chat = owner_id if 'owner_id' in locals() and owner_id else chat_id
                # await context.bot.send_message(chat_id=target_chat, text=missing_text) # Опционально, чтобы не спамить
        conn.commit()
    except Exception as e:
        print(f"Error handling deleted messages: {e}")
    finally:
        conn.close()

async def handle_edited_business_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для edited_business_message: сохранение истории правок и уведомление администратора."""
    edited_message = update.edited_business_message
    if not edited_message:
        return
    
    # Пытаемся получить ID соединения из разных мест
    business_connection_id = getattr(update.business_connection, 'id', None) or getattr(edited_message, 'business_connection_id', None)

    if not business_connection_id:
        print('Warning: edited_business_message received without business_connection, skipping')
        return

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        # Найти оригинальное сообщение
        c.execute("SELECT text, file_id, chat_id, edit_count FROM messages WHERE business_connection_id = ? AND message_id = ?",
                  (business_connection_id, edited_message.message_id))
        row = c.fetchone()
        if not row:
            return

        old_text, old_file_id, chat_id, edit_count = row

        # Новая версия
        new_text = edited_message.text or edited_message.caption
        new_file_id = None
        if edited_message.photo:
            new_file_id = edited_message.photo[-1].file_id
        elif edited_message.document:
            new_file_id = edited_message.document.file_id
        elif edited_message.audio:
            new_file_id = edited_message.audio.file_id
        elif edited_message.video:
            new_file_id = edited_message.video.file_id
        elif edited_message.voice:
            new_file_id = edited_message.voice.file_id
        elif edited_message.video_note:
            new_file_id = edited_message.video_note.file_id
        elif edited_message.sticker:
            new_file_id = edited_message.sticker.file_id

        # Сохранить старую версию в message_edits
        c.execute("""INSERT INTO message_edits (
            message_id, chat_id, old_text, new_text, old_file_id, new_file_id, edited_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)""", (
            edited_message.message_id, chat_id, old_text, new_text, old_file_id, new_file_id, edited_message.edit_date
        ))

        # Обновить оригинальное сообщение
        new_edit_count = (edit_count or 0) + 1
        c.execute("UPDATE messages SET text = ?, file_id = ?, edit_count = ? WHERE business_connection_id = ? AND message_id = ?",
                  (new_text, new_file_id, new_edit_count, business_connection_id, edited_message.message_id))
        conn.commit()

        # Отправить уведомления владельцу и администратору
        owner_id = get_owner_user_id(conn, business_connection_id)
        target_chat = owner_id or chat_id

        user = edited_message.from_user.full_name if edited_message.from_user else 'Неизвестный'
        timestamp = edited_message.edit_date.strftime('%Y-%m-%d %H:%M:%S')
        notification_text = f"""✏️ Сообщение отредактировано
👤 От: {user}  |  💬 Чат: {chat_id}
━━━━━━━━━━━━━━
Было: {old_text or 'Нет текста'}
Стало: {new_text or 'Нет текста'}
━━━━━━━━━━━━━━
🕐 {timestamp}  |  Правка #{new_edit_count}"""

        # В чат владельца (или в chat_id, если нет owner_id)
        try:
            await context.bot.send_message(chat_id=target_chat, text=notification_text)
        except Exception as ex:
            print(f"Can't send edit notification to target {target_chat}: {ex}")

    except Exception as e:
        print(f"Error handling edited message: {e}")
    finally:
        conn.close()
