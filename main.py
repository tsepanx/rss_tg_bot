import dataclasses
import datetime
from typing import Optional

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from functools import wraps
from utils import get_parsed_feed, get_divided_long_message

MAX_MSG_LEN = 4096

async def wrapped_reply_text(update: Update, msg: str, *args, **kwargs):
    print(msg)
    if len(msg) > MAX_MSG_LEN:
        fpart, leftpart = get_divided_long_message(msg, MAX_MSG_LEN)

        await update.message.reply_text(fpart, *args, **kwargs)
        await wrapped_reply_text(update, leftpart, *args, **kwargs)
    else:
        await update.message.reply_text(msg, *args, **kwargs)

@dataclasses.dataclass
class FeedDataclass:
    url: str
    last_update_time: Optional[datetime.datetime] = datetime.datetime.min
    # last_item_id: Optional[str] = None

    def __str__(self):
        return self.url


data_dict: dict[int, list[FeedDataclass]] = {}


def handler_decorator(func):
    """
    Wrapper over each handler
    @param func: handler func
    @return:
    """
    @wraps(func)
    async def wrapper(update: Update, *args, **kwargs):
        if update.message:
            user_id = update.message.from_user.id

            if user_id not in data_dict:
                data_dict[user_id] = []

        try:
            await func(update, *args, **kwargs)
        except Exception as e:
            await update.message.reply_text(f"Error executing {func.__name__} func:\n{e}")

    return wrapper


@handler_decorator
async def add_command(update: Update, _):
    """
    Subscribe to a list of rss urls, given separated by spacing characters
    """
    rss_links = update.message.text.split()[1:]
    for link in rss_links:
        data_dict[update.effective_user.id].append(
            FeedDataclass(link)
        )

        await update.message.reply_text(f"Subscribed {link}")


@handler_decorator
async def list_command(update: Update, _):
    user_feeds = data_dict[update.effective_user.id]
    await update.message.reply_text('List:\n' + '\n'.join(map(str, user_feeds)))


@handler_decorator
async def del_command(update: Update, _):
    """
    Delete one of subscribed feeds
    """
    current_chat_feeds = data_dict[update.effective_user.id]

    rss_link = update.message.text.split(' ')[1]
    feed_dataclass_obj = list(filter(lambda x: x.url == rss_link, current_chat_feeds))[0]
    current_chat_feeds.remove(feed_dataclass_obj)
    await update.message.reply_text(f"Removed {rss_link}")


@handler_decorator
async def plaintext_handler(update: Update, _):
    text = update.message.text
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

def fetch_for_given_chat_id(chat_id: int) -> str:
    """
    Fetch new rss entries
    @param chat_id: fetch feeds from given chat_id subscriptions
    @return: message to send
    """
    current_chat_feeds: list[FeedDataclass] = data_dict[chat_id]
    result_msg_str = ''

    for feed_obj in current_chat_feeds:
        parser_obj = get_parsed_feed(feed_obj.url)

        result_msg_str += f'<b>{parser_obj.feed.title}</b>\n\n'

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

            result_msg_str += f"<a href='{entry_link}'>[{i}]</a> {entry_title}\n"

        feed_obj.last_update_time = datetime.datetime.now()
        result_msg_str += "\n"

    return result_msg_str


@handler_decorator
async def fetch_command(update: Update, _):
    result_msg = fetch_for_given_chat_id(update.effective_user.id)

    await wrapped_reply_text(
        update,
        result_msg,
        parse_mode=ParseMode.HTML
    )


async def callback_daily(context: ContextTypes.DEFAULT_TYPE):
    print('daily')
    for chat_id in data_dict.keys():
        result_msg = fetch_for_given_chat_id(chat_id)

        result_msg = "DAILY FETCH:\n" + result_msg

        await context.bot.send_message(
            chat_id=chat_id,
            text=result_msg,
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
job_minute = app.job_queue.run_repeating(callback_daily, interval=datetime.timedelta(days=1))

for command_string, func in commands_funcs_mapping.items():
    app.add_handler(CommandHandler(command_string, func))

app.add_handler(MessageHandler(filters.TEXT, plaintext_handler))
app.run_polling()
