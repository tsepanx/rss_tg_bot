import datetime
import time

import feedparser


def get_parsed_feed(url: str) -> feedparser.FeedParserDict:
    return feedparser.parse(url)
    # return parsed.entries