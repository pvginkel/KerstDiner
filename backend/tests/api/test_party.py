"""GET /api/party and PUT /api/party/answer: a household's own answer."""

from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.change_report import ChangeReport
from app.models.dish import Dish
from app.models.tableware_item import TablewareItem
from app.services.config_sync_service import AppliedConfig
from tests.conftest import link_headers

UNKNOWN_LINK_MESSAGE = "Gebruik de persoonlijke link uit je e-mail"


def _reports(session: Session) -> list[str]:
    return [
        r.message
        for r in session.scalars(select(ChangeReport).order_by(ChangeReport.id))
    ]


def _counts(vegan: int = 0, vegetarisch: int = 0, normaal: int = 0, kind: int = 0):
    return {
        "vegan": vegan,
        "vegetarisch": vegetarisch,
        "normaal": normaal,
        "kind": kind,
    }


@pytest.fixture
def jansen_headers(seeded: AppliedConfig) -> dict[str, str]:
    return link_headers(seeded.parties[0].link_token)


@pytest.fixture
def de_boer_headers(seeded: AppliedConfig) -> dict[str, str]:
    return link_headers(seeded.parties[1].link_token)


class TestPartyApi:
    # -- GET /api/party ----------------------------------------------------

    def test_get_party_before_answering_shows_the_guess(
        self, client: FlaskClient, jansen_headers: dict[str, str], seeded: AppliedConfig
    ):
        response = client.get("/api/party", headers=jansen_headers)

        assert response.status_code == 200
        assert response.get_json() == {
            "id": seeded.parties[0].id,
            "name": "Familie Jansen",
            "answer": "unanswered",
            "counts": _counts(vegetarisch=1, normaal=2, kind=2),
            "people": 5,
            "answered_at": None,
        }

    def test_get_party_returns_the_household_of_the_token(
        self, client: FlaskClient, de_boer_headers: dict[str, str]
    ):
        body = client.get("/api/party", headers=de_boer_headers).get_json()

        assert body["name"] == "Familie de Boer"
        assert body["counts"] == _counts(normaal=2)
        assert body["people"] == 2

    def test_get_party_after_answering(
        self, client: FlaskClient, jansen_headers: dict[str, str]
    ):
        client.put(
            "/api/party/answer",
            headers=jansen_headers,
            json={"answer": "coming", "counts": _counts(vegan=1, normaal=1, kind=1)},
        )

        body = client.get("/api/party", headers=jansen_headers).get_json()

        assert body["answer"] == "coming"
        assert body["counts"] == _counts(vegan=1, normaal=1, kind=1)
        assert body["people"] == 3
        assert body["answered_at"] is not None

    def test_get_party_without_a_token(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        response = client.get("/api/party")

        assert response.status_code == 401
        assert response.get_json()["error"] == UNKNOWN_LINK_MESSAGE
        assert response.get_json()["code"] == "AUTHENTICATION_REQUIRED"

    def test_get_party_with_an_empty_token(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        response = client.get("/api/party", headers=link_headers(""))

        assert response.status_code == 401
        assert response.get_json()["error"] == UNKNOWN_LINK_MESSAGE

    def test_get_party_with_an_over_long_token(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        response = client.get("/api/party", headers=link_headers("x" * 65))

        assert response.status_code == 400

    def test_get_party_with_an_unknown_token(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        response = client.get("/api/party", headers=link_headers("no-such-token"))

        assert response.status_code == 401
        assert response.get_json()["error"] == UNKNOWN_LINK_MESSAGE
        assert response.get_json()["code"] == "AUTHENTICATION_REQUIRED"

    def test_get_party_with_a_replaced_token(
        self, client: FlaskClient, seeded: AppliedConfig, container: Any
    ):
        party = seeded.parties[0]
        old_token = party.link_token
        container.party_service().replace_link(party.id)

        response = client.get("/api/party", headers=link_headers(old_token))

        assert response.status_code == 401
        assert response.get_json()["error"] == UNKNOWN_LINK_MESSAGE

    # -- PUT /api/party/answer ---------------------------------------------

    def test_answer_coming(
        self,
        client: FlaskClient,
        session: Session,
        jansen_headers: dict[str, str],
        seeded: AppliedConfig,
    ):
        response = client.put(
            "/api/party/answer",
            headers=jansen_headers,
            json={
                "answer": "coming",
                "counts": _counts(vegetarisch=1, normaal=2, kind=2),
            },
        )

        assert response.status_code == 200
        body = response.get_json()
        assert body["id"] == seeded.parties[0].id
        assert body["name"] == "Familie Jansen"
        assert body["answer"] == "coming"
        assert body["counts"] == _counts(vegetarisch=1, normaal=2, kind=2)
        assert body["people"] == 5
        assert body["answered_at"] is not None
        assert _reports(session) == [
            "Familie Jansen komt met 5: 1 vegetarisch, 2 eet alles, 2 kindermenu's."
        ]

    def test_answer_coming_replaces_the_guess(
        self, client: FlaskClient, jansen_headers: dict[str, str]
    ):
        client.put(
            "/api/party/answer",
            headers=jansen_headers,
            json={"answer": "coming", "counts": _counts(vegan=4)},
        )

        body = client.get("/api/party", headers=jansen_headers).get_json()
        assert body["counts"] == _counts(vegan=4)
        assert body["people"] == 4

    def test_answer_coming_with_only_young_children_counts_them_in_people(
        self, client: FlaskClient, jansen_headers: dict[str, str]
    ):
        response = client.put(
            "/api/party/answer",
            headers=jansen_headers,
            json={"answer": "coming", "counts": _counts(kind=1)},
        )

        assert response.status_code == 200
        assert response.get_json()["people"] == 1

    def test_answer_coming_at_the_upper_bound(
        self, client: FlaskClient, jansen_headers: dict[str, str]
    ):
        response = client.put(
            "/api/party/answer",
            headers=jansen_headers,
            json={"answer": "coming", "counts": _counts(normaal=99)},
        )

        assert response.status_code == 200
        assert response.get_json()["counts"]["normaal"] == 99

    def test_the_same_answer_twice_queues_one_report(
        self,
        client: FlaskClient,
        session: Session,
        jansen_headers: dict[str, str],
    ):
        payload = {"answer": "coming", "counts": _counts(normaal=2)}
        first = client.put("/api/party/answer", headers=jansen_headers, json=payload)

        second = client.put("/api/party/answer", headers=jansen_headers, json=payload)

        assert second.status_code == 200
        assert second.get_json()["answered_at"] == first.get_json()["answered_at"]
        assert _reports(session) == ["Familie Jansen komt met 2: 2 eet alles."]

    def test_a_changed_answer_queues_another_report(
        self,
        client: FlaskClient,
        session: Session,
        jansen_headers: dict[str, str],
    ):
        client.put(
            "/api/party/answer",
            headers=jansen_headers,
            json={"answer": "coming", "counts": _counts(normaal=2)},
        )
        client.put(
            "/api/party/answer",
            headers=jansen_headers,
            json={"answer": "coming", "counts": _counts(normaal=2, kind=1)},
        )

        assert _reports(session) == [
            "Familie Jansen komt met 2: 2 eet alles.",
            "Familie Jansen komt met 3: 2 eet alles, 1 kindermenu.",
        ]

    def test_answer_not_coming(
        self,
        client: FlaskClient,
        session: Session,
        de_boer_headers: dict[str, str],
    ):
        response = client.put(
            "/api/party/answer",
            headers=de_boer_headers,
            json={"answer": "not_coming"},
        )

        assert response.status_code == 200
        body = response.get_json()
        assert body["answer"] == "not_coming"
        assert body["counts"] == _counts()
        assert body["people"] == 0
        assert body["answered_at"] is not None
        assert _reports(session) == ["Familie de Boer komt niet."]

    def test_answer_not_coming_ignores_counts_it_is_given(
        self, client: FlaskClient, de_boer_headers: dict[str, str]
    ):
        response = client.put(
            "/api/party/answer",
            headers=de_boer_headers,
            json={"answer": "not_coming", "counts": _counts(normaal=3)},
        )

        assert response.status_code == 200
        assert response.get_json()["counts"] == _counts()
        assert response.get_json()["people"] == 0

    def test_answer_not_coming_twice_queues_one_report(
        self,
        client: FlaskClient,
        session: Session,
        de_boer_headers: dict[str, str],
    ):
        for _ in range(2):
            response = client.put(
                "/api/party/answer",
                headers=de_boer_headers,
                json={"answer": "not_coming"},
            )
            assert response.status_code == 200

        assert _reports(session) == ["Familie de Boer komt niet."]

    def test_answer_not_coming_releases_dishes_and_servies(
        self,
        client: FlaskClient,
        session: Session,
        seeded: AppliedConfig,
        jansen_headers: dict[str, str],
        de_boer_headers: dict[str, str],
    ):
        soep, rollade, _ = seeded.dishes
        borden, glazen = seeded.servies
        for headers in (jansen_headers, de_boer_headers):
            client.put(
                "/api/party/answer",
                headers=headers,
                json={"answer": "coming", "counts": _counts(normaal=2)},
            )
        for response in (
            client.put(f"/api/dishes/{soep.id}/claim", headers=jansen_headers),
            client.put(f"/api/dishes/{rollade.id}/claim", headers=de_boer_headers),
            client.put(f"/api/tableware/{borden.id}/claim", headers=jansen_headers),
            client.put(f"/api/tableware/{glazen.id}/claim", headers=de_boer_headers),
        ):
            assert response.status_code == 200

        response = client.put(
            "/api/party/answer",
            headers=jansen_headers,
            json={"answer": "not_coming"},
        )

        assert response.status_code == 200
        session.expire_all()
        dishes = {d.key: d.made_by_id for d in session.scalars(select(Dish))}
        servies = {
            t.key: t.brought_by_id for t in session.scalars(select(TablewareItem))
        }
        assert dishes == {
            "soep": None,
            "rollade": seeded.parties[1].id,
            "wellington": None,
        }
        assert servies == {"borden": None, "glazen": seeded.parties[1].id}

    def test_answer_coming_again_after_declining(
        self, client: FlaskClient, jansen_headers: dict[str, str]
    ):
        client.put(
            "/api/party/answer", headers=jansen_headers, json={"answer": "not_coming"}
        )

        response = client.put(
            "/api/party/answer",
            headers=jansen_headers,
            json={"answer": "coming", "counts": _counts(normaal=1)},
        )

        assert response.status_code == 200
        assert response.get_json()["answer"] == "coming"
        assert response.get_json()["people"] == 1

    @pytest.mark.parametrize(
        ("payload", "case"),
        [
            ({"answer": "coming"}, "coming without counts"),
            ({"answer": "coming", "counts": None}, "coming with null counts"),
            (
                {"answer": "coming", "counts": _counts()},
                "coming with nobody",
            ),
            (
                {"answer": "coming", "counts": {"vegan": 1, "vegetarisch": 0}},
                "missing count fields",
            ),
            (
                {
                    "answer": "coming",
                    "counts": {
                        "vegetarisch": 0,
                        "normaal": 1,
                        "kind": 0,
                    },
                },
                "missing vegan",
            ),
            (
                {"answer": "coming", "counts": _counts(normaal=-1, vegan=2)},
                "negative count",
            ),
            (
                {"answer": "coming", "counts": _counts(normaal=100)},
                "count over 99",
            ),
            (
                {"answer": "coming", "counts": {**_counts(normaal=1), "baby": 1}},
                "unknown count field",
            ),
            (
                {"answer": "coming", "counts": {**_counts(), "normaal": "twee"}},
                "count that is no number",
            ),
            (
                {"answer": "coming", "counts": {**_counts(), "normaal": 1.5}},
                "fractional count",
            ),
            (
                {"answer": "not_coming", "counts": _counts(normaal=-1)},
                "invalid counts of a decline",
            ),
            ({"answer": "maybe", "counts": _counts(normaal=1)}, "unknown answer"),
            (
                {"answer": "unanswered", "counts": _counts(normaal=1)},
                "unanswered as the answer",
            ),
            ({"counts": _counts(normaal=1)}, "missing answer"),
            ({"answer": None}, "null answer"),
            (
                {"answer": "coming", "counts": _counts(normaal=1), "extra": 1},
                "unknown field",
            ),
            ({}, "empty body"),
        ],
        ids=lambda value: value if isinstance(value, str) else None,
    )
    def test_answer_rejects_an_invalid_body(
        self,
        client: FlaskClient,
        session: Session,
        jansen_headers: dict[str, str],
        payload: dict[str, Any],
        case: str,
    ):
        response = client.put("/api/party/answer", headers=jansen_headers, json=payload)

        assert response.status_code == 400, case
        # Nothing was saved or reported.
        body = client.get("/api/party", headers=jansen_headers).get_json()
        assert body["answer"] == "unanswered"
        assert body["answered_at"] is None
        assert body["counts"] == _counts(vegetarisch=1, normaal=2, kind=2)
        assert _reports(session) == []

    def test_answer_rejects_a_body_that_is_not_json(
        self, client: FlaskClient, jansen_headers: dict[str, str]
    ):
        response = client.put(
            "/api/party/answer",
            headers=jansen_headers,
            data="komt wel",
            content_type="application/json",
        )

        assert response.status_code == 400

    def test_answer_without_a_token(self, client: FlaskClient, seeded: AppliedConfig):
        response = client.put(
            "/api/party/answer",
            json={"answer": "coming", "counts": _counts(normaal=1)},
        )

        assert response.status_code == 401
        assert response.get_json()["error"] == UNKNOWN_LINK_MESSAGE

    def test_answer_with_an_unknown_token(
        self, client: FlaskClient, session: Session, seeded: AppliedConfig
    ):
        response = client.put(
            "/api/party/answer",
            headers=link_headers("no-such-token"),
            json={"answer": "coming", "counts": _counts(normaal=1)},
        )

        assert response.status_code == 401
        assert response.get_json()["error"] == UNKNOWN_LINK_MESSAGE
        assert _reports(session) == []

    def test_a_token_only_answers_for_its_own_household(
        self,
        client: FlaskClient,
        jansen_headers: dict[str, str],
        de_boer_headers: dict[str, str],
    ):
        client.put(
            "/api/party/answer",
            headers=jansen_headers,
            json={"answer": "not_coming"},
        )

        body = client.get("/api/party", headers=de_boer_headers).get_json()
        assert body["answer"] == "unanswered"
