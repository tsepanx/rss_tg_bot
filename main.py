from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram.ext.filters import BaseFilter

data_dict: dict[int, list] = {}

def handler_decorator(func):
    async def wrapper(update: Update, *args, **kwargs):
        if update.message:
            user_id = update.message.from_user.id

            if user_id not in data_dict:
                data_dict[user_id] = []

        await func(update, *args, **kwargs)
        print(data_dict)

    return wrapper

@handler_decorator
async def subscribe_command(update: Update, _):
    print(update.effective_user.id)
    try:
        rss_link = update.message.text.split(' ')[1]
        data_dict[update.effective_user.id].append(rss_link)

        await update.message.reply_text(f"Subscribed {rss_link}")
    except Exception:
        await update.message.reply_text(f"Error subscribing")

@handler_decorator
async def list_command(update: Update, _):
    user_feeds = data_dict[update.effective_user.id]
    await update.message.reply_text('\n'.join(user_feeds))

@handler_decorator
async def del_command(update: Update, _):
    try:
        rss_link = update.message.text.split(' ')[1]
        data_dict[update.effective_user.id].remove(rss_link)
        await update.message.reply_text(f"Removed {rss_link}")
    except Exception:
        await update.message.reply_text(f"Error removing")

@handler_decorator
async def plain_text(update: Update, _):
    text = update.message.text
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# import schedule
# schedule.every().week.at()


TOKEN = open('.token').read()
print(TOKEN)

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("add", subscribe_command))
app.add_handler(CommandHandler("list", list_command))
app.add_handler(CommandHandler("del", del_command))
app.add_handler(MessageHandler(filters.TEXT, plain_text))

app.run_polling()
