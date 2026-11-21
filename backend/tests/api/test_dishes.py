"""GET /api/dishes and PUT|DELETE /api/dishes/<id>/claim: the dish tiles."""

from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.change_report import ChangeReport
from app.services.config_sync_service import AppliedConfig
from tests.conftest import link_headers

UNKNOWN_LINK_MESSAGE = "Gebruik de persoonlijke link uit je e-mail"


def _reports(session: Session) -> list[str]:
    return [
        f"{r.party.name}: {r.message}"
        for r in session.scalars(select(ChangeReport).order_by(ChangeReport.id))
    ]


def _answer_coming(client: FlaskClient, headers: dict[str, str], normaal: int = 2):
    response = client.put(
        "/api/party/answer",
        headers=headers,
        json={
            "answer": "coming",
            "counts": {"vegan": 0, "vegetarisch": 0, "normaal": normaal, "kind": 0},
        },
    )
    assert response.status_code == 200


@pytest.fixture
def jansen_headers(seeded: AppliedConfig) -> dict[str, str]:
    return link_headers(seeded.parties[0].link_token)


@pytest.fixture
def de_boer_headers(seeded: AppliedConfig) -> dict[str, str]:
    return link_headers(seeded.parties[1].link_token)


@pytest.fixture
def els_headers(seeded: AppliedConfig) -> dict[str, str]:
    return link_headers(seeded.parties[2].link_token)


@pytest.fixture
def soep_id(seeded: AppliedConfig) -> int:
    return seeded.dishes[0].id


class TestDishesApi:
    # -- GET /api/dishes ---------------------------------------------------

    def test_list_dishes(
        self,
        client: FlaskClient,
        seeded: AppliedConfig,
        jansen_headers: dict[str, str],
    ):
        response = client.get("/api/dishes", headers=jansen_headers)

        assert response.status_code == 200
        soep, rollade, wellington = seeded.dishes
        # Guesses: vegan 1, vegetarisch 1, normaal 4 and kind 2, which no dish counts.
        assert response.get_json() == {
            "dishes": [
                {
                    "id": soep.id,
                    "name": "Pompoensoep",
                    "image": "pompoensoep.jpg",
                    "people": 6,
                    "status": "free",
                    "made_by": None,
                },
                {
                    "id": rollade.id,
                    "name": "Rollade",
                    "image": None,
                    "people": 4,
                    "status": "free",
                    "made_by": None,
                },
                {
                    "id": wellington.id,
                    "name": "Linzen-wellington",
                    "image": "wellington.jpg",
                    "people": 2,
                    "status": "free",
                    "made_by": None,
                },
            ]
        }

    def test_list_dishes_people_follow_the_answers(
        self,
        client: FlaskClient,
        jansen_headers: dict[str, str],
        de_boer_headers: dict[str, str],
    ):
        client.put(
            "/api/party/answer", headers=de_boer_headers, json={"answer": "not_coming"}
        )

        dishes = client.get("/api/dishes", headers=jansen_headers).get_json()["dishes"]

        assert {d["name"]: d["people"] for d in dishes} == {
            "Pompoensoep": 4,
            "Rollade": 2,
            "Linzen-wellington": 2,
        }

    def test_list_dishes_shows_who_makes_what(
        self,
        client: FlaskClient,
        soep_id: int,
        jansen_headers: dict[str, str],
        de_boer_headers: dict[str, str],
    ):
        _answer_coming(client, jansen_headers)
        client.put(f"/api/dishes/{soep_id}/claim", headers=jansen_headers)

        mine = client.get("/api/dishes", headers=jansen_headers).get_json()["dishes"]
        theirs = client.get("/api/dishes", headers=de_boer_headers).get_json()["dishes"]

        assert (mine[0]["status"], mine[0]["made_by"]) == ("yours", "Familie Jansen")
        assert (theirs[0]["status"], theirs[0]["made_by"]) == (
            "taken",
            "Familie Jansen",
        )
        assert mine[1]["status"] == theirs[1]["status"] == "free"

    def test_list_dishes_without_a_token(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        assert client.get("/api/dishes").status_code == 401

    def test_list_dishes_with_an_unknown_token(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        response = client.get("/api/dishes", headers=link_headers("nope"))

        assert response.status_code == 401
        assert response.get_json()["error"] == UNKNOWN_LINK_MESSAGE

    # -- PUT /api/dishes/<id>/claim ----------------------------------------

    def test_claim_takes_the_dish(
        self,
        client: FlaskClient,
        session: Session,
        soep_id: int,
        jansen_headers: dict[str, str],
    ):
        _answer_coming(client, jansen_headers)

        response = client.put(f"/api/dishes/{soep_id}/claim", headers=jansen_headers)

        assert response.status_code == 200
        assert response.get_json() == {
            "id": soep_id,
            "name": "Pompoensoep",
            "image": "pompoensoep.jpg",
            "people": 5,  # Jansen's answer drops the guess of 1 vegetarisch.
            "status": "yours",
            "made_by": "Familie Jansen",
        }
        assert _reports(session)[-1] == "Familie Jansen: Maakt Pompoensoep."

    def test_claim_of_a_dish_you_have_changes_nothing(
        self,
        client: FlaskClient,
        session: Session,
        soep_id: int,
        jansen_headers: dict[str, str],
    ):
        _answer_coming(client, jansen_headers)
        client.put(f"/api/dishes/{soep_id}/claim", headers=jansen_headers)
        reports = _reports(session)

        response = client.put(f"/api/dishes/{soep_id}/claim", headers=jansen_headers)

        assert response.status_code == 200
        assert response.get_json()["status"] == "yours"
        assert _reports(session) == reports

    def test_claim_of_a_dish_another_household_makes(
        self,
        client: FlaskClient,
        session: Session,
        soep_id: int,
        jansen_headers: dict[str, str],
        de_boer_headers: dict[str, str],
    ):
        _answer_coming(client, jansen_headers)
        _answer_coming(client, de_boer_headers)
        client.put(f"/api/dishes/{soep_id}/claim", headers=jansen_headers)
        reports = _reports(session)

        response = client.put(f"/api/dishes/{soep_id}/claim", headers=de_boer_headers)

        assert response.status_code == 409
        body = response.get_json()
        assert body["code"] == "CLAIMED_BY_OTHER"
        assert body["error"] == "Dit gerecht is net door Familie Jansen gekozen"
        assert _reports(session) == reports
        dishes = client.get("/api/dishes", headers=de_boer_headers).get_json()["dishes"]
        assert dishes[0]["status"] == "taken"

    def test_claim_by_a_household_that_has_not_answered(
        self,
        client: FlaskClient,
        session: Session,
        soep_id: int,
        els_headers: dict[str, str],
    ):
        response = client.put(f"/api/dishes/{soep_id}/claim", headers=els_headers)

        assert response.status_code == 409
        assert response.get_json()["code"] == "INVALID_OPERATION"
        assert _reports(session) == []

    def test_claim_by_a_household_that_declined(
        self, client: FlaskClient, soep_id: int, els_headers: dict[str, str]
    ):
        client.put(
            "/api/party/answer", headers=els_headers, json={"answer": "not_coming"}
        )

        response = client.put(f"/api/dishes/{soep_id}/claim", headers=els_headers)

        assert response.status_code == 409
        assert response.get_json()["code"] == "INVALID_OPERATION"

    def test_claim_unknown_dish(
        self, client: FlaskClient, jansen_headers: dict[str, str]
    ):
        _answer_coming(client, jansen_headers)

        response = client.put("/api/dishes/999999999/claim", headers=jansen_headers)

        assert response.status_code == 404
        assert response.get_json()["code"] == "RECORD_NOT_FOUND"

    def test_claim_with_a_dish_id_that_is_no_number(
        self, client: FlaskClient, jansen_headers: dict[str, str]
    ):
        response = client.put("/api/dishes/soep/claim", headers=jansen_headers)

        assert response.status_code == 404

    def test_claim_without_a_token(self, client: FlaskClient, soep_id: int):
        assert client.put(f"/api/dishes/{soep_id}/claim").status_code == 401

    def test_claim_with_an_unknown_token(self, client: FlaskClient, soep_id: int):
        response = client.put(
            f"/api/dishes/{soep_id}/claim", headers=link_headers("nope")
        )

        assert response.status_code == 401
        assert response.get_json()["error"] == UNKNOWN_LINK_MESSAGE

    # -- DELETE /api/dishes/<id>/claim -------------------------------------

    def test_release_gives_the_dish_back(
        self,
        client: FlaskClient,
        session: Session,
        soep_id: int,
        jansen_headers: dict[str, str],
    ):
        _answer_coming(client, jansen_headers)
        client.put(f"/api/dishes/{soep_id}/claim", headers=jansen_headers)

        response = client.delete(f"/api/dishes/{soep_id}/claim", headers=jansen_headers)

        assert response.status_code == 200
        body = response.get_json()
        assert body["id"] == soep_id
        assert body["status"] == "free"
        assert body["made_by"] is None
        assert _reports(session)[-1] == "Familie Jansen: Maakt Pompoensoep toch niet."

    def test_release_of_a_dish_nobody_makes_changes_nothing(
        self,
        client: FlaskClient,
        session: Session,
        soep_id: int,
        jansen_headers: dict[str, str],
    ):
        response = client.delete(f"/api/dishes/{soep_id}/claim", headers=jansen_headers)

        assert response.status_code == 200
        assert response.get_json()["status"] == "free"
        assert _reports(session) == []

    def test_release_of_a_dish_another_household_makes(
        self,
        client: FlaskClient,
        soep_id: int,
        jansen_headers: dict[str, str],
        de_boer_headers: dict[str, str],
    ):
        _answer_coming(client, jansen_headers)
        client.put(f"/api/dishes/{soep_id}/claim", headers=jansen_headers)

        response = client.delete(
            f"/api/dishes/{soep_id}/claim", headers=de_boer_headers
        )

        assert response.status_code == 409
        assert response.get_json()["code"] == "CLAIMED_BY_OTHER"
        dishes = client.get("/api/dishes", headers=jansen_headers).get_json()["dishes"]
        assert dishes[0]["made_by"] == "Familie Jansen"

    def test_release_unknown_dish(
        self, client: FlaskClient, jansen_headers: dict[str, str]
    ):
        response = client.delete("/api/dishes/999999999/claim", headers=jansen_headers)

        assert response.status_code == 404
        assert response.get_json()["code"] == "RECORD_NOT_FOUND"

    def test_release_without_a_token(self, client: FlaskClient, soep_id: int):
        assert client.delete(f"/api/dishes/{soep_id}/claim").status_code == 401

    def test_release_with_an_unknown_token(self, client: FlaskClient, soep_id: int):
        response = client.delete(
            f"/api/dishes/{soep_id}/claim", headers=link_headers("nope")
        )

        assert response.status_code == 401
        assert response.get_json()["error"] == UNKNOWN_LINK_MESSAGE

    def test_a_released_dish_can_be_taken_by_another_household(
        self,
        client: FlaskClient,
        soep_id: int,
        jansen_headers: dict[str, str],
        de_boer_headers: dict[str, str],
    ):
        _answer_coming(client, jansen_headers)
        _answer_coming(client, de_boer_headers)
        client.put(f"/api/dishes/{soep_id}/claim", headers=jansen_headers)
        client.delete(f"/api/dishes/{soep_id}/claim", headers=jansen_headers)

        response = client.put(f"/api/dishes/{soep_id}/claim", headers=de_boer_headers)

        assert response.status_code == 200
        body: dict[str, Any] = response.get_json()
        assert body["made_by"] == "Familie de Boer"
