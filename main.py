import dataclasses
import datetime
import traceback
from typing import Optional
from functools import wraps

import validators
import feedparser

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, PicklePersistence

from utils import get_parsed_feed, get_divided_long_message, to_list, MAX_MSG_LEN

DEFAULT_TZ = datetime.timezone(datetime.timedelta(hours=3))
PERIODICAL_FETCHING_TIME = datetime.time(hour=18, tzinfo=DEFAULT_TZ)

MIN_TIME = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)

FEEDS_KEY = 'feeds'


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


def handler_decorator(func):
    """
    Wrapper over each handler
    @param func: handler func
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.message:
            if FEEDS_KEY not in context.chat_data:
                context.chat_data[FEEDS_KEY] = list()

        try:
            await func(update, context, *args, **kwargs)
        except Exception:
            await wrapped_send_text(update.message.reply_text, text=traceback.format_exc())

    return wrapper


@handler_decorator
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Subscribe to a list of rss urls, given separated by spacing characters
    """
    user_feeds: list[FeedDataclass] = context.chat_data.get(FEEDS_KEY, list())

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
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_feeds: list[FeedDataclass] = context.chat_data.get(FEEDS_KEY, list())

    if not user_feeds:
        await update.message.reply_text("List is empty")
        return

    res_str = 'List:\n' + '\n'.join([f"[{i}] {user_feeds[i]}" for i in range(len(user_feeds))])
    await update.message.reply_text(res_str)


@handler_decorator
async def del_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Delete one of subscribed feeds
    """
    user_feeds: list[FeedDataclass] = context.chat_data.get(FEEDS_KEY, list())

    query_args = context.args
    if len(query_args) != 1:
        await wrapped_send_text(update.message.reply_text, text="Wrong format: Should be exactly one argument")
        return

    first_arg = query_args[0]

    if first_arg.isdigit():
        try:
            feed_dataclass_obj = user_feeds[int(first_arg)]
        except IndexError:
            feed_dataclass_obj = None
            await update.message.reply_text(f"Error: number '{first_arg}' is out of bounds")
            return
    else:
        # Find in list by matching x.url attribute
        try:
            feed_dataclass_obj = list(filter(lambda x: x.url == first_arg, user_feeds))[0]
        except IndexError:
            feed_dataclass_obj = None
            await update.message.reply_text(f"Error: {first_arg} is not found in subscriptions")
            return

    if feed_dataclass_obj:
        user_feeds.remove(feed_dataclass_obj)
    await update.message.reply_text(f"Removed {feed_dataclass_obj.url}")


@handler_decorator
async def plaintext_handler(update: Update, _):
    text = update.message.text
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@dataclasses.dataclass
class SingleFetchedFeedDataclass:
    feed_dataclass: FeedDataclass
    feed_parser_obj: feedparser.FeedParserDict | None
    processed_entries: [feedparser.FeedParserDict]
    is_error: bool


@to_list
def fetch_for_given_chat(chat_data: dict) -> [SingleFetchedFeedDataclass]:
    """
    Fetch new rss entries
    @param chat_data: context.chat_data for given chat
    @return: message to send
    """
    chat_feeds: list[FeedDataclass] = chat_data[FEEDS_KEY]

    feed_obj: FeedDataclass
    for feed_obj in chat_feeds:
        single_feed_dataclass = SingleFetchedFeedDataclass(feed_obj, None, [], False)

        url = feed_obj.url
        try:
            parser_obj = get_parsed_feed(url)  # Fetching command
            single_feed_dataclass.feed_parser_obj = parser_obj

            if parser_obj.get('bozo_exception') or parser_obj.get('status') != 200:
                raise Exception
        except Exception as e:  # Exception occurred manually, or while fetching url
            print(f"Error fetching url: {url}", e, sep='\n')
            single_feed_dataclass.is_error = True
            continue

        entries_list = parser_obj.entries
        entries_list.sort(key=lambda x: datetime.datetime.fromisoformat(x.published), reverse=True)

        # Take only entries, published after last update time
        entries_list = list(filter(
            lambda x: datetime.datetime.fromisoformat(x.published) > feed_obj.last_update_time,
            entries_list
        ))

        single_feed_dataclass.processed_entries = entries_list

        if not entries_list:
            continue

        feed_obj.last_update_time = datetime.datetime.now(datetime.timezone.utc)

        yield single_feed_dataclass


def build_message_from(fetched_dataclasses: [SingleFetchedFeedDataclass]) -> str | None:
    message_str = ""

    successfully_fetched_feeds = list(filter(lambda x: x.is_error == False, fetched_dataclasses))
    single_feed: SingleFetchedFeedDataclass
    for single_feed in successfully_fetched_feeds:
        message_str += f'<b>{single_feed.feed_parser_obj.feed.title}</b>\n'

        for ind, entry in enumerate(single_feed.processed_entries):
            entry_id = entry.id
            entry_link = entry.link
            entry_published = datetime.datetime.fromisoformat(entry.published)
            entry_title = entry.title
            entry_content = entry.content

            message_str += f"<a href='{entry_link}'>[{ind}]</a> {entry_title}\n"
        message_str += '\n'

    if not message_str:
        return None

    message_str += '\n'

    error_to_fetch_feeds = filter(lambda x: x.is_error == True, fetched_dataclasses)
    for err_feed in error_to_fetch_feeds:
        message_str += f"err:{err_feed.feed_dataclass.url}\n"

    return message_str


@handler_decorator
async def fetch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fetched_list = fetch_for_given_chat(context.chat_data)
    result_msg = build_message_from(fetched_list)

    if not result_msg:
        result_msg = "No updates :("

    await wrapped_send_text(
        update.message.reply_text,
        text=result_msg,
        parse_mode=ParseMode.HTML
    )


async def callback_periodically(context: ContextTypes.DEFAULT_TYPE):
    for chat_id in context.application.chat_data.keys():
        chat_data = context.application.chat_data[chat_id]

        fetched_feeds = fetch_for_given_chat(chat_data)
        updates_msg = build_message_from(fetched_feeds)

        if not updates_msg:  # Do not send messages if no updates
            return None

        msgs_to_send = [
            "--- PERIODICAL FETCH ---\n\n",
            updates_msg
        ]

        for msg in msgs_to_send:
            await wrapped_send_text(
                context.bot.send_message,
                text=msg,
                chat_id=chat_id,
                parse_mode=ParseMode.HTML
            )

if __name__ == "__main__":
    TOKEN = open('.token').read(); print(TOKEN)

    persistence = PicklePersistence(filepath='persitencebot', update_interval=1)

    app = ApplicationBuilder() \
        .persistence(persistence) \
        .token(TOKEN) \
        .build()

    job_daily = app.job_queue.run_daily(
        callback_periodically,
        days=(5,),  # Friday
        time=PERIODICAL_FETCHING_TIME
    )

    commands_funcs_mapping = {
        "add": add_command,
        "list": list_command,
        "del": del_command,
        "fetch": fetch_command,
    }

    for command_string, func in commands_funcs_mapping.items():
        app.add_handler(CommandHandler(command_string, func))

    app.add_handler(MessageHandler(filters.TEXT, plaintext_handler))
    app.run_polling()
