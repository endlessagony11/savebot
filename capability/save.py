from telegram import Message
from telegram.ext import ContextTypes

SAVE_COMMAND = "/чотам"


def is_save_command(text: str | None) -> bool:
    if not text:
        return False
    command = text.strip().split(maxsplit=1)[0].split("@", 1)[0].lower()
    return command == SAVE_COMMAND


async def cleanup_save_command_message(
    message: Message, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """Удаляет сообщение с командой /чотам, если оно отправлено ответом на другое сообщение."""
    if not message or not is_save_command(message.text):
        return False

    if not getattr(message, "reply_to_message", None):
        return False

    try:
        business_connection_id = getattr(message, "business_connection_id", None)
        if business_connection_id:
            await context.bot.delete_business_messages(
                business_connection_id=business_connection_id,
                message_ids=[message.message_id],
            )
        else:
            await context.bot.delete_message(
                chat_id=message.chat.id,
                message_id=message.message_id,
            )
        print(f"Deleted чотам command message {message.message_id} in chat {message.chat.id}")
        return True
    except Exception as e:
        print(f"Warning: failed deleting чотам command message {message.message_id}: {e}")
        return False
