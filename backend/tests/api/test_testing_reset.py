"""Tests of ``POST /api/testing/reset``, the Playwright specs' reset."""

import copy
from collections.abc import Generator
from typing import Any

import pytest
from dependency_injector import providers
from flask.testing import FlaskClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, Stage
from app.models.change_report import ChangeReport
from app.models.config_state import ConfigState
from app.models.dish import Dish
from app.models.guest_category import GuestCategory
from app.models.party import Party, PartyAnswer
from app.models.tableware_item import TablewareItem
from app.services.config_sync_service import AppliedConfig
from app.services.container import ServiceContainer
from tests.conftest import SEED_CONFIG, link_headers

URL = "/api/testing/reset"


def _body(**changes: Any) -> dict[str, Any]:
    body = copy.deepcopy(SEED_CONFIG)
    body.update(changes)
    return body


@pytest.fixture
def settings_override(
    container: ServiceContainer, test_settings: Settings
) -> Generator[Any]:
    """Run the app under other settings than the testing ones; undone afterwards."""

    def _override(**changes: Any) -> None:
        container.config.override(
            providers.Object(test_settings.model_copy(update=changes))
        )

    yield _override
    container.config.reset_override()


class TestTestingResetApi:
    """The testing reset: success, validation and the testing-mode guard."""

    def test_applies_the_config_and_answers_with_what_it_created(
        self, client: FlaskClient, session: Session
    ) -> None:
        response = client.post(URL, json=SEED_CONFIG)

        assert response.status_code == 200
        data = response.get_json()
        assert set(data) == {"parties", "dishes", "servies"}
        assert [p["key"] for p in data["parties"]] == ["jansen", "de-boer", "tante-els"]
        assert [p["name"] for p in data["parties"]] == [
            "Familie Jansen",
            "Familie de Boer",
            "Tante Els",
        ]
        assert [d["key"] for d in data["dishes"]] == ["soep", "rollade", "wellington"]
        assert [t["key"] for t in data["servies"]] == ["borden", "glazen"]
        assert set(data["parties"][0]) == {"id", "key", "name", "link_token"}
        assert set(data["dishes"][0]) == {"id", "key"}
        assert set(data["servies"][0]) == {"id", "key"}

    def test_the_answer_matches_the_database(
        self, client: FlaskClient, session: Session
    ) -> None:
        data = client.post(URL, json=SEED_CONFIG).get_json()

        parties = session.scalars(select(Party).order_by(Party.position)).all()
        assert [(p["id"], p["key"], p["link_token"]) for p in data["parties"]] == [
            (p.id, p.key, p.link_token) for p in parties
        ]
        dishes = session.scalars(select(Dish).order_by(Dish.position)).all()
        assert [(d["id"], d["key"]) for d in data["dishes"]] == [
            (d.id, d.key) for d in dishes
        ]
        servies = session.scalars(
            select(TablewareItem).order_by(TablewareItem.position)
        ).all()
        assert [(t["id"], t["key"]) for t in data["servies"]] == [
            (t.id, t.key) for t in servies
        ]

    def test_link_tokens_are_unique_and_open_the_households(
        self, client: FlaskClient
    ) -> None:
        data = client.post(URL, json=SEED_CONFIG).get_json()

        tokens = [p["link_token"] for p in data["parties"]]
        assert all(tokens)
        assert len(set(tokens)) == len(tokens)
        for party in data["parties"]:
            response = client.get(
                "/api/party", headers=link_headers(party["link_token"])
            )
            assert response.status_code == 200

    def test_every_reset_issues_new_tokens(self, client: FlaskClient) -> None:
        first = client.post(URL, json=SEED_CONFIG).get_json()
        second = client.post(URL, json=SEED_CONFIG).get_json()

        old = {p["link_token"] for p in first["parties"]}
        new = {p["link_token"] for p in second["parties"]}
        assert old.isdisjoint(new)
        old_response = client.get(
            "/api/party", headers=link_headers(first["parties"][0]["link_token"])
        )
        assert old_response.status_code == 401

    def test_wipes_answers_claims_and_the_report_queue(
        self,
        client: FlaskClient,
        seeded: AppliedConfig,
        container: ServiceContainer,
        session: Session,
    ) -> None:
        jansen = seeded.parties[0]
        container.party_service().save_answer(
            jansen, PartyAnswer.COMING, {GuestCategory.NORMAAL: 3}
        )
        seeded.dishes[0].made_by = jansen
        session.flush()
        assert session.scalar(select(func.count()).select_from(ChangeReport))

        response = client.post(URL, json=SEED_CONFIG)

        assert response.status_code == 200
        session.expire_all()
        parties = session.scalars(select(Party)).all()
        assert all(p.answer == PartyAnswer.UNANSWERED for p in parties)
        assert all(d.made_by_id is None for d in session.scalars(select(Dish)))
        assert session.scalar(select(func.count()).select_from(ChangeReport)) == 0

    def test_replaces_the_shipped_data(
        self, client: FlaskClient, session: Session
    ) -> None:
        body = {
            "households": [{"key": "enige", "name": "Enige", "guess": {"vegan": 1}}]
        }

        data = client.post(URL, json=body).get_json()

        assert [p["key"] for p in data["parties"]] == ["enige"]
        assert data["dishes"] == []
        assert data["servies"] == []
        assert set(session.scalars(select(Party.key))) == {"enige"}
        assert session.scalar(select(func.count()).select_from(Dish)) == 0

    def test_empty_object_is_an_empty_config(
        self, client: FlaskClient, session: Session
    ) -> None:
        response = client.post(URL, json={})

        assert response.status_code == 200
        assert response.get_json() == {"parties": [], "dishes": [], "servies": []}

    def test_records_the_reset_of_the_body(
        self, client: FlaskClient, session: Session
    ) -> None:
        client.post(URL, json=_body(reset=9))

        session.expire_all()
        state = session.get(ConfigState, 1)
        assert state is not None
        assert state.reset_applied == 9

    def test_applies_images_and_groups(
        self, client: FlaskClient, session: Session
    ) -> None:
        client.post(URL, json=SEED_CONFIG)

        rollade = session.scalars(select(Dish).where(Dish.key == "rollade")).one()
        soep = session.scalars(select(Dish).where(Dish.key == "soep")).one()
        assert rollade.categories == {GuestCategory.NORMAAL}
        assert soep.image == "pompoensoep.jpg"
        assert len(soep.categories) == 3

    @pytest.mark.parametrize(
        "dish",
        [
            {"key": "a", "name": "A", "for": ["kind"]},
            {"key": "a", "name": "A", "for": ["normaal", "kind"]},
            {"key": "a", "name": "A", "for": []},
            {"key": "a", "name": "A", "for": ["vegan", "vegan"]},
            {"key": "a", "name": "A", "for": ["onbekend"]},
            {"key": "a", "name": "A", "image": "map/foto.jpg"},
            {"key": "A", "name": "A"},
            {"key": "a", "name": "A", "extra": True},
            {"key": "a"},
        ],
    )
    def test_invalid_dish_is_refused(
        self, client: FlaskClient, session: Session, dish: dict[str, Any]
    ) -> None:
        response = client.post(URL, json=_body(dishes=[dish]))

        assert response.status_code == 400

    @pytest.mark.parametrize(
        "changes",
        [
            {
                "households": [
                    {"key": "a", "name": "A"},
                    {"key": "a", "name": "B"},
                ]
            },
            {"dishes": [{"key": "a", "name": "A"}, {"key": "a", "name": "B"}]},
            {"servies": [{"key": "a", "text": "A"}, {"key": "a", "text": "B"}]},
            {"gasten": []},
            {"reset": -1},
            {"reset": "veel"},
            {"households": [{"key": "a", "name": "A", "guess": {"baby": 1}}]},
            {"households": [{"key": "a", "name": "A", "guess": {"vegan": -1}}]},
            {"households": "iedereen"},
            {"servies": [{"key": "a", "name": "A"}]},
        ],
    )
    def test_invalid_body_is_refused(
        self, client: FlaskClient, changes: dict[str, Any]
    ) -> None:
        response = client.post(URL, json=_body(**changes))

        assert response.status_code == 400

    def test_an_invalid_body_changes_nothing(
        self,
        client: FlaskClient,
        seeded: AppliedConfig,
        session: Session,
    ) -> None:
        tokens = {p.key: p.link_token for p in seeded.parties}
        body = _body(dishes=[{"key": "a", "name": "A", "for": ["kind"]}])

        response = client.post(URL, json=body)

        assert response.status_code == 400
        session.expire_all()
        assert {p.key: p.link_token for p in session.scalars(select(Party))} == tokens
        assert session.scalar(select(func.count()).select_from(Dish)) == 3

    def test_duplicate_key_message_names_the_key(self, client: FlaskClient) -> None:
        body = _body(dishes=[{"key": "a", "name": "A"}, {"key": "a", "name": "B"}])

        response = client.post(URL, json=body)

        assert response.status_code == 400
        assert "used twice" in response.get_data(as_text=True)

    def test_kind_message_explains_the_kindermenu(self, client: FlaskClient) -> None:
        body = _body(dishes=[{"key": "a", "name": "A", "for": ["kind"]}])

        response = client.post(URL, json=body)

        assert response.status_code == 400
        assert "kindermenu" in response.get_data(as_text=True)

    def test_a_body_that_is_not_an_object_is_refused(self, client: FlaskClient) -> None:
        response = client.post(URL, json=["jansen"])

        assert response.status_code == 400

    @pytest.mark.parametrize("data", ["", "{not json"])
    def test_an_empty_or_malformed_json_body_is_refused(
        self, client: FlaskClient, data: str
    ) -> None:
        response = client.post(URL, data=data, content_type="application/json")

        assert response.status_code == 400

    def test_get_is_not_allowed(self, client: FlaskClient) -> None:
        assert client.get(URL).status_code == 405

    def test_refused_outside_testing_mode(
        self,
        client: FlaskClient,
        seeded: AppliedConfig,
        settings_override: Any,
        session: Session,
    ) -> None:
        settings_override(flask_env="development")
        tokens = {p.key: p.link_token for p in seeded.parties}

        response = client.post(URL, json={})

        assert response.status_code == 400
        data = response.get_json()
        assert data["code"] == "ROUTE_NOT_AVAILABLE"
        session.expire_all()
        assert {p.key: p.link_token for p in session.scalars(select(Party))} == tokens

    def test_refused_in_production_mode(
        self, client: FlaskClient, settings_override: Any
    ) -> None:
        settings_override(flask_env="production")

        response = client.post(URL, json=SEED_CONFIG)

        assert response.status_code == 400
        assert response.get_json()["code"] == "ROUTE_NOT_AVAILABLE"

    def test_refused_on_the_prd_stage_even_when_testing(
        self,
        client: FlaskClient,
        seeded: AppliedConfig,
        settings_override: Any,
        session: Session,
    ) -> None:
        settings_override(flask_env="testing", stage=Stage("prd"))
        tokens = {p.key: p.link_token for p in seeded.parties}

        response = client.post(URL, json={})

        assert response.status_code == 400
        assert response.get_json()["code"] == "ROUTE_NOT_AVAILABLE"
        session.expire_all()
        assert {p.key: p.link_token for p in session.scalars(select(Party))} == tokens

    def test_the_guard_comes_before_the_validation(
        self, client: FlaskClient, settings_override: Any
    ) -> None:
        settings_override(flask_env="development")

        response = client.post(URL, json={"gasten": []})

        assert response.status_code == 400
        assert response.get_json()["code"] == "ROUTE_NOT_AVAILABLE"
