"""The Dutch texts of the change reports, in their exact wording."""

import pytest

from app.models.dish import Dish
from app.models.guest_category import GuestCategory
from app.models.party import GuestCount, Party, PartyAnswer
from app.models.tableware_item import TablewareItem
from app.services.report_texts import (
    attendance_report,
    dish_released_report,
    dish_taken_report,
    tableware_released_report,
    tableware_taken_report,
)


def _party(
    name: str,
    answer: PartyAnswer,
    vegan: int = 0,
    vegetarisch: int = 0,
    normaal: int = 0,
    kind: int = 0,
) -> Party:
    counts = {
        GuestCategory.VEGAN: vegan,
        GuestCategory.VEGETARISCH: vegetarisch,
        GuestCategory.NORMAAL: normaal,
        GuestCategory.KIND: kind,
    }
    return Party(
        name=name,
        answer=answer,
        guest_counts=[GuestCount(category=c, people=n) for c, n in counts.items()],
    )


class TestReportTexts:
    def test_attendance_names_every_group_that_comes(self):
        party = _party(
            "Familie Jansen", PartyAnswer.COMING, vegetarisch=1, normaal=2, kind=2
        )

        assert attendance_report(party) == (
            "Familie Jansen komt met 5: 1 vegetarisch, 2 eet alles, 2 kindermenu's."
        )

    def test_attendance_names_all_four_groups_in_order(self):
        party = _party(
            "Familie Jansen",
            PartyAnswer.COMING,
            vegan=2,
            vegetarisch=3,
            normaal=4,
            kind=5,
        )

        assert attendance_report(party) == (
            "Familie Jansen komt met 14: 2 vegan, 3 vegetarisch, 4 eet alles, "
            "5 kindermenu's."
        )

    def test_attendance_leaves_zero_groups_out(self):
        party = _party("Familie de Boer", PartyAnswer.COMING, normaal=2)

        assert attendance_report(party) == "Familie de Boer komt met 2: 2 eet alles."

    def test_attendance_uses_the_singular(self):
        party = _party("Tante Els", PartyAnswer.COMING, vegan=1, kind=1)

        assert (
            attendance_report(party) == "Tante Els komt met 2: 1 vegan, 1 kindermenu."
        )

    def test_attendance_counts_young_children_in_the_total(self):
        party = _party("Familie Jansen", PartyAnswer.COMING, kind=3)

        assert attendance_report(party) == "Familie Jansen komt met 3: 3 kindermenu's."

    def test_attendance_of_a_household_that_does_not_come(self):
        party = _party("Familie de Boer", PartyAnswer.NOT_COMING)

        assert attendance_report(party) == "Familie de Boer komt niet."

    def test_dish_taken(self):
        dish = Dish(name="Pompoensoep")

        assert (
            dish_taken_report(_party("Familie Jansen", PartyAnswer.COMING), dish)
            == "Familie Jansen maakt Pompoensoep."
        )

    def test_dish_released(self):
        dish = Dish(name="Pompoensoep")

        assert (
            dish_released_report(_party("Familie Jansen", PartyAnswer.COMING), dish)
            == "Familie Jansen maakt Pompoensoep toch niet."
        )

    def test_tableware_taken(self):
        item = TablewareItem(text="20 borden")

        assert (
            tableware_taken_report(_party("Familie Jansen", PartyAnswer.COMING), item)
            == "Familie Jansen neemt 20 borden mee."
        )

    def test_tableware_released(self):
        item = TablewareItem(text="20 borden")

        assert (
            tableware_released_report(
                _party("Familie Jansen", PartyAnswer.COMING), item
            )
            == "Familie Jansen neemt 20 borden toch niet mee."
        )

    @pytest.mark.parametrize(
        ("people", "word"),
        [(1, "1 vegetarisch"), (7, "7 vegetarisch")],
    )
    def test_vegetarisch_has_no_plural(self, people: int, word: str):
        party = _party("Tante Els", PartyAnswer.COMING, vegetarisch=people)

        assert attendance_report(party) == f"Tante Els komt met {people}: {word}."
