import os
import sqlite3
from datetime import datetime
from html import escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes


def get_owner_user_id(conn, business_connection_id):
    if not business_connection_id:
        return None
    c = conn.cursor()
    c.execute(
        "SELECT user_id FROM business_connections WHERE connection_id = ?",
        (business_connection_id,),
    )
    row = c.fetchone()
    return row[0] if row else None


def format_text_block(text: str | None, empty_text: str = "Без текста") -> str:
    value = (text or "").strip()
    if not value:
        value = empty_text
    return escape(value).replace("\n", "<br>")


def is_delete_reply_command(text: str | None) -> bool:
    command = ((text or "").strip().split(maxsplit=1) or [""])[0]
    if not command.startswith("/"):
        return False
    return command.split("@", 1)[0].lower() in {"/del", "/delete", "/rm", "/save"}


def is_save_command(text: str | None) -> bool:
    command = ((text or "").strip().split(maxsplit=1) or [""])[0]
    if not command.startswith("/"):
        return False
    return command.split("@", 1)[0].lower() == "/save"


def build_card_message(
    icon: str,
    title: str,
    user_name: str | None = None,
    username: str | None = None,
    sections: list[tuple[str, str | None]] | None = None,
    footer: str | None = None,
) -> str:
    parts = [f"{icon} <b>{escape(title)}</b>"]

    if user_name or username:
        safe_name = escape(user_name or "Неизвестный пользователь")
        if username:
            parts.append(
                f"Пользователь: <b>{safe_name}</b>\nЮзернейм: @{escape(username)}"
            )
        else:
            parts.append(
                f"Пользователь: <b>{safe_name}</b>\nЮзернейм: <i>не указан</i>"
            )

    if sections:
        for label, value in sections:
            parts.append(f"{escape(label)}:\n<blockquote>{format_text_block(value)}</blockquote>")

    if footer:
        parts.append(f"<i>{escape(footer)}</i>")

    return "\n\n".join(parts)


async def handle_regular_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    owner_chat = update.message.chat_id
    text = update.message.text or "Без текста"
    await context.bot.send_message(
        chat_id=owner_chat,
        text=build_card_message(
            icon="💬",
            title="Новое сообщение",
            user_name=update.message.from_user.full_name if update.message.from_user else None,
            username=update.message.from_user.username if update.message.from_user else None,
            sections=[("Текст", text)],
        ),
        parse_mode="HTML",
    )


async def handle_regular_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.edited_message:
        return

    owner_chat = update.edited_message.chat_id
    new_text = update.edited_message.text or "Без текста"
    await context.bot.send_message(
        chat_id=owner_chat,
        text=build_card_message(
            icon="✏️",
            title="Сообщение изменено",
            user_name=update.edited_message.from_user.full_name if update.edited_message.from_user else None,
            username=update.edited_message.from_user.username if update.edited_message.from_user else None,
            sections=[("Новый текст", new_text)],
        ),
        parse_mode="HTML",
    )


async def handle_business_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для business_connection: сохранение нового соединения в БД."""
    business_connection = update.business_connection
    if not business_connection:
        return

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO business_connections (connection_id, user_id, connected_at) VALUES (?, ?, ?)",
            (business_connection.id, business_connection.user.id, business_connection.date),
        )
        conn.commit()
    except Exception as e:
        print(f"Error saving business connection: {e}")
    finally:
        conn.close()


async def handle_business_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для business_message: сохранение сообщений и обработка команд."""
    business_message = update.business_message
    if not business_message:
        return

    business_connection_id = None
    if update.business_connection:
        business_connection_id = update.business_connection.id
    elif getattr(business_message, "business_connection_id", None):
        business_connection_id = business_message.business_connection_id
    else:
        print("Warning: business_message received without business_connection, skipping")
        return

    conn = sqlite3.connect("database.db")
    owner_id = get_owner_user_id(conn, business_connection_id)
    conn.close()

    reply_to_message = getattr(business_message, "reply_to_message", None)
    is_owner_message = bool(
        business_message.from_user and business_message.from_user.id == owner_id
    )
    is_save_reply = (
        is_owner_message
        and reply_to_message is not None
        and is_save_command(business_message.text)
    )

    if is_save_reply:
        try:
            await context.bot.delete_business_messages(
                business_connection_id=business_connection_id,
                message_ids=[business_message.message_id],
            )
        except Exception as e:
            print(f"Error deleting /save command: {e}")

    source_message = reply_to_message if is_save_reply else business_message

    content_type = "text"
    file_id = None
    text = source_message.text or source_message.caption
    is_protected = getattr(source_message, "has_protected_content", False)

    if source_message.photo:
        content_type = "photo"
        file_id = source_message.photo[-1].file_id
    elif source_message.document:
        content_type = "document"
        file_id = source_message.document.file_id
    elif source_message.audio:
        content_type = "audio"
        file_id = source_message.audio.file_id
    elif source_message.video:
        content_type = "video"
        file_id = source_message.video.file_id
    elif source_message.voice:
        content_type = "voice"
        file_id = source_message.voice.file_id
    elif source_message.video_note:
        content_type = "video_note"
        file_id = source_message.video_note.file_id
    elif source_message.sticker:
        content_type = "sticker"
        file_id = source_message.sticker.file_id

    file_path = None
    download_error = None
    if file_id:
        try:
            file = await context.bot.get_file(file_id)
            file_extension = os.path.splitext(file.file_path)[1] if file.file_path else ""
            file_path = f"storage/{file_id}{file_extension}"
            os.makedirs("storage", exist_ok=True)
            await file.download_to_drive(file_path)
        except Exception as e:
            print(f"Error downloading file {file_id}: {e}")
            download_error = str(e)
            file_path = None

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    try:
        c.execute(
            """INSERT INTO messages (
            business_connection_id, message_id, chat_id, from_user_id, content_type, text, file_id, file_path, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                business_connection_id,
                business_message.message_id,
                business_message.chat.id,
                business_message.from_user.id if business_message.from_user else None,
                "text",
                business_message.text or business_message.caption,
                None,
                None,
                business_message.date,
            ),
        )
        conn.commit()
    except Exception as e:
        print(f"Error saving message: {e}")
    finally:
        conn.close()

    if owner_id and is_save_reply:
        sender = source_message.from_user or business_message.from_user
        sender_name = sender.full_name if sender else None

        if file_path and os.path.exists(file_path):
            try:
                caption_text = build_card_message(
                    icon="📥",
                    title="Поймано медиа",
                    user_name=sender_name,
                    username=sender.username if sender else None,
                    sections=[("Подпись", text)] if text else None,
                )

                with open(file_path, "rb") as f:
                    if content_type == "photo":
                        await context.bot.send_photo(
                            chat_id=owner_id, photo=f, caption=caption_text, parse_mode="HTML"
                        )
                    elif content_type == "video":
                        await context.bot.send_video(
                            chat_id=owner_id, video=f, caption=caption_text, parse_mode="HTML"
                        )
                    elif content_type == "voice":
                        await context.bot.send_voice(
                            chat_id=owner_id, voice=f, caption=caption_text, parse_mode="HTML"
                        )
                    elif content_type == "video_note":
                        await context.bot.send_video_note(chat_id=owner_id, video_note=f)
                    elif content_type == "audio":
                        await context.bot.send_audio(
                            chat_id=owner_id, audio=f, caption=caption_text, parse_mode="HTML"
                        )
                    elif content_type == "document":
                        await context.bot.send_document(
                            chat_id=owner_id, document=f, caption=caption_text, parse_mode="HTML"
                        )
                    elif content_type == "sticker":
                        await context.bot.send_sticker(chat_id=owner_id, sticker=f)
            except Exception as e:
                print(f"Error forwarding saved media to owner: {e}")
        elif file_id and download_error:
            try:
                failure_reason = (
                    "Файл защищен: Telegram API не дает скачать такое view once медиа."
                    if is_protected
                    else f"Ошибка загрузки: {download_error}"
                )
                sections = [("Причина", failure_reason)]
                if text:
                    sections.append(("Подпись", text))

                error_text = build_card_message(
                    icon="⚠️",
                    title="Медиа не сохранено",
                    user_name=sender_name,
                    username=sender.username if sender else None,
                    sections=sections,
                )
                await context.bot.send_message(chat_id=owner_id, text=error_text, parse_mode="HTML")
            except Exception as e:
                print(f"Error sending error notification: {e}")
        else:
            try:
                saved_text = build_card_message(
                    icon="💾",
                    title="Сохранено сообщение",
                    user_name=sender_name,
                    username=sender.username if sender else None,
                    sections=[("Текст", text)],
                )
                await context.bot.send_message(chat_id=owner_id, text=saved_text, parse_mode="HTML")
            except Exception as e:
                print(f"Error sending saved text message: {e}")

    if (
        is_owner_message
        and reply_to_message is not None
        and is_delete_reply_command(business_message.text)
        and not is_save_command(business_message.text)
    ):
        try:
            await context.bot.delete_business_messages(
                business_connection_id=business_connection_id,
                message_ids=[reply_to_message.message_id, business_message.message_id],
            )
        except Exception as e:
            print(f"Error deleting business messages via command: {e}")


async def handle_deleted_business_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для deleted_business_messages: отправка содержимого удаленных сообщений администратору."""
    deleted_event = update.deleted_business_messages
    if not deleted_event:
        return

    business_connection_id = deleted_event.business_connection_id
    message_ids = deleted_event.message_ids
    event_chat_id = deleted_event.chat.id

    conn = sqlite3.connect("database.db")
    owner_id = get_owner_user_id(conn, business_connection_id)
    c = conn.cursor()

    try:
        for msg_id in message_ids:
            c.execute(
                "SELECT content_type, text, file_path, chat_id, from_user_id FROM messages WHERE business_connection_id = ? AND message_id = ?",
                (business_connection_id, msg_id),
            )
            row = c.fetchone()

            target_chat = owner_id or event_chat_id

            if row:
                content_type, text, file_path, db_chat_id, from_user_id = row

                user_name = "Неизвестный"
                user_handle_str = ""
                button_url = None

                if from_user_id:
                    try:
                        chat_info = await context.bot.get_chat(from_user_id)
                        user_name = chat_info.full_name
                        if chat_info.username:
                            user_handle_str = chat_info.username
                            button_url = f"https://t.me/{chat_info.username}"
                        else:
                            button_url = f"tg://user?id={from_user_id}"
                    except Exception:
                        user_name = "Пользователь"
                        button_url = f"tg://user?id={from_user_id}"

                text_to_send = build_card_message(
                    icon="♻️",
                    title="Сообщение удалено",
                    user_name=user_name,
                    username=user_handle_str or None,
                    sections=[("Удаленный текст", text or "Только медиа")],
                )

                reply_markup = None
                if button_url:
                    reply_markup = InlineKeyboardMarkup(
                        [[InlineKeyboardButton("💬 Перейти в чат", url=button_url)]]
                    )

                try:
                    if file_path and os.path.exists(file_path):
                        with open(file_path, "rb") as f:
                            if content_type == "photo":
                                await context.bot.send_photo(
                                    chat_id=target_chat,
                                    photo=f,
                                    caption=text_to_send,
                                    parse_mode="HTML",
                                    reply_markup=reply_markup,
                                )
                            elif content_type == "video":
                                await context.bot.send_video(
                                    chat_id=target_chat,
                                    video=f,
                                    caption=text_to_send,
                                    parse_mode="HTML",
                                    reply_markup=reply_markup,
                                )
                            elif content_type == "voice":
                                await context.bot.send_voice(
                                    chat_id=target_chat,
                                    voice=f,
                                    caption=text_to_send,
                                    parse_mode="HTML",
                                    reply_markup=reply_markup,
                                )
                            else:
                                await context.bot.send_document(
                                    chat_id=target_chat,
                                    document=f,
                                    caption=text_to_send,
                                    parse_mode="HTML",
                                    reply_markup=reply_markup,
                                )
                    else:
                        await context.bot.send_message(
                            chat_id=target_chat,
                            text=text_to_send,
                            parse_mode="HTML",
                            reply_markup=reply_markup,
                        )
                except Exception as e:
                    print(f"Can't notify owner {target_chat}: {e}")

                c.execute(
                    "UPDATE messages SET is_deleted = 1 WHERE business_connection_id = ? AND message_id = ?",
                    (business_connection_id, msg_id),
                )
            else:
                print(f"Message {msg_id} not found in DB for deletion (skipped).")

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

    business_connection_id = getattr(update.business_connection, "id", None) or getattr(
        edited_message, "business_connection_id", None
    )

    if not business_connection_id:
        print("Warning: edited_business_message received without business_connection, skipping")
        return

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    try:
        c.execute(
            "SELECT text, file_id, chat_id, edit_count FROM messages WHERE business_connection_id = ? AND message_id = ?",
            (business_connection_id, edited_message.message_id),
        )
        row = c.fetchone()
        if not row:
            return

        old_text, old_file_id, chat_id, edit_count = row

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

        c.execute(
            """INSERT INTO message_edits (
            message_id, chat_id, old_text, new_text, old_file_id, new_file_id, edited_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                edited_message.message_id,
                chat_id,
                old_text,
                new_text,
                old_file_id,
                new_file_id,
                edited_message.edit_date,
            ),
        )

        new_edit_count = (edit_count or 0) + 1
        c.execute(
            "UPDATE messages SET text = ?, file_id = ?, edit_count = ? WHERE business_connection_id = ? AND message_id = ?",
            (new_text, new_file_id, new_edit_count, business_connection_id, edited_message.message_id),
        )
        conn.commit()

        owner_id = get_owner_user_id(conn, business_connection_id)
        target_chat = owner_id or chat_id

        user_name = edited_message.from_user.full_name if edited_message.from_user else "Неизвестный"
        username = edited_message.from_user.username if edited_message.from_user else None
        timestamp = edited_message.edit_date.strftime("%H:%M") if edited_message.edit_date else None

        notification_text = build_card_message(
            icon="♻️",
            title="Пользователь изменил(а) сообщение",
            user_name=user_name,
            username=username,
            sections=[
                ("Старый текст", old_text),
                ("Новый текст", new_text),
            ],
            footer=timestamp,
        )

        button_url = f"https://t.me/{username}" if username else None
        if not button_url and edited_message.from_user:
            button_url = f"tg://user?id={edited_message.from_user.id}"
        reply_markup = None
        if button_url:
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton("💬 Перейти в чат", url=button_url)]]
            )

        try:
            await context.bot.send_message(
                chat_id=target_chat,
                text=notification_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        except Exception as ex:
            print(f"Can't send edit notification to target {target_chat}: {ex}")

    except Exception as e:
        print(f"Error handling edited message: {e}")
    finally:
        conn.close()
