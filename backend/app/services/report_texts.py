"""The Telegram messages a household's changes produce (docs/design.md, Change reports).

Each change is a line, without the household's name: the household's changes
go out together, in one message headed by its name.
"""

import re

from app.models.dish import Dish
from app.models.guest_category import GuestCategory
from app.models.party import Party, PartyAnswer
from app.models.tableware_item import TablewareItem

# Singular and plural, in the order the line names them.
_CATEGORY_WORDS: tuple[tuple[GuestCategory, str, str], ...] = (
    (GuestCategory.VEGAN, "vegan", "vegan"),
    (GuestCategory.VEGETARISCH, "vegetarisch", "vegetarisch"),
    (GuestCategory.NORMAAL, "eet alles", "eet alles"),
    (GuestCategory.KIND, "kindermenu", "kindermenu's"),
)

# The bridge's limits on a submit (pvginkel/Notifications, README, Submit).
MAX_TITLE = 250
MAX_MESSAGE = 4096

_MARKDOWN_SPECIAL = re.compile(r"([\\`*_\[\]<>~])")


def _text(value: str) -> str:
    """``value`` as literal Markdown text: a dish named "*" stays a "*"."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", value)


def attendance_report(party: Party) -> str:
    """ "Komt met 5: 1 vegetarisch, 2 eet alles, 2 kindermenu's." """
    if party.answer != PartyAnswer.COMING:
        return "Komt niet."
    parts = []
    total = 0
    for category, singular, plural in _CATEGORY_WORDS:
        people = party.people(category)
        total += people
        if people:
            parts.append(f"{people} {singular if people == 1 else plural}")
    return f"Komt met {total}: {', '.join(parts)}."


def dish_taken_report(dish: Dish) -> str:
    """ "Maakt Tiramisu." """
    return f"Maakt {_text(dish.name)}."


def dish_released_report(dish: Dish) -> str:
    """ "Maakt Tiramisu toch niet." """
    return f"Maakt {_text(dish.name)} toch niet."


def tableware_taken_report(item: TablewareItem) -> str:
    """ "Neemt 20 borden mee." """
    return f"Neemt {_text(item.text)} mee."


def tableware_released_report(item: TablewareItem) -> str:
    """ "Neemt 20 borden toch niet mee." """
    return f"Neemt {_text(item.text)} toch niet mee."


def batch_title(party: Party) -> str:
    """The message's title, which the bridge shows in bold: the household's name."""
    return party.name[:MAX_TITLE]


def batch_messages(lines: list[str]) -> list[str]:
    """A household's changes as a Markdown list, one item per change, in order.

    Almost always one message; the lines go over more of them only where one
    would pass the bridge's limit.
    """
    messages: list[str] = []
    current = ""
    for line in lines:
        item = f"- {line}"[:MAX_MESSAGE]
        if current and len(current) + 1 + len(item) > MAX_MESSAGE:
            messages.append(current)
            current = ""
        current = f"{current}\n{item}" if current else item
    if current:
        messages.append(current)
    return messages
