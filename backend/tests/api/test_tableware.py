"""GET /api/tableware and PUT|DELETE /api/tableware/<id>/claim: the servies tiles."""

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
        r.message
        for r in session.scalars(select(ChangeReport).order_by(ChangeReport.id))
    ]


def _answer_coming(client: FlaskClient, headers: dict[str, str]):
    response = client.put(
        "/api/party/answer",
        headers=headers,
        json={
            "answer": "coming",
            "counts": {"vegan": 0, "vegetarisch": 0, "normaal": 2, "kind": 0},
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
def borden_id(seeded: AppliedConfig) -> int:
    return seeded.servies[0].id


class TestTablewareApi:
    # -- GET /api/tableware ------------------------------------------------

    def test_list_tableware(
        self,
        client: FlaskClient,
        seeded: AppliedConfig,
        jansen_headers: dict[str, str],
    ):
        response = client.get("/api/tableware", headers=jansen_headers)

        assert response.status_code == 200
        borden, glazen = seeded.servies
        assert response.get_json() == {
            "items": [
                {
                    "id": borden.id,
                    "text": "20 borden",
                    "image": "borden.jpg",
                    "status": "free",
                    "brought_by": None,
                },
                {
                    "id": glazen.id,
                    "text": "20 wijnglazen",
                    "image": None,
                    "status": "free",
                    "brought_by": None,
                },
            ]
        }

    def test_list_tableware_shows_who_brings_what(
        self,
        client: FlaskClient,
        borden_id: int,
        jansen_headers: dict[str, str],
        de_boer_headers: dict[str, str],
    ):
        _answer_coming(client, jansen_headers)
        client.put(f"/api/tableware/{borden_id}/claim", headers=jansen_headers)

        mine = client.get("/api/tableware", headers=jansen_headers).get_json()["items"]
        theirs = client.get("/api/tableware", headers=de_boer_headers).get_json()[
            "items"
        ]

        assert (mine[0]["status"], mine[0]["brought_by"]) == (
            "yours",
            "Familie Jansen",
        )
        assert (theirs[0]["status"], theirs[0]["brought_by"]) == (
            "taken",
            "Familie Jansen",
        )
        assert mine[1]["status"] == theirs[1]["status"] == "free"

    def test_list_tableware_without_a_token(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        assert client.get("/api/tableware").status_code == 401

    def test_list_tableware_with_an_unknown_token(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        response = client.get("/api/tableware", headers=link_headers("nope"))

        assert response.status_code == 401
        assert response.get_json()["error"] == UNKNOWN_LINK_MESSAGE

    # -- PUT /api/tableware/<id>/claim -------------------------------------

    def test_claim_takes_the_item(
        self,
        client: FlaskClient,
        session: Session,
        borden_id: int,
        jansen_headers: dict[str, str],
    ):
        _answer_coming(client, jansen_headers)

        response = client.put(
            f"/api/tableware/{borden_id}/claim", headers=jansen_headers
        )

        assert response.status_code == 200
        assert response.get_json() == {
            "id": borden_id,
            "text": "20 borden",
            "image": "borden.jpg",
            "status": "yours",
            "brought_by": "Familie Jansen",
        }
        assert _reports(session)[-1] == "Familie Jansen neemt 20 borden mee."

    def test_claim_of_an_item_you_have_changes_nothing(
        self,
        client: FlaskClient,
        session: Session,
        borden_id: int,
        jansen_headers: dict[str, str],
    ):
        _answer_coming(client, jansen_headers)
        client.put(f"/api/tableware/{borden_id}/claim", headers=jansen_headers)
        reports = _reports(session)

        response = client.put(
            f"/api/tableware/{borden_id}/claim", headers=jansen_headers
        )

        assert response.status_code == 200
        assert response.get_json()["status"] == "yours"
        assert _reports(session) == reports

    def test_claim_of_an_item_another_household_brings(
        self,
        client: FlaskClient,
        session: Session,
        borden_id: int,
        jansen_headers: dict[str, str],
        de_boer_headers: dict[str, str],
    ):
        _answer_coming(client, jansen_headers)
        _answer_coming(client, de_boer_headers)
        client.put(f"/api/tableware/{borden_id}/claim", headers=jansen_headers)
        reports = _reports(session)

        response = client.put(
            f"/api/tableware/{borden_id}/claim", headers=de_boer_headers
        )

        assert response.status_code == 409
        body = response.get_json()
        assert body["code"] == "CLAIMED_BY_OTHER"
        assert body["error"] == "Dit servies is net door Familie Jansen gekozen"
        assert _reports(session) == reports

    def test_claim_by_a_household_that_has_not_answered(
        self,
        client: FlaskClient,
        session: Session,
        borden_id: int,
        els_headers: dict[str, str],
    ):
        response = client.put(f"/api/tableware/{borden_id}/claim", headers=els_headers)

        assert response.status_code == 409
        assert response.get_json()["code"] == "INVALID_OPERATION"
        assert _reports(session) == []

    def test_claim_by_a_household_that_declined(
        self, client: FlaskClient, borden_id: int, els_headers: dict[str, str]
    ):
        client.put(
            "/api/party/answer", headers=els_headers, json={"answer": "not_coming"}
        )

        response = client.put(f"/api/tableware/{borden_id}/claim", headers=els_headers)

        assert response.status_code == 409
        assert response.get_json()["code"] == "INVALID_OPERATION"

    def test_claim_unknown_item(
        self, client: FlaskClient, jansen_headers: dict[str, str]
    ):
        _answer_coming(client, jansen_headers)

        response = client.put("/api/tableware/999999999/claim", headers=jansen_headers)

        assert response.status_code == 404
        assert response.get_json()["code"] == "RECORD_NOT_FOUND"

    def test_claim_with_an_item_id_that_is_no_number(
        self, client: FlaskClient, jansen_headers: dict[str, str]
    ):
        response = client.put("/api/tableware/borden/claim", headers=jansen_headers)

        assert response.status_code == 404

    def test_claim_without_a_token(self, client: FlaskClient, borden_id: int):
        assert client.put(f"/api/tableware/{borden_id}/claim").status_code == 401

    def test_claim_with_an_unknown_token(self, client: FlaskClient, borden_id: int):
        response = client.put(
            f"/api/tableware/{borden_id}/claim", headers=link_headers("nope")
        )

        assert response.status_code == 401
        assert response.get_json()["error"] == UNKNOWN_LINK_MESSAGE

    # -- DELETE /api/tableware/<id>/claim ----------------------------------

    def test_release_gives_the_item_back(
        self,
        client: FlaskClient,
        session: Session,
        borden_id: int,
        jansen_headers: dict[str, str],
    ):
        _answer_coming(client, jansen_headers)
        client.put(f"/api/tableware/{borden_id}/claim", headers=jansen_headers)

        response = client.delete(
            f"/api/tableware/{borden_id}/claim", headers=jansen_headers
        )

        assert response.status_code == 200
        body = response.get_json()
        assert body["id"] == borden_id
        assert body["status"] == "free"
        assert body["brought_by"] is None
        assert _reports(session)[-1] == "Familie Jansen neemt 20 borden toch niet mee."

    def test_release_of_an_item_nobody_brings_changes_nothing(
        self,
        client: FlaskClient,
        session: Session,
        borden_id: int,
        jansen_headers: dict[str, str],
    ):
        response = client.delete(
            f"/api/tableware/{borden_id}/claim", headers=jansen_headers
        )

        assert response.status_code == 200
        assert response.get_json()["status"] == "free"
        assert _reports(session) == []

    def test_release_of_an_item_another_household_brings(
        self,
        client: FlaskClient,
        borden_id: int,
        jansen_headers: dict[str, str],
        de_boer_headers: dict[str, str],
    ):
        _answer_coming(client, jansen_headers)
        client.put(f"/api/tableware/{borden_id}/claim", headers=jansen_headers)

        response = client.delete(
            f"/api/tableware/{borden_id}/claim", headers=de_boer_headers
        )

        assert response.status_code == 409
        assert response.get_json()["code"] == "CLAIMED_BY_OTHER"
        items = client.get("/api/tableware", headers=jansen_headers).get_json()["items"]
        assert items[0]["brought_by"] == "Familie Jansen"

    def test_release_unknown_item(
        self, client: FlaskClient, jansen_headers: dict[str, str]
    ):
        response = client.delete(
            "/api/tableware/999999999/claim", headers=jansen_headers
        )

        assert response.status_code == 404
        assert response.get_json()["code"] == "RECORD_NOT_FOUND"

    def test_release_without_a_token(self, client: FlaskClient, borden_id: int):
        assert client.delete(f"/api/tableware/{borden_id}/claim").status_code == 401

    def test_release_with_an_unknown_token(self, client: FlaskClient, borden_id: int):
        response = client.delete(
            f"/api/tableware/{borden_id}/claim", headers=link_headers("nope")
        )

        assert response.status_code == 401
        assert response.get_json()["error"] == UNKNOWN_LINK_MESSAGE

    def test_a_released_item_can_be_taken_by_another_household(
        self,
        client: FlaskClient,
        borden_id: int,
        jansen_headers: dict[str, str],
        de_boer_headers: dict[str, str],
    ):
        _answer_coming(client, jansen_headers)
        _answer_coming(client, de_boer_headers)
        client.put(f"/api/tableware/{borden_id}/claim", headers=jansen_headers)
        client.delete(f"/api/tableware/{borden_id}/claim", headers=jansen_headers)

        response = client.put(
            f"/api/tableware/{borden_id}/claim", headers=de_boer_headers
        )

        assert response.status_code == 200
        assert response.get_json()["brought_by"] == "Familie de Boer"
