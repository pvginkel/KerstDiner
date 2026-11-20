"""The config file, ``app/data/kerstdiner.yaml``: households, dishes and servies.

The deploy's migration step syncs it into the database (``ConfigSyncService``);
the testing endpoint ``POST /api/testing/reset`` takes the same shape as JSON.
docs/design.md, "The config file", describes every field.
"""

from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.exceptions import ConfigurationError
from app.models.guest_category import DISH_CATEGORIES, GuestCategory

CONFIG_FILE = Path(__file__).resolve().parent.parent / "data" / "kerstdiner.yaml"
"""The config file the deploy applies."""

ConfigKey = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
        description="Never changes: lower case letters, digits and dashes",
    ),
]
ConfigName = Annotated[str, Field(min_length=1, max_length=200)]
ImageFile = Annotated[
    str,
    Field(
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        description="A photo's file name, without a directory",
    ),
]
People = Annotated[int, Field(ge=0, le=99)]


class _ConfigModel(BaseModel):
    """A part of the config file: a key it does not know is an error."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class GuessConfig(_ConfigModel):
    """The operator's guess of who a household brings; a category left out is 0."""

    vegan: People = 0
    vegetarisch: People = 0
    normaal: People = 0
    kind: People = Field(default=0, description="Children under 6: a kindermenu")

    def people(self, category: GuestCategory) -> int:
        """The guessed number of people of ``category``."""
        return int(getattr(self, category.value))


class HouseholdConfig(_ConfigModel):
    """A household (a Party) as the config gives it."""

    key: ConfigKey
    name: ConfigName
    guess: GuessConfig = Field(default_factory=GuessConfig)


class DishConfig(_ConfigModel):
    """A dish as the config gives it; without ``for`` it is made for all three groups."""

    key: ConfigKey
    name: ConfigName
    made_for: list[GuestCategory] | None = Field(
        default=None,
        alias="for",
        description="vegan, vegetarisch and normaal at most; left out, all three",
    )
    image: ImageFile | None = None

    @model_validator(mode="after")
    def _check_made_for(self) -> Self:
        if self.made_for is None:
            return self
        if not self.made_for:
            raise ValueError(f"dish {self.key}: 'for' names no group")
        if len(set(self.made_for)) != len(self.made_for):
            raise ValueError(f"dish {self.key}: 'for' names a group twice")
        if GuestCategory.KIND in self.made_for:
            raise ValueError(
                f"dish {self.key}: no dish is made for kind, the kindermenu <6jr; "
                "'for' names vegan, vegetarisch and normaal at most"
            )
        return self

    @property
    def categories(self) -> tuple[GuestCategory, ...]:
        """The Guest Categories the dish is made for, in display order."""
        if self.made_for is None:
            return DISH_CATEGORIES
        return tuple(c for c in DISH_CATEGORIES if c in self.made_for)


class TablewareConfig(_ConfigModel):
    """A servies item (a Tableware Item) as the config gives it."""

    key: ConfigKey
    text: ConfigName = Field(description='What it is, such as "20 borden"')
    image: ImageFile | None = None


class KerstDinerConfig(_ConfigModel):
    """The whole config file."""

    reset: int = Field(
        default=0,
        ge=0,
        description="Raise it to wipe every answer, claim and link on the next deploy",
    )
    households: list[HouseholdConfig] = Field(default_factory=list)
    dishes: list[DishConfig] = Field(default_factory=list)
    servies: list[TablewareConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_unique_keys(self) -> Self:
        for section, items in (
            ("households", self.households),
            ("dishes", self.dishes),
            ("servies", self.servies),
        ):
            keys = [item.key for item in items]
            duplicates = sorted({key for key in keys if keys.count(key) > 1})
            if duplicates:
                raise ValueError(
                    f"{section}: key {', '.join(duplicates)} is used twice"
                )
        return self


def load_config_file(path: Path = CONFIG_FILE) -> KerstDinerConfig:
    """Read and check the config file.

    Raises:
        ConfigurationError: The file is missing, is not YAML, or does not
            describe a valid config; the message says where.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigurationError(
            f"Cannot read the config file {path}: {error}"
        ) from error
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigurationError(
            f"The config file {path} is not valid YAML: {error}"
        ) from error
    if data is None:
        data = {}
    try:
        return KerstDinerConfig.model_validate(data)
    except ValidationError as error:
        raise ConfigurationError(
            f"The config file {path} is not valid: {error}"
        ) from error
