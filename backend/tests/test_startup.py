"""Tests of the startup hooks: the deploy's config sync."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from flask import Flask
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.config_state import ConfigState
from app.models.dish import Dish, DishGuestCategory
from app.models.guest_category import GuestCategory
from app.models.party import GuestCount, Party, PartyAnswer
from app.models.tableware_item import TablewareItem
from app.schemas.config_file import CONFIG_FILE, load_config_file
from app.services.config_sync_service import ConfigSyncService
from app.startup import load_test_data_hook, post_migration_hook, sync_config_file

_Hook = Callable[[Flask], None]


@contextmanager
def _fresh_session(app: Flask) -> Generator[Session]:
    """A session of its own on the app's database: what a commit made is seen here."""
    session = app.container.session_maker()()  # type: ignore[attr-defined]
    try:
        yield session
    finally:
        session.close()


def _wipe(app: Flask) -> None:
    """Leave the database as an empty one, as before the first deploy."""
    with _fresh_session(app) as session:
        session.execute(delete(Dish))
        session.execute(delete(TablewareItem))
        session.execute(delete(Party))
        session.execute(delete(ConfigState))
        session.commit()


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "kerstdiner.yaml"
    path.write_text(text, encoding="utf-8")
    return path


class TestSyncConfigFile:
    """``sync_config_file`` and the hooks that call it."""

    @pytest.mark.parametrize(
        "hook", [sync_config_file, post_migration_hook, load_test_data_hook]
    )
    def test_applies_the_shipped_file_and_commits(
        self, committed_app: Flask, hook: _Hook
    ) -> None:
        config = load_config_file(CONFIG_FILE)
        _wipe(committed_app)

        hook(committed_app)

        with _fresh_session(committed_app) as session:
            parties = session.scalars(select(Party).order_by(Party.position)).all()
            assert [p.key for p in parties] == [h.key for h in config.households]
            assert [p.name for p in parties] == [h.name for h in config.households]
            assert all(p.answer == PartyAnswer.UNANSWERED for p in parties)
            assert all(p.link_token for p in parties)
            dishes = session.scalars(select(Dish).order_by(Dish.position)).all()
            assert [d.key for d in dishes] == [d.key for d in config.dishes]
            assert [d.categories for d in dishes] == [
                set(d.categories) for d in config.dishes
            ]
            servies = session.scalars(
                select(TablewareItem).order_by(TablewareItem.position)
            ).all()
            assert [t.key for t in servies] == [t.key for t in config.servies]
            state = session.get(ConfigState, 1)
            assert state is not None
            assert state.reset_applied == config.reset

    def test_applies_the_guess_as_the_counts(self, committed_app: Flask) -> None:
        config = load_config_file(CONFIG_FILE)
        _wipe(committed_app)

        sync_config_file(committed_app)

        with _fresh_session(committed_app) as session:
            for household in config.households:
                party = session.scalars(
                    select(Party).where(Party.key == household.key)
                ).one()
                for category in GuestCategory:
                    assert party.people(category) == household.guess.people(category)

    def test_prints_the_summary(
        self, committed_app: Flask, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = load_config_file(CONFIG_FILE)
        _wipe(committed_app)

        sync_config_file(committed_app)

        out = capsys.readouterr().out
        assert (
            f"Config synced: {len(config.households)} households, "
            f"{len(config.dishes)} dishes, {len(config.servies)} servies items"
        ) in out
        assert "Config reset" not in out

    def test_a_second_run_changes_nothing(self, committed_app: Flask) -> None:
        sync_config_file(committed_app)
        with _fresh_session(committed_app) as session:
            before = {p.key: p.link_token for p in session.scalars(select(Party))}

        sync_config_file(committed_app)

        with _fresh_session(committed_app) as session:
            after = {p.key: p.link_token for p in session.scalars(select(Party))}
        assert before
        assert after == before

    def test_a_raised_reset_clears_the_answers_and_says_so(
        self, committed_app: Flask, capsys: pytest.CaptureFixture[str]
    ) -> None:
        config = load_config_file(CONFIG_FILE)
        with _fresh_session(committed_app) as session:
            old_tokens = {p.key: p.link_token for p in session.scalars(select(Party))}
            jansen = session.scalars(select(Party).where(Party.key == "jansen")).one()
            jansen.answer = PartyAnswer.COMING
            jansen.set_people(GuestCategory.NORMAAL, 9)
            session.scalars(select(Dish)).first().made_by = jansen  # type: ignore[union-attr]
            state = session.get(ConfigState, 1)
            assert state is not None
            state.reset_applied = config.reset - 1
            session.commit()

        sync_config_file(committed_app)

        with _fresh_session(committed_app) as session:
            jansen = session.scalars(select(Party).where(Party.key == "jansen")).one()
            assert jansen.answer == PartyAnswer.UNANSWERED
            guess = next(h for h in config.households if h.key == "jansen").guess
            assert jansen.people(GuestCategory.NORMAAL) == guess.normaal
            assert jansen.link_token != old_tokens["jansen"]
            assert all(d.made_by_id is None for d in session.scalars(select(Dish)))
            state = session.get(ConfigState, 1)
            assert state is not None
            assert state.reset_applied == config.reset
        out = capsys.readouterr().out
        assert (
            f"Config reset {config.reset}: every answer, claim and link cleared" in out
        )

    def test_keeps_the_answers_when_the_reset_is_not_raised(
        self, committed_app: Flask, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with _fresh_session(committed_app) as session:
            jansen = session.scalars(select(Party).where(Party.key == "jansen")).one()
            jansen.answer = PartyAnswer.COMING
            jansen.set_people(GuestCategory.NORMAAL, 9)
            session.commit()

        sync_config_file(committed_app)

        with _fresh_session(committed_app) as session:
            jansen = session.scalars(select(Party).where(Party.key == "jansen")).one()
            assert jansen.answer == PartyAnswer.COMING
            assert jansen.people(GuestCategory.NORMAAL) == 9
        assert "Config reset" not in capsys.readouterr().out

    @pytest.mark.parametrize(
        ("text", "message"),
        [
            ("households: [unclosed\n", "is not valid YAML"),
            ("dishes:\n  - {key: a, name: A, for: [kind]}\n", "is not valid"),
            ("servies:\n  - {key: a, text: A}\n  - {key: a, text: B}\n", "twice"),
            ("gasten: []\n", "is not valid"),
        ],
    )
    def test_invalid_file_exits_1(
        self,
        committed_app: Flask,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
        text: str,
        message: str,
    ) -> None:
        path = _write(tmp_path, text)
        monkeypatch.setattr("app.schemas.config_file.CONFIG_FILE", path)

        with pytest.raises(SystemExit) as raised:
            sync_config_file(committed_app)

        assert raised.value.code == 1
        err = capsys.readouterr().err
        assert "Config sync failed" in err
        assert str(path) in err
        assert message in err

    def test_missing_file_exits_1(
        self,
        committed_app: Flask,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("app.schemas.config_file.CONFIG_FILE", tmp_path / "no.yaml")

        with pytest.raises(SystemExit) as raised:
            post_migration_hook(committed_app)

        assert raised.value.code == 1
        assert "Cannot read the config file" in capsys.readouterr().err

    def test_invalid_file_changes_nothing(
        self,
        committed_app: Flask,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        with _fresh_session(committed_app) as session:
            before = session.scalar(select(func.count()).select_from(Party))
        monkeypatch.setattr(
            "app.schemas.config_file.CONFIG_FILE",
            _write(tmp_path, "reset: 99\nhouseholds: [oops\n"),
        )

        with pytest.raises(SystemExit):
            sync_config_file(committed_app)

        with _fresh_session(committed_app) as session:
            assert session.scalar(select(func.count()).select_from(Party)) == before
            state = session.get(ConfigState, 1)
            assert state is not None
            assert state.reset_applied != 99

    def test_a_valid_file_of_its_own_is_applied(
        self,
        committed_app: Flask,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        path = _write(
            tmp_path,
            "reset: 1\n"
            "households:\n  - {key: enige, name: Enige, guess: {vegan: 2}}\n"
            "dishes:\n  - {key: taart, name: Taart}\n"
            "servies:\n  - {key: borden, text: 20 borden}\n",
        )
        monkeypatch.setattr("app.schemas.config_file.CONFIG_FILE", path)

        sync_config_file(committed_app)

        with _fresh_session(committed_app) as session:
            assert set(session.scalars(select(Party.key))) == {"enige"}
            assert set(session.scalars(select(Dish.key))) == {"taart"}
            assert set(session.scalars(select(TablewareItem.key))) == {"borden"}
            assert session.scalar(select(func.count()).select_from(GuestCount)) == 4
            assert (
                session.scalar(select(func.count()).select_from(DishGuestCategory)) == 3
            )

    def test_a_failing_sync_rolls_back_and_raises(
        self,
        committed_app: Flask,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        real_sync = ConfigSyncService.sync
        with _fresh_session(committed_app) as session:
            before = session.scalar(select(func.count()).select_from(Party))

        def sync_then_fail(self: ConfigSyncService, config):  # type: ignore[no-untyped-def]
            real_sync(self, config)
            raise RuntimeError("database went away")

        monkeypatch.setattr(ConfigSyncService, "sync", sync_then_fail)
        monkeypatch.setattr(
            "app.schemas.config_file.CONFIG_FILE",
            _write(tmp_path, "households:\n  - {key: enige, name: Enige}\n"),
        )

        with pytest.raises(RuntimeError, match="database went away"):
            sync_config_file(committed_app)

        with _fresh_session(committed_app) as session:
            assert "enige" not in set(session.scalars(select(Party.key)))
            assert session.scalar(select(func.count()).select_from(Party)) == before
