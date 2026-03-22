import os
import difflib
import sqlite3
from telegram import Update
from telegram.ext import ContextTypes

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /history {chat_id} — показать историю переписки."""
    if not context.args:
        await update.message.reply_text("Укажите chat_id: /history <chat_id>")
        return

    user_id = update.effective_user.id
    try:
        chat_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный chat_id.")
        return

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        # Выбираем сообщения только если они принадлежат бизнес-соединению этого пользователя
        query = """
            SELECT m.from_user_id, m.text, m.timestamp 
            FROM messages m
            JOIN business_connections bc ON m.business_connection_id = bc.connection_id
            WHERE m.chat_id = ? AND bc.user_id = ? AND m.is_deleted = 0 
            ORDER BY m.timestamp
        """
        c.execute(query, (chat_id, user_id))
        rows = c.fetchall()
        if not rows:
            await update.message.reply_text("Сообщений не найдено.")
            return

        response = f"История переписки для чата {chat_id}:\n\n"
        for row in rows[-20:]:  # Последние 20 для краткости
            user_id, text, timestamp = row
            response += f"[{timestamp}] {user_id}: {text or '[Медиа]'}\n"
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")
    finally:
        conn.close()

async def deleted_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /deleted — показать последние удалённые сообщения."""
    user_id = update.effective_user.id
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        query = """
            SELECT m.chat_id, m.from_user_id, m.text, m.timestamp 
            FROM messages m
            JOIN business_connections bc ON m.business_connection_id = bc.connection_id
            WHERE bc.user_id = ? AND m.is_deleted = 1 
            ORDER BY m.timestamp DESC LIMIT 10
        """
        c.execute(query, (user_id,))
        rows = c.fetchall()
        if not rows:
            await update.message.reply_text("Удалённых сообщений не найдено.")
            return

        response = "Последние удалённые сообщения:\n\n"
        for row in rows:
            chat_id, user_id, text, timestamp = row
            response += f"[{timestamp}] Чат {chat_id}, Пользователь {user_id}: {text or '[Медиа]'}\n"
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")
    finally:
        conn.close()

async def connections_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /connections — список активных бизнес-соединений."""
    user_id = update.effective_user.id
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        c.execute("SELECT connection_id, user_id, connected_at FROM business_connections WHERE user_id = ?", (user_id,))
        rows = c.fetchall()
        if not rows:
            await update.message.reply_text("Активных соединений не найдено.")
            return

        response = "Активные бизнес-соединения:\n\n"
        for row in rows:
            connection_id, user_id, connected_at = row
            response += f"ID: {connection_id}, Пользователь: {user_id}, Подключено: {connected_at}\n"
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")
    finally:
        conn.close()

async def edits_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /edits {message_id} — показать всю историю правок."""
    if not context.args:
        await update.message.reply_text("Укажите message_id: /edits <message_id>")
        return

    try:
        message_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный message_id.")
        return

    user_id = update.effective_user.id
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        # Проверяем, принадлежит ли сообщение пользователю
        query = """
            SELECT me.old_text, me.new_text, me.edited_at 
            FROM message_edits me
            JOIN messages m ON me.message_id = m.message_id
            JOIN business_connections bc ON m.business_connection_id = bc.connection_id
            WHERE me.message_id = ? AND bc.user_id = ?
            ORDER BY me.edited_at
        """
        c.execute(query, (message_id, user_id))
        rows = c.fetchall()
        if not rows:
            await update.message.reply_text("Правок не найдено.")
            return

        response = f"История правок для сообщения {message_id}:\n\n"
        for row in rows:
            old_text, new_text, edited_at = row
            response += f"[{edited_at}]\nБыло: {old_text or 'Нет текста'}\nСтало: {new_text or 'Нет текста'}\n\n"
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")
    finally:
        conn.close()

async def diff_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /diff {message_id} — показать diff между первой и последней версией."""
    if not context.args:
        await update.message.reply_text("Укажите message_id: /diff <message_id>")
        return

    try:
        message_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Неверный message_id.")
        return

    user_id = update.effective_user.id
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        # Получить текущий текст
        query_last = """
            SELECT m.text 
            FROM messages m
            JOIN business_connections bc ON m.business_connection_id = bc.connection_id
            WHERE m.message_id = ? AND bc.user_id = ?
        """
        c.execute(query_last, (message_id, user_id))
        row = c.fetchone()
        if not row:
            await update.message.reply_text("Сообщение не найдено.")
            return
        last_text = row[0] or ""

        # Получить первую версию
        # Здесь не обязательно join, так как message_id уже проверен выше
        c.execute("SELECT old_text FROM message_edits WHERE message_id = ? ORDER BY edited_at LIMIT 1", (message_id,))
        edit_row = c.fetchone()
        first_text = edit_row[0] if edit_row else last_text

        # Создать diff
        diff = list(difflib.ndiff(first_text.split(), last_text.split()))
        result = []
        for line in diff:
            if line.startswith('- '):
                result.append(f"~~{line[2:]}~~")
            elif line.startswith('+ '):
                result.append(f"++{line[2:]}++")
            elif line.startswith('  '):
                result.append(line[2:])

        diff_text = ' '.join(result)
        response = f"Diff для сообщения {message_id}:\n\n{diff_text}"
        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")
    finally:
        conn.close()