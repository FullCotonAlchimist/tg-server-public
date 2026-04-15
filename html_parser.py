from html.parser import HTMLParser
from telethon.tl.types import (
    MessageEntityBold,
    MessageEntityUnderline,
    MessageEntityCustomEmoji,
)


def _utf16_len(s: str) -> int:
    return sum(2 if ord(c) > 0xFFFF else 1 for c in s)


class _TgHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.plain_parts = []
        self.entities = []
        self._pos = 0
        self.stack = []

    def _append(self, s):
        self.plain_parts.append(s)
        self._pos += _utf16_len(s)

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if tag in ('b', 'u'):
            self.stack.append((tag, self._pos, None))
        elif tag == 'tg-emoji':
            self.stack.append((tag, self._pos, attrs_d.get('emoji-id')))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                entry = self.stack.pop(i)
                length = self._pos - entry[1]
                if length > 0:
                    if tag == 'b':
                        self.entities.append(MessageEntityBold(offset=entry[1], length=length))
                    elif tag == 'u':
                        self.entities.append(MessageEntityUnderline(offset=entry[1], length=length))
                    elif tag == 'tg-emoji' and entry[2]:
                        self.entities.append(MessageEntityCustomEmoji(
                            offset=entry[1], length=length, document_id=int(entry[2])
                        ))
                break

    def handle_data(self, data):
        self._append(data)


def parse_telegram_html(text: str):
    parser = _TgHTMLParser()
    parser.feed(text)
    return ''.join(parser.plain_parts), parser.entities