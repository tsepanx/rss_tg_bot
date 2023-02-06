import functools
import feedparser

MAX_MSG_LEN = 7000


def get_parsed_feed(url: str) -> feedparser.FeedParserDict:
    print(f"Fetching {url}")
    return feedparser.parse(url)


def get_divided_long_message(text, max_size) -> [str, str]:
    """
    Cuts long message text with \n separator

    @param text: str - given text
    @param max_size: int - single text message max size

    return: text part from start, and the rest of text
    """
    subtext = text[:max_size]
    border = subtext.rfind('\n')

    subtext = subtext[:border]
    text = text[border:]

    return subtext, text


def to_list(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> list:
        res = list(func(*args, **kwargs))
        return res
    return wrapper
