"""GET /api/admin/parties and POST /api/admin/parties/<id>/link: the admin's view."""

from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.change_report import ChangeReport
from app.services.config_sync_service import AppliedConfig
from tests.conftest import link_headers


def _reports(session: Session) -> list[str]:
    return [
        f"{r.party.name}: {r.message}"
        for r in session.scalars(select(ChangeReport).order_by(ChangeReport.id))
    ]


def _counts(vegan: int = 0, vegetarisch: int = 0, normaal: int = 0, kind: int = 0):
    return {
        "vegan": vegan,
        "vegetarisch": vegetarisch,
        "normaal": normaal,
        "kind": kind,
    }


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestAdminApi:
    # -- GET /api/admin/parties --------------------------------------------

    def test_list_parties_in_config_order(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        response = client.get("/api/admin/parties")

        assert response.status_code == 200
        body = response.get_json()
        assert [p["name"] for p in body["parties"]] == [
            "Familie Jansen",
            "Familie de Boer",
            "Tante Els",
        ]

    def test_list_parties_shape(self, client: FlaskClient, seeded: AppliedConfig):
        body = client.get("/api/admin/parties").get_json()

        jansen = seeded.parties[0]
        assert body["parties"][0] == {
            "id": jansen.id,
            "name": "Familie Jansen",
            "answer": "unanswered",
            "counts": _counts(vegetarisch=1, normaal=2, kind=2),
            "people": 5,
            "answered_at": None,
            "link_token": jansen.link_token,
        }
        assert set(body) == {"parties", "totals", "people"}

    def test_list_parties_carries_every_link_token(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        body = client.get("/api/admin/parties").get_json()

        assert [p["link_token"] for p in body["parties"]] == [
            p.link_token for p in seeded.parties
        ]
        assert len({p["link_token"] for p in body["parties"]}) == 3

    def test_list_parties_totals_include_the_guesses(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        body = client.get("/api/admin/parties").get_json()

        assert body["totals"] == _counts(vegan=1, vegetarisch=1, normaal=4, kind=2)
        assert body["people"] == 8

    def test_list_parties_follows_the_answers(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        jansen, de_boer, _ = seeded.parties
        client.put(
            "/api/party/answer",
            headers=link_headers(jansen.link_token),
            json={"answer": "coming", "counts": _counts(vegan=2, kind=1)},
        )
        client.put(
            "/api/party/answer",
            headers=link_headers(de_boer.link_token),
            json={"answer": "not_coming"},
        )

        body = client.get("/api/admin/parties").get_json()

        first, second, third = body["parties"]
        assert first["answer"] == "coming"
        assert first["counts"] == _counts(vegan=2, kind=1)
        assert first["people"] == 3
        assert first["answered_at"] is not None
        assert second["answer"] == "not_coming"
        assert second["counts"] == _counts()
        assert second["people"] == 0
        assert second["answered_at"] is not None
        assert third["answer"] == "unanswered"
        assert third["answered_at"] is None
        # Tante Els has not answered: her guess of 1 vegan still counts.
        assert body["totals"] == _counts(vegan=3, kind=1)
        assert body["people"] == 4

    def test_list_parties_without_households(
        self, client: FlaskClient, apply_config: Any
    ):
        apply_config({"households": []})

        body = client.get("/api/admin/parties").get_json()

        assert body == {"parties": [], "totals": _counts(), "people": 0}

    # -- POST /api/admin/parties/<id>/link ---------------------------------

    def test_replace_link(
        self, client: FlaskClient, session: Session, seeded: AppliedConfig
    ):
        jansen = seeded.parties[0]
        old_token = jansen.link_token

        response = client.post(f"/api/admin/parties/{jansen.id}/link")

        assert response.status_code == 200
        body = response.get_json()
        assert body["id"] == jansen.id
        assert body["name"] == "Familie Jansen"
        assert body["link_token"] != old_token
        assert body["answer"] == "unanswered"
        assert body["counts"] == _counts(vegetarisch=1, normaal=2, kind=2)
        assert body["people"] == 5
        assert body["answered_at"] is None

    def test_replace_link_stops_the_old_link(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        jansen = seeded.parties[0]
        old_token = jansen.link_token

        new_token = client.post(f"/api/admin/parties/{jansen.id}/link").get_json()[
            "link_token"
        ]

        old = client.get("/api/party", headers=link_headers(old_token))
        new = client.get("/api/party", headers=link_headers(new_token))
        assert old.status_code == 401
        assert old.get_json()["error"] == "Gebruik de persoonlijke link uit je e-mail"
        assert new.status_code == 200
        assert new.get_json()["name"] == "Familie Jansen"

    def test_replace_link_shows_in_the_list(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        jansen = seeded.parties[0]

        new_token = client.post(f"/api/admin/parties/{jansen.id}/link").get_json()[
            "link_token"
        ]

        tokens = [
            p["link_token"]
            for p in client.get("/api/admin/parties").get_json()["parties"]
        ]
        assert tokens == [
            new_token,
            seeded.parties[1].link_token,
            seeded.parties[2].link_token,
        ]

    def test_replace_link_leaves_the_other_links_alone(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        jansen, de_boer, _ = seeded.parties

        client.post(f"/api/admin/parties/{jansen.id}/link")

        response = client.get("/api/party", headers=link_headers(de_boer.link_token))
        assert response.status_code == 200

    def test_replace_link_queues_no_report(
        self, client: FlaskClient, session: Session, seeded: AppliedConfig
    ):
        client.post(f"/api/admin/parties/{seeded.parties[0].id}/link")

        assert _reports(session) == []

    def test_replace_link_unknown_party(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        response = client.post("/api/admin/parties/999999999/link")

        assert response.status_code == 404
        assert response.get_json()["code"] == "RECORD_NOT_FOUND"

    def test_replace_link_with_an_id_that_is_no_number(
        self, client: FlaskClient, seeded: AppliedConfig
    ):
        assert client.post("/api/admin/parties/jansen/link").status_code == 404

    # -- OIDC enabled ------------------------------------------------------

    def test_list_parties_without_login(self, oidc_client: Any, seeded: AppliedConfig):
        response = oidc_client.get("/api/admin/parties")

        assert response.status_code == 401

    def test_list_parties_without_the_admin_role(
        self, oidc_client: Any, generate_test_jwt: Any, seeded: AppliedConfig
    ):
        token = generate_test_jwt(roles=["reader"])

        response = oidc_client.get("/api/admin/parties", headers=_bearer(token))

        assert response.status_code == 403

    def test_list_parties_with_the_admin_role(
        self, oidc_client: Any, generate_test_jwt: Any, seeded: AppliedConfig
    ):
        token = generate_test_jwt(roles=["admin"])

        response = oidc_client.get("/api/admin/parties", headers=_bearer(token))

        assert response.status_code == 200
        assert len(response.get_json()["parties"]) == 3

    def test_list_parties_with_an_expired_token(
        self, oidc_client: Any, generate_test_jwt: Any, seeded: AppliedConfig
    ):
        token = generate_test_jwt(expired=True)

        response = oidc_client.get("/api/admin/parties", headers=_bearer(token))

        assert response.status_code == 401

    def test_replace_link_without_login(self, oidc_client: Any, seeded: AppliedConfig):
        jansen = seeded.parties[0]
        old_token = jansen.link_token

        response = oidc_client.post(f"/api/admin/parties/{jansen.id}/link")

        assert response.status_code == 401
        still_works = oidc_client.get("/api/party", headers=link_headers(old_token))
        assert still_works.status_code == 200

    def test_replace_link_without_the_admin_role(
        self, oidc_client: Any, generate_test_jwt: Any, seeded: AppliedConfig
    ):
        jansen = seeded.parties[0]
        token = generate_test_jwt(roles=["reader"])

        response = oidc_client.post(
            f"/api/admin/parties/{jansen.id}/link", headers=_bearer(token)
        )

        assert response.status_code == 403
        still_works = oidc_client.get(
            "/api/party", headers=link_headers(jansen.link_token)
        )
        assert still_works.status_code == 200

    def test_replace_link_with_the_admin_role(
        self, oidc_client: Any, generate_test_jwt: Any, seeded: AppliedConfig
    ):
        jansen = seeded.parties[0]
        old_token = jansen.link_token
        token = generate_test_jwt(roles=["admin"])

        response = oidc_client.post(
            f"/api/admin/parties/{jansen.id}/link", headers=_bearer(token)
        )

        assert response.status_code == 200
        assert response.get_json()["link_token"] != old_token

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/party"),
            ("put", "/api/party/answer"),
            ("get", "/api/dishes"),
            ("put", "/api/dishes/{dish}/claim"),
            ("delete", "/api/dishes/{dish}/claim"),
            ("get", "/api/tableware"),
            ("put", "/api/tableware/{item}/claim"),
            ("delete", "/api/tableware/{item}/claim"),
        ],
    )
    def test_the_household_endpoints_need_no_login(
        self,
        oidc_client: Any,
        seeded: AppliedConfig,
        method: str,
        path: str,
    ):
        jansen = seeded.parties[0]
        # A household must have said it comes before it takes a dish or servies.
        oidc_client.put(
            "/api/party/answer",
            headers=link_headers(jansen.link_token),
            json={"answer": "coming", "counts": _counts(normaal=2)},
        )
        request_path = path.format(dish=seeded.dishes[0].id, item=seeded.servies[0].id)
        kwargs: dict[str, Any] = {"headers": link_headers(jansen.link_token)}
        if request_path.endswith("/answer"):
            kwargs["json"] = {"answer": "coming", "counts": _counts(normaal=2)}

        response = getattr(oidc_client, method)(request_path, **kwargs)

        assert response.status_code == 200
