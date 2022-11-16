import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram.ext.filters import BaseFilter

from rss import get_parsed_feed

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
async def add_command(update: Update, _):
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
    await update.message.reply_text('List:\n' + '\n'.join(user_feeds))


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


@handler_decorator
async def fetch_command(update: Update, _):
    entries_list = []

    feeds_urls = data_dict[update.effective_user.id]
    for url in feeds_urls:
        feed_obj = get_parsed_feed(url)
        parsed_entries = feed_obj.entries
        entries_list.extend(parsed_entries)

    entries_list.sort(key=lambda x: datetime.datetime.fromisoformat(x.published), reverse=True)

    result_msg_str = ''

    for i in range(len(entries_list)):
        entry = entries_list[i]
        entry_id = entry.id
        entry_link = entry.link
        entry_published = datetime.datetime.fromisoformat(entry.published)
        entry_title = entry.title
        entry_content = entry.content

        result_msg_str += f"[{i}]({entry_link}) {entry_title}\n"

    await update.message.reply_text(
        result_msg_str,
        parse_mode=ParseMode.MARKDOWN
    )


TOKEN = open('.token').read()
print(TOKEN)

commands_funcs_mapping = {
    "add": add_command,
    "list": list_command,
    "del": del_command,
    "fetch": fetch_command,
}

app = ApplicationBuilder().token(TOKEN).build()

for command_string, func in commands_funcs_mapping.items():
    app.add_handler(
        CommandHandler(command_string, list_command)
    )

app.add_handler(MessageHandler(filters.TEXT, plain_text))
app.run_polling()
