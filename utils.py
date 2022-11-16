import feedparser


def get_parsed_feed(url: str) -> feedparser.FeedParserDict:
    print("")
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
