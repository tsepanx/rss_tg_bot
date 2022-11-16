import dataclasses
import datetime
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from functools import wraps
from rss import get_parsed_feed


@dataclasses.dataclass
class FeedDataclass:
    url: str
    last_update_time: Optional[datetime.datetime] = datetime.datetime.min
    # last_item_id: Optional[str] = None

    def __str__(self):
        return self.url


data_dict: dict[int, list[FeedDataclass]] = {}


def handler_decorator(func):
    @wraps(func)
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
        data_dict[update.effective_user.id].append(
            FeedDataclass(rss_link)
        )

        await update.message.reply_text(f"Subscribed {rss_link}")
    except Exception:
        await update.message.reply_text(f"Error subscribing")


@handler_decorator
async def list_command(update: Update, _):
    user_feeds = data_dict[update.effective_user.id]
    await update.message.reply_text('List:\n' + '\n'.join(map(str, user_feeds)))


@handler_decorator
async def del_command(update: Update, _):
    current_chat_feeds = data_dict[update.effective_user.id]
    try:
        rss_link = update.message.text.split(' ')[1]
        feed_dataclass_obj = list(filter(lambda x: x.url == rss_link, current_chat_feeds))[0]
        current_chat_feeds.remove(feed_dataclass_obj)
        await update.message.reply_text(f"Removed {rss_link}")
    except Exception:
        await update.message.reply_text(f"Error removing")


@handler_decorator
async def plaintext_handler(update: Update, _):
    text = update.message.text
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@handler_decorator
async def fetch_command(update: Update, _):
    current_chat_feeds: list[FeedDataclass] = data_dict[update.effective_user.id]
    result_msg_str = ''

    for feed_obj in current_chat_feeds:
        parser_obj = get_parsed_feed(feed_obj.url)

        result_msg_str += f'**{parser_obj.feed.title}**\n\n'

        entries_list = parser_obj.entries
        entries_list.sort(key=lambda x: datetime.datetime.fromisoformat(x.published), reverse=True)

        # Take only entries, published after last update time
        entries_list = list(filter(
            lambda x: datetime.datetime.fromisoformat(x.published).replace(tzinfo=None) > feed_obj.last_update_time,
            entries_list
        ))

        if not entries_list:
            result_msg_str += 'EMPTY\n'
            continue

        for i in range(len(entries_list)):
            entry = entries_list[i]
            entry_id = entry.id
            entry_link = entry.link
            entry_published = datetime.datetime.fromisoformat(entry.published)
            entry_title = entry.title
            entry_content = entry.content

            result_msg_str += f"[{i}]({entry_link}) {entry_title}\n"

        feed_obj.last_update_time = datetime.datetime.now()
        result_msg_str += "\n"

    await update.message.reply_text(
        result_msg_str,
        parse_mode=ParseMode.MARKDOWN
    )


async def callback_every_second(context: ContextTypes.DEFAULT_TYPE):
    for i in data_dict.keys():
        await context.bot.send_message(
            chat_id=i,
            text='One message every 1 second'
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
# job_minute = app.job_queue.run_repeating(callback_every_second, interval=1, first=0)

for command_string, func in commands_funcs_mapping.items():
    app.add_handler(CommandHandler(command_string, func))

app.add_handler(MessageHandler(filters.TEXT, plaintext_handler))
app.run_polling()
