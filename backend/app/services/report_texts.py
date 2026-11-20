"""The Telegram messages a household's changes produce (docs/design.md, Change reports)."""

from app.models.dish import Dish
from app.models.guest_category import GuestCategory
from app.models.party import Party, PartyAnswer
from app.models.tableware_item import TablewareItem

# Singular and plural, in the order the message names them.
_CATEGORY_WORDS: tuple[tuple[GuestCategory, str, str], ...] = (
    (GuestCategory.VEGAN, "vegan", "vegan"),
    (GuestCategory.VEGETARISCH, "vegetarisch", "vegetarisch"),
    (GuestCategory.NORMAAL, "eet alles", "eet alles"),
    (GuestCategory.KIND, "kindermenu", "kindermenu's"),
)


def attendance_report(party: Party) -> str:
    """ "Familie Jansen komt met 5: 1 vegetarisch, 2 eet alles, 2 kindermenu's." """
    if party.answer != PartyAnswer.COMING:
        return f"{party.name} komt niet."
    parts = []
    total = 0
    for category, singular, plural in _CATEGORY_WORDS:
        people = party.people(category)
        total += people
        if people:
            parts.append(f"{people} {singular if people == 1 else plural}")
    return f"{party.name} komt met {total}: {', '.join(parts)}."


def dish_taken_report(party: Party, dish: Dish) -> str:
    """ "Familie Jansen maakt Tiramisu." """
    return f"{party.name} maakt {dish.name}."


def dish_released_report(party: Party, dish: Dish) -> str:
    """ "Familie Jansen maakt Tiramisu toch niet." """
    return f"{party.name} maakt {dish.name} toch niet."


def tableware_taken_report(party: Party, item: TablewareItem) -> str:
    """ "Familie Jansen neemt 20 borden mee." """
    return f"{party.name} neemt {item.text} mee."


def tableware_released_report(party: Party, item: TablewareItem) -> str:
    """ "Familie Jansen neemt 20 borden toch niet mee." """
    return f"{party.name} neemt {item.text} toch niet mee."
