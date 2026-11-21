"""The Dutch texts of the change reports, in their exact wording."""

import pytest

from app.models.dish import Dish
from app.models.guest_category import GuestCategory
from app.models.party import GuestCount, Party, PartyAnswer
from app.models.tableware_item import TablewareItem
from app.services.report_texts import (
    MAX_MESSAGE,
    MAX_TITLE,
    attendance_report,
    batch_messages,
    batch_title,
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
            "Komt met 5: 1 vegetarisch, 2 eet alles, 2 kindermenu's."
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
            "Komt met 14: 2 vegan, 3 vegetarisch, 4 eet alles, 5 kindermenu's."
        )

    def test_attendance_leaves_zero_groups_out(self):
        party = _party("Familie de Boer", PartyAnswer.COMING, normaal=2)

        assert attendance_report(party) == "Komt met 2: 2 eet alles."

    def test_attendance_uses_the_singular(self):
        party = _party("Tante Els", PartyAnswer.COMING, vegan=1, kind=1)

        assert attendance_report(party) == "Komt met 2: 1 vegan, 1 kindermenu."

    def test_attendance_counts_young_children_in_the_total(self):
        party = _party("Familie Jansen", PartyAnswer.COMING, kind=3)

        assert attendance_report(party) == "Komt met 3: 3 kindermenu's."

    def test_attendance_of_a_household_that_does_not_come(self):
        party = _party("Familie de Boer", PartyAnswer.NOT_COMING)

        assert attendance_report(party) == "Komt niet."

    def test_dish_taken(self):
        assert dish_taken_report(Dish(name="Tiramisu")) == "Maakt Tiramisu."

    def test_dish_released(self):
        assert (
            dish_released_report(Dish(name="Tiramisu")) == "Maakt Tiramisu toch niet."
        )

    def test_tableware_taken(self):
        item = TablewareItem(text="20 borden")

        assert tableware_taken_report(item) == "Neemt 20 borden mee."

    def test_tableware_released(self):
        item = TablewareItem(text="20 borden")

        assert tableware_released_report(item) == "Neemt 20 borden toch niet mee."

    @pytest.mark.parametrize(
        ("people", "word"),
        [(1, "1 vegetarisch"), (7, "7 vegetarisch")],
    )
    def test_vegetarisch_has_no_plural(self, people: int, word: str):
        party = _party("Tante Els", PartyAnswer.COMING, vegetarisch=people)

        assert attendance_report(party) == f"Komt met {people}: {word}."


class TestMarkdownEscaping:
    def test_dish_name_is_escaped(self):
        dish = Dish(name="*Soep* [met] <b> a_b `c` ~d~ e\\f")

        expected = "\\*Soep\\* \\[met\\] \\<b\\> a\\_b \\`c\\` \\~d\\~ e\\\\f"
        assert dish_taken_report(dish) == f"Maakt {expected}."
        assert dish_released_report(dish) == f"Maakt {expected} toch niet."

    def test_tableware_text_is_escaped(self):
        item = TablewareItem(text="2_x *borden*")

        assert tableware_taken_report(item) == "Neemt 2\\_x \\*borden\\* mee."
        assert (
            tableware_released_report(item) == "Neemt 2\\_x \\*borden\\* toch niet mee."
        )

    def test_plain_text_is_untouched(self):
        assert dish_taken_report(Dish(name="Pompoensoep (vers)")) == (
            "Maakt Pompoensoep (vers)."
        )


class TestBatchTitle:
    def test_is_the_household_name(self):
        party = _party("Familie Jansen", PartyAnswer.COMING)

        assert batch_title(party) == "Familie Jansen"

    def test_is_cut_to_250_characters(self):
        party = _party("x" * 400, PartyAnswer.COMING)

        assert batch_title(party) == "x" * MAX_TITLE
        assert MAX_TITLE == 250

    def test_a_name_of_exactly_250_is_kept(self):
        party = _party("y" * 250, PartyAnswer.COMING)

        assert batch_title(party) == "y" * 250


class TestBatchMessages:
    def test_one_line_is_a_one_item_list(self):
        assert batch_messages(["Komt niet."]) == ["- Komt niet."]

    def test_several_lines_keep_their_order(self):
        assert batch_messages(["Komt met 2: 2 eet alles.", "Maakt Tiramisu."]) == [
            "- Komt met 2: 2 eet alles.\n- Maakt Tiramisu."
        ]

    def test_no_lines_make_no_message(self):
        assert batch_messages([]) == []

    def test_splits_only_where_a_message_would_pass_the_limit(self):
        # "- " + 2046 characters is 2048; two of them and the newline are 4097.
        long_line = "a" * 2046
        short_line = "b" * 2045

        assert MAX_MESSAGE == 4096
        # 2048 + 1 + 2047 = 4096: exactly the limit, so one message.
        assert batch_messages([long_line, short_line]) == [
            f"- {long_line}\n- {short_line}"
        ]
        # One character more and the second line starts a new message.
        assert batch_messages([long_line, short_line + "b"]) == [
            f"- {long_line}",
            f"- {short_line}b",
        ]

    def test_split_messages_keep_the_order_of_the_lines(self):
        lines = [f"{number}" + "c" * 1500 for number in range(5)]

        messages = batch_messages(lines)

        assert len(messages) == 3  # Two lines fit in one message, not three.
        assert all(len(message) <= MAX_MESSAGE for message in messages)
        assert "\n".join(messages).split("\n") == [f"- {line}" for line in lines]

    def test_an_over_long_line_is_cut_to_the_limit(self):
        messages = batch_messages(["d" * 5000])

        assert messages == [("- " + "d" * 5000)[:MAX_MESSAGE]]
        assert len(messages[0]) == MAX_MESSAGE

    def test_an_over_long_line_gets_a_message_of_its_own(self):
        messages = batch_messages(["Komt niet.", "e" * 5000, "Maakt Tiramisu."])

        assert messages == [
            "- Komt niet.",
            ("- " + "e" * 5000)[:MAX_MESSAGE],
            "- Maakt Tiramisu.",
        ]
