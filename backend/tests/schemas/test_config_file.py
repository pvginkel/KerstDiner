"""Tests of the config file's schema and its loader."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.exceptions import ConfigurationError
from app.models.guest_category import DISH_CATEGORIES, GuestCategory
from app.schemas.config_file import (
    CONFIG_FILE,
    DishConfig,
    GuessConfig,
    HouseholdConfig,
    KerstDinerConfig,
    TablewareConfig,
    load_config_file,
)


class TestKerstDinerConfig:
    """The shape of the config file and what it refuses."""

    def test_empty_config_has_defaults(self) -> None:
        config = KerstDinerConfig.model_validate({})

        assert config.reset == 0
        assert config.households == []
        assert config.dishes == []
        assert config.servies == []

    def test_full_config_is_parsed(self) -> None:
        config = KerstDinerConfig.model_validate(
            {
                "reset": 3,
                "households": [
                    {
                        "key": "jansen",
                        "name": "Familie Jansen",
                        "guess": {"vegan": 1, "normaal": 2, "kind": 3},
                    }
                ],
                "dishes": [
                    {
                        "key": "soep",
                        "name": "Pompoensoep",
                        "for": ["vegan", "normaal"],
                        "image": "soep.jpg",
                    }
                ],
                "servies": [{"key": "borden", "text": "20 borden", "image": "b.png"}],
            }
        )

        assert config.reset == 3
        assert config.households[0].key == "jansen"
        assert config.households[0].guess.people(GuestCategory.KIND) == 3
        assert config.dishes[0].made_for == [GuestCategory.VEGAN, GuestCategory.NORMAAL]
        assert config.dishes[0].image == "soep.jpg"
        assert config.servies[0].text == "20 borden"
        assert config.servies[0].image == "b.png"

    def test_negative_reset_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            KerstDinerConfig.model_validate({"reset": -1})

    def test_unknown_top_level_field_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="extra_forbidden"):
            KerstDinerConfig.model_validate({"gasten": []})

    def test_servies_key_is_the_section_name(self) -> None:
        with pytest.raises(ValidationError, match="extra_forbidden"):
            KerstDinerConfig.model_validate(
                {"tableware": [{"key": "borden", "text": "20 borden"}]}
            )

    @pytest.mark.parametrize(
        ("section", "item"),
        [
            ("households", {"name": "Familie Jansen", "extra": 1}),
            ("dishes", {"name": "Soep", "extra": 1}),
            ("servies", {"text": "20 borden", "extra": 1}),
        ],
    )
    def test_unknown_item_field_is_refused(
        self, section: str, item: dict[str, Any]
    ) -> None:
        with pytest.raises(ValidationError, match="extra_forbidden"):
            KerstDinerConfig.model_validate({section: [{"key": "a", **item}]})

    def test_unknown_guess_field_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="extra_forbidden"):
            KerstDinerConfig.model_validate(
                {"households": [{"key": "a", "name": "A", "guess": {"baby": 1}}]}
            )

    @pytest.mark.parametrize(
        ("section", "item"),
        [
            ("households", {"name": "A"}),
            ("dishes", {"name": "A"}),
            ("servies", {"text": "A"}),
        ],
    )
    def test_duplicate_key_in_a_section_is_refused(
        self, section: str, item: dict[str, Any]
    ) -> None:
        with pytest.raises(ValidationError, match=rf"{section}: key a is used twice"):
            KerstDinerConfig.model_validate(
                {section: [{"key": "a", **item}, {"key": "a", **item}]}
            )

    def test_all_duplicate_keys_are_named(self) -> None:
        with pytest.raises(ValidationError, match="key a, b is used twice"):
            KerstDinerConfig.model_validate(
                {
                    "dishes": [
                        {"key": "b", "name": "B"},
                        {"key": "a", "name": "A"},
                        {"key": "b", "name": "B"},
                        {"key": "a", "name": "A"},
                    ]
                }
            )

    def test_same_key_in_different_sections_is_fine(self) -> None:
        config = KerstDinerConfig.model_validate(
            {
                "households": [{"key": "a", "name": "A"}],
                "dishes": [{"key": "a", "name": "A"}],
                "servies": [{"key": "a", "text": "A"}],
            }
        )

        assert len(config.households) == len(config.dishes) == len(config.servies) == 1

    def test_json_dump_roundtrip_uses_for_alias(self) -> None:
        config = KerstDinerConfig.model_validate(
            {"dishes": [{"key": "a", "name": "A", "for": ["vegan"]}]}
        )

        dumped = config.model_dump(mode="json", by_alias=True)

        assert dumped["dishes"][0]["for"] == ["vegan"]
        assert KerstDinerConfig.model_validate(dumped) == config


class TestConfigKey:
    """The key pattern, shared by all three sections."""

    @pytest.mark.parametrize("key", ["a", "0", "de-boer", "oma-opa-2", "a-", "9-9"])
    def test_valid_keys(self, key: str) -> None:
        assert HouseholdConfig(key=key, name="N").key == key
        assert DishConfig(key=key, name="N").key == key
        assert TablewareConfig(key=key, text="N").key == key

    @pytest.mark.parametrize(
        "key",
        ["", "-a", "A", "de_boer", "de boer", "de.boer", "é", "a/b", "Jansen", "a\n"],
    )
    def test_invalid_keys(self, key: str) -> None:
        with pytest.raises(ValidationError):
            HouseholdConfig(key=key, name="N")
        with pytest.raises(ValidationError):
            DishConfig(key=key, name="N")
        with pytest.raises(ValidationError):
            TablewareConfig(key=key, text="N")

    def test_key_of_64_characters_is_the_longest(self) -> None:
        assert HouseholdConfig(key="a" * 64, name="N").key == "a" * 64
        with pytest.raises(ValidationError):
            HouseholdConfig(key="a" * 65, name="N")

    def test_key_is_required(self) -> None:
        with pytest.raises(ValidationError):
            HouseholdConfig.model_validate({"name": "N"})


class TestGuessConfig:
    """A household's guess."""

    def test_categories_left_out_are_zero(self) -> None:
        guess = GuessConfig.model_validate({"normaal": 2})

        assert guess.people(GuestCategory.VEGAN) == 0
        assert guess.people(GuestCategory.VEGETARISCH) == 0
        assert guess.people(GuestCategory.NORMAAL) == 2
        assert guess.people(GuestCategory.KIND) == 0

    def test_household_without_guess_guesses_nobody(self) -> None:
        household = HouseholdConfig.model_validate({"key": "a", "name": "A"})

        assert all(household.guess.people(c) == 0 for c in GuestCategory)

    @pytest.mark.parametrize("people", [-1, 100])
    def test_people_out_of_range_is_refused(self, people: int) -> None:
        with pytest.raises(ValidationError):
            GuessConfig.model_validate({"normaal": people})

    def test_people_range_limits_are_allowed(self) -> None:
        guess = GuessConfig.model_validate({"vegan": 0, "normaal": 99})

        assert guess.normaal == 99

    def test_non_integer_people_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            GuessConfig.model_validate({"normaal": "two"})


class TestDishConfig:
    """A dish's ``for``, name and image."""

    def test_without_for_it_is_made_for_all_three_groups(self) -> None:
        dish = DishConfig.model_validate({"key": "a", "name": "A"})

        assert dish.made_for is None
        assert dish.categories == DISH_CATEGORIES
        assert GuestCategory.KIND not in dish.categories

    def test_for_names_the_groups(self) -> None:
        dish = DishConfig.model_validate(
            {"key": "a", "name": "A", "for": ["vegetarisch"]}
        )

        assert dish.categories == (GuestCategory.VEGETARISCH,)

    def test_categories_follow_display_order(self) -> None:
        dish = DishConfig.model_validate(
            {"key": "a", "name": "A", "for": ["normaal", "vegan"]}
        )

        assert dish.categories == (GuestCategory.VEGAN, GuestCategory.NORMAAL)

    def test_all_three_groups_may_be_named(self) -> None:
        dish = DishConfig.model_validate(
            {"key": "a", "name": "A", "for": ["normaal", "vegetarisch", "vegan"]}
        )

        assert dish.categories == DISH_CATEGORIES

    def test_made_for_by_field_name_is_accepted(self) -> None:
        dish = DishConfig(key="a", name="A", made_for=[GuestCategory.VEGAN])

        assert dish.categories == (GuestCategory.VEGAN,)

    def test_kind_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="kindermenu"):
            DishConfig.model_validate({"key": "a", "name": "A", "for": ["kind"]})

    def test_kind_among_other_groups_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="no dish is made for kind"):
            DishConfig.model_validate(
                {"key": "a", "name": "A", "for": ["normaal", "kind"]}
            )

    def test_empty_for_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="names no group"):
            DishConfig.model_validate({"key": "a", "name": "A", "for": []})

    def test_group_twice_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="names a group twice"):
            DishConfig.model_validate(
                {"key": "a", "name": "A", "for": ["vegan", "vegan"]}
            )

    def test_unknown_group_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            DishConfig.model_validate(
                {"key": "a", "name": "A", "for": ["pescotarisch"]}
            )

    def test_explicit_null_for_means_all_three(self) -> None:
        dish = DishConfig.model_validate({"key": "a", "name": "A", "for": None})

        assert dish.categories == DISH_CATEGORIES

    @pytest.mark.parametrize("image", ["soep.jpg", "a", "Soep_2-x.PNG", "0.jpg"])
    def test_valid_image_file_names(self, image: str) -> None:
        assert DishConfig(key="a", name="A", image=image).image == image
        assert TablewareConfig(key="a", text="A", image=image).image == image

    @pytest.mark.parametrize(
        "image", ["", "map/soep.jpg", "../soep.jpg", ".hidden", "-soep.jpg", "a b.jpg"]
    )
    def test_invalid_image_file_names(self, image: str) -> None:
        with pytest.raises(ValidationError):
            DishConfig(key="a", name="A", image=image)
        with pytest.raises(ValidationError):
            TablewareConfig(key="a", text="A", image=image)

    def test_image_is_optional(self) -> None:
        assert DishConfig(key="a", name="A").image is None
        assert TablewareConfig(key="a", text="A").image is None

    def test_name_is_required_and_not_empty(self) -> None:
        with pytest.raises(ValidationError):
            DishConfig.model_validate({"key": "a"})
        with pytest.raises(ValidationError):
            DishConfig.model_validate({"key": "a", "name": ""})

    def test_name_of_200_characters_is_the_longest(self) -> None:
        assert DishConfig(key="a", name="x" * 200).name == "x" * 200
        with pytest.raises(ValidationError):
            DishConfig(key="a", name="x" * 201)


class TestTablewareConfig:
    """A servies item."""

    def test_text_is_required(self) -> None:
        with pytest.raises(ValidationError):
            TablewareConfig.model_validate({"key": "a"})

    def test_name_is_not_a_field(self) -> None:
        with pytest.raises(ValidationError):
            TablewareConfig.model_validate({"key": "a", "name": "20 borden"})


class TestLoadConfigFile:
    """Reading the config file from disk."""

    def test_valid_file(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text(
            "reset: 2\n"
            "households:\n"
            "  - key: jansen\n"
            "    name: Familie Jansen\n"
            "    guess: {normaal: 2, kind: 1}\n"
            "dishes:\n"
            "  - key: rollade\n"
            "    name: Rollade\n"
            "    for: [normaal]\n"
            "servies:\n"
            "  - key: borden\n"
            "    text: 20 borden\n",
            encoding="utf-8",
        )

        config = load_config_file(path)

        assert config.reset == 2
        assert [h.key for h in config.households] == ["jansen"]
        assert config.households[0].guess.kind == 1
        assert config.dishes[0].categories == (GuestCategory.NORMAAL,)
        assert config.servies[0].text == "20 borden"

    def test_file_is_read_as_utf8(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text(
            "households:\n  - key: a\n    name: Café Zoë\n", encoding="utf-8"
        )

        assert load_config_file(path).households[0].name == "Café Zoë"

    def test_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nope.yaml"

        with pytest.raises(ConfigurationError, match="Cannot read the config file"):
            load_config_file(path)

    def test_directory_instead_of_file(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError, match="Cannot read the config file"):
            load_config_file(tmp_path)

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text("households: [unclosed\n  - key: a\n", encoding="utf-8")

        with pytest.raises(ConfigurationError, match="is not valid YAML"):
            load_config_file(path)

    def test_message_names_the_file(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text("reset: -1\n", encoding="utf-8")

        with pytest.raises(ConfigurationError) as raised:
            load_config_file(path)

        assert str(path) in str(raised.value)

    def test_invalid_content(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text(
            "dishes:\n  - key: a\n    name: A\n    for: [kind]\n", encoding="utf-8"
        )

        with pytest.raises(ConfigurationError, match="is not valid"):
            load_config_file(path)

    def test_unknown_field(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text("gasten: []\n", encoding="utf-8")

        with pytest.raises(ConfigurationError, match="gasten"):
            load_config_file(path)

    def test_duplicate_key(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text(
            "servies:\n  - {key: a, text: A}\n  - {key: a, text: B}\n",
            encoding="utf-8",
        )

        with pytest.raises(ConfigurationError, match="key a is used twice"):
            load_config_file(path)

    def test_top_level_list_is_invalid(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text("- key: a\n", encoding="utf-8")

        with pytest.raises(ConfigurationError, match="is not valid"):
            load_config_file(path)

    def test_empty_file_is_an_empty_config(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text("", encoding="utf-8")

        config = load_config_file(path)

        assert config == KerstDinerConfig()

    def test_comment_only_file_is_an_empty_config(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        path.write_text("# nothing yet\n", encoding="utf-8")

        assert load_config_file(path) == KerstDinerConfig()

    def test_default_path_is_the_shipped_file(self) -> None:
        assert CONFIG_FILE.name == "kerstdiner.yaml"
        assert CONFIG_FILE.parent.name == "data"
        assert CONFIG_FILE.is_file()


class TestShippedConfigFile:
    """``app/data/kerstdiner.yaml``, which every deploy applies."""

    def test_loads_and_is_valid(self) -> None:
        config = load_config_file(CONFIG_FILE)

        assert config.reset >= 1
        assert config.households
        assert config.dishes
        assert config.servies

    def test_loads_without_a_path(self) -> None:
        assert load_config_file() == load_config_file(CONFIG_FILE)

    def test_no_dish_is_made_for_kind(self) -> None:
        config = load_config_file(CONFIG_FILE)

        for dish in config.dishes:
            assert GuestCategory.KIND not in dish.categories
