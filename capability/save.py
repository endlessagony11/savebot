from telegram import Message
from telegram.ext import ContextTypes

SAVE_COMMAND = "/чотам"

async def cleanup_save_command_message(message: Message, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Удаляет командное сообщение /чотам, когда оно отправлено в ответ на другое сообщение."""
    if not message or not message.text:
        return False

    if message.text.strip() != SAVE_COMMAND:
        return False

    if not getattr(message, 'reply_to_message', None):
        return False

    try:
        await context.bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        print(f"✓ Deleted save command message {message.message_id} in chat {message.chat.id}")
        return True
    except Exception as e:
        print(f"Warning: failed deleting save command message {message.message_id}: {e}")
        return False
