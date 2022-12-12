import dataclasses
import datetime
from typing import Optional
from functools import wraps
import validators

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

from utils import get_parsed_feed, get_divided_long_message

MAX_MSG_LEN = 7000
DEFAULT_TZ = datetime.timezone(datetime.timedelta(hours=3))
PERIODICAL_FETCHING_TIME = datetime.time(hour=18, tzinfo=DEFAULT_TZ)

MIN_TIME = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)

async def wrapped_send_text(send_message_func, *args, **kwargs):
    text = kwargs.pop("text", None)
    if not text:
        raise Exception("No text argument passed")

    if len(text) > MAX_MSG_LEN:
        lpart, rpart = get_divided_long_message(text, MAX_MSG_LEN)

        await send_message_func(*args, text=lpart, **kwargs)
        await wrapped_send_text(send_message_func, *args, text=rpart, **kwargs)
    else:
        await send_message_func(*args, text=text, **kwargs)

@dataclasses.dataclass
class FeedDataclass:
    url: str
    last_update_time: Optional[datetime.datetime] = MIN_TIME
    # last_item_id: Optional[str] = None

    def __str__(self):
        return self.url

    def __hash__(self):
        return self.url.__hash__()


chats_data: dict[int, list[FeedDataclass]] = {}


def handler_decorator(func):
    """
    Wrapper over each handler
    @param func: handler func
    """
    @wraps(func)
    async def wrapper(update: Update, *args, **kwargs):
        if update.message:
            user_id = update.message.from_user.id

            if user_id not in chats_data:
                chats_data[user_id] = []

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
    user_feeds = chats_data[update.effective_user.id]
    args = update.message.text.split()[1:]
    for i in args:
        if not validators.url(i):
            await update.message.reply_text(f"Error: {i} is not a url")
            continue

        if FeedDataclass(i) not in user_feeds:
            user_feeds.append(FeedDataclass(i))
            await update.message.reply_text(f"Subscribed {i}")
        else:
            await update.message.reply_text(f"Error: {i} is already in subscriptions")


@handler_decorator
async def list_command(update: Update, _):
    user_feeds = chats_data[update.effective_user.id]
    if not user_feeds:
        await update.message.reply_text("List is empty")
        return

    res_str = 'List:\n' + '\n'.join([f"[{i}] {user_feeds[i]}" for i in range(len(user_feeds))])
    await update.message.reply_text(res_str)


@handler_decorator
async def del_command(update: Update, _):
    """
    Delete one of subscribed feeds
    """
    user_feeds = chats_data[update.effective_user.id]

    arg1 = update.message.text.split(' ')[1]
    if arg1.isdigit():
        try:
            feed_dataclass_obj = user_feeds[int(arg1)]
        except KeyError:
            feed_dataclass_obj = None
            await update.message.reply_text(f"Error: {arg1} is out of bounds")
    else:
        # Find in list by matching x.url attribute
        try:
            feed_dataclass_obj = list(filter(lambda x: x.url == arg1, user_feeds))[0]
        except KeyError:
            feed_dataclass_obj = None
            await update.message.reply_text(f"Error: {arg1} is not found in subscriptions")

    if feed_dataclass_obj:
        user_feeds.remove(feed_dataclass_obj)
    await update.message.reply_text(f"Removed {feed_dataclass_obj.url}")


@handler_decorator
async def plaintext_handler(update: Update, _):
    text = update.message.text
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

def fetch_for_given_chat_id(chat_id: int) -> str:
    """
    Fetch new rss entries
    @param chat_id: fetch feeds from given chat_id subscriptions
    @return: message to send
    """
    current_chat_feeds: list[FeedDataclass] = chats_data[chat_id]
    result_msg_str = ''

    for feed_obj in current_chat_feeds:
        tmp_feed_msg_part = ''
        url = feed_obj.url
        try:
            parser_obj = get_parsed_feed(url)

            if parser_obj.get('bozo_exception') or parser_obj.status == 404:
                raise Exception
        except Exception:  # Exception occurred manually, or while fetching url
            print(f"Error fetching url: {url}")
            result_msg_str += f"err:\n{url}"
            # yield error_msg
            continue

        tmp_feed_msg_part += f'<b>{parser_obj.feed.title}</b>\n'

        entries_list = parser_obj.entries
        entries_list.sort(key=lambda x: datetime.datetime.fromisoformat(x.published), reverse=True)

        # Take only entries, published after last update time
        entries_list = list(filter(
            lambda x: datetime.datetime.fromisoformat(x.published) > feed_obj.last_update_time,
            entries_list
        ))

        for i in range(len(entries_list)):
            entry = entries_list[i]
            entry_id = entry.id
            entry_link = entry.link
            entry_published = datetime.datetime.fromisoformat(entry.published)
            entry_title = entry.title
            entry_content = entry.content

            tmp_feed_msg_part += f"<a href='{entry_link}'>[{i}]</a> {entry_title}\n"

        feed_obj.last_update_time = datetime.datetime.now(datetime.timezone.utc)
        tmp_feed_msg_part += "\n"

        if entries_list:
            result_msg_str += tmp_feed_msg_part

    if not result_msg_str:
        result_msg_str = "No updates :("

    return result_msg_str


@handler_decorator
async def fetch_command(update: Update, _):
    result_msg = fetch_for_given_chat_id(update.effective_user.id)

    await wrapped_send_text(
        update.message.reply_text,
        text=result_msg,
        parse_mode=ParseMode.HTML
    )


async def callback_periodically(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in chats_data.keys():
        result_msg = "--- PERIODICAL FETCH ---\n\n" + fetch_for_given_chat_id(chat_id)

        await wrapped_send_text(
            context.bot.send_message,
            text=result_msg,
            chat_id=chat_id,
            parse_mode=ParseMode.HTML
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

job_daily = app.job_queue.run_repeating(
    callback_periodically,
    interval=datetime.timedelta(days=1),
    first=PERIODICAL_FETCHING_TIME
)

for command_string, func in commands_funcs_mapping.items():
    app.add_handler(CommandHandler(command_string, func))

app.add_handler(MessageHandler(filters.TEXT, plaintext_handler))
app.run_polling()
