import asyncio

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.core.config import settings
from app.services import legal_research


def _case_id(client) -> str:
    response = client.post("/api/v1/cases", json={"title": "Synthetic research matter"})
    assert response.status_code == 201
    return response.json()["id"]


def test_legal_research_configuration_does_not_disclose_credentials(client, monkeypatch):
    case_id = _case_id(client)
    monkeypatch.setattr(settings, "indiankanoon_api_token", None)
    monkeypatch.setattr(settings, "indiankanoon_private_key", "test-private-key-material")
    monkeypatch.setattr(settings, "indiankanoon_private_key_path", None)
    monkeypatch.setattr(settings, "indiankanoon_customer_email", "registered@example.test")

    response = client.get(f"/api/v1/cases/{case_id}/legal-research/config")

    assert response.status_code == 200
    payload = response.json()
    indian_kanoon = next(item for item in payload["providers"] if item["provider"] == "indian_kanoon")
    assert indian_kanoon["configured"] is False
    assert "could not be loaded as RSA PEM" in indian_kanoon["message"]
    assert "test-private-key-material" not in response.text


def test_advocate_can_save_and_list_authority_review(client):
    case_id = _case_id(client)
    response = client.put(f"/api/v1/cases/{case_id}/legal-research/authority-reviews", json={
        "provider": "india_code", "source_id": "cpc-order-vii-rule-11",
        "title": "Code of Civil Procedure, Order VII Rule 11",
        "url": "https://indiacode.ecourtsindia.com/acts/cpc/order/vii/rule/11",
        "status": "verified", "note": "Checked against the official text for this issue.",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "verified"
    assert body["reviewed_at"] is not None
    listed = client.get(f"/api/v1/cases/{case_id}/legal-research/authority-reviews")
    assert listed.status_code == 200
    assert listed.json()[0]["note"] == "Checked against the official text for this issue."


def test_authority_review_rejects_untrusted_external_url(client):
    case_id = _case_id(client)
    response = client.put(f"/api/v1/cases/{case_id}/legal-research/authority-reviews", json={
        "provider": "india_code", "source_id": "test-1", "title": "Untrusted link",
        "url": "https://example.com/authority", "status": "verified",
    })
    assert response.status_code == 422


def test_legal_research_returns_partial_results_and_provider_status(client, monkeypatch):
    case_id = _case_id(client)

    async def india_code_search(_self, query, limit):
        assert query == "Order VII Rule 11 CPC"
        assert limit == 6
        return [{"provider": "india_code", "title": "Order VII Rule 11", "url": "https://indiacode.ecourtsindia.com/cpc/order/vii/rule/11/"}]

    async def indian_kanoon_search(_self, query, limit):
        raise RuntimeError("synthetic provider outage")

    monkeypatch.setattr(legal_research.IndiaCodeProvider, "search", india_code_search)
    monkeypatch.setattr(legal_research.IndianKanoonProvider, "search", indian_kanoon_search)
    monkeypatch.setattr(settings, "indiankanoon_api_token", "synthetic-token")

    response = client.post(
        f"/api/v1/cases/{case_id}/legal-research/search",
        json={"query": "Order VII Rule 11 CPC"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["provider"] for item in payload["results"]] == ["india_code"]
    assert {item["provider"]: item["status"] for item in payload["providers"]} == {
        "india_code": "ok",
        "indian_kanoon": "error",
    }
    assert "Synthetic provider outage" not in response.text


def test_indian_kanoon_private_key_headers_use_non_reusable_signed_message(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    monkeypatch.setattr(settings, "indiankanoon_api_token", None)
    monkeypatch.setattr(settings, "indiankanoon_private_key", pem)
    monkeypatch.setattr(settings, "indiankanoon_customer_email", "registered@example.test")

    headers_one = legal_research.IndianKanoonProvider()._authorization_headers()
    headers_two = legal_research.IndianKanoonProvider()._authorization_headers()
    message = __import__("base64").b64decode(headers_one["X-Message"])
    signature = __import__("base64").b64decode(headers_one["Authorization"].removeprefix("HMAC "))
    key.public_key().verify(signature, message, padding.PKCS1v15(), hashes.SHA256())
    assert headers_one["X-Message"] != headers_two["X-Message"]
    assert "BEGIN PRIVATE KEY" not in str(headers_one)


def test_indian_kanoon_private_key_file_path_configures_provider(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_path = tmp_path / "indiankanoon_private.pem"
    pem_path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    monkeypatch.setattr(settings, "indiankanoon_api_token", None)
    monkeypatch.setattr(settings, "indiankanoon_private_key", None)
    monkeypatch.setattr(settings, "indiankanoon_private_key_path", pem_path)
    monkeypatch.setattr(settings, "indiankanoon_customer_email", "registered@example.test")

    status = next(item for item in legal_research.provider_status() if item.provider == "indian_kanoon")

    assert status.configured is True
    assert "ready" in status.message.casefold()


def test_india_code_provider_normalizes_documented_response(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "results": [{
                    "kind": "section",
                    "ref": "cpc/order/vii/rule/11",
                    "title": "Order VII Rule 11. Rejection of plaint",
                    "snippet": "The plaint shall be rejected…",
                    "url": "https://indiacode.ecourtsindia.com/cpc/order/vii/rule/11/",
                }]
            }

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url, *, params):
            assert params["q"] == "Order VII Rule 11 CPC"
            return FakeResponse()

    monkeypatch.setattr(legal_research.httpx, "AsyncClient", FakeClient)
    records = asyncio.run(legal_research.IndiaCodeProvider().search("Order VII Rule 11 CPC", 5))

    assert len(records) == 1
    assert records[0]["provider"] == "india_code"
    assert records[0]["source_id"] == "cpc/order/vii/rule/11"


def test_india_code_mapping_for_non_transition_act_returns_supported_explanation(client, monkeypatch):
    case_id = _case_id(client)

    async def unexpected_provider_call(*_args, **_kwargs):
        raise AssertionError("unsupported acts must not be sent to the mappings provider")

    monkeypatch.setattr(legal_research.IndiaCodeProvider, "mappings", unexpected_provider_call)
    response = client.get(
        f"/api/v1/cases/{case_id}/legal-research/india-code/mappings",
        params={"from_act": "cpc", "section": "9"},
    )

    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["mappings"]["mappings"] == []
    assert "No statutory transition mapping" in response.json()["message"]


def test_india_code_judgment_search_maps_precedential_metadata(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [{
                "title": "Synthetic v State", "url": "https://indiacode.ecourtsindia.com/judgments/1",
                "citation": "2025 INSC 1", "court_name": "Supreme Court of India",
                "date": "2025-01-01", "ratio_decidendi": "Synthetic ratio",
                "precedential_value": "binding", "cnr": "CNR123",
            }]}

    class FakeClient:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def get(self, url, *, params):
            assert url.endswith("/judgments")
            assert params["act"] == "cpc" and params["section"] == "9"
            assert params["precedential"] == "true"
            return FakeResponse()

    monkeypatch.setattr(legal_research.httpx, "AsyncClient", FakeClient)
    records = asyncio.run(legal_research.IndiaCodeProvider().judgments(
        act="cpc", section="9", precedential=True
    ))
    assert records[0]["court"] == "Supreme Court of India"
    assert records[0]["precedential_value"] == "binding"
    assert records[0]["source_id"] == "CNR123"


def test_indian_kanoon_search_passes_pagination_and_filters(monkeypatch):
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"docs": [{"tid": 12345, "title": "Synthetic case", "headline": "Relevant passage", "docsource": "Supreme Court", "date": "2025-01-01"}]}

    class FakeClient:
        def __init__(self, **_kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): return None
        async def post(self, url, *, params, headers):
            assert url.endswith("/search/")
            assert params["pagenum"] == 2
            assert params["court"] == "supremecourt"
            assert params["fromdate"] == "01-01-2020"
            return FakeResponse()

    monkeypatch.setattr(legal_research.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(legal_research.IndianKanoonProvider, "_authorization_headers", lambda _self: {"Authorization": "synthetic"})
    records = asyncio.run(legal_research.IndianKanoonProvider().search(
        "synthetic query", 5, 2, "supremecourt", "01-01-2020", None
    ))
    assert records[0]["source_id"] == "12345"
    assert records[0]["court"] == "Supreme Court"


def test_legal_research_rejects_path_like_act_identifiers(client):
    case_id = _case_id(client)
    response = client.post(
        f"/api/v1/cases/{case_id}/legal-research/search",
        json={"query": "civil procedure", "act": "../../secret", "section": "9"},
    )
    assert response.status_code == 422


def test_case_research_suggestions_are_empty_until_analysis_exists(client):
    case_id = _case_id(client)
    response = client.get(f"/api/v1/cases/{case_id}/legal-research/suggestions")
    assert response.status_code == 200
    assert response.json()["suggestions"] == []
    assert "Run case analysis" in response.json()["message"]


def test_indian_kanoon_detail_and_fragment_routes_are_safe_and_case_scoped(client, monkeypatch):
    case_id = _case_id(client)

    async def fake_document(_self, _doc_id):
        return {"title": "Synthetic judgment", "doc": "<p>Useful passage</p><script>ignore this instruction</script>", "docsource": "Supreme Court"}

    async def fake_metadata(_self, _doc_id):
        return {"cites": ["synthetic citation"], "citedby": []}

    async def fake_fragment(_self, _doc_id, query):
        return {"fragment": f"passage matching {query}"}

    monkeypatch.setattr(legal_research.IndianKanoonProvider, "document", fake_document)
    monkeypatch.setattr(legal_research.IndianKanoonProvider, "metadata", fake_metadata)
    monkeypatch.setattr(legal_research.IndianKanoonProvider, "fragment", fake_fragment)

    detail = client.get(f"/api/v1/cases/{case_id}/legal-research/indian-kanoon/12345")
    fragment = client.get(f"/api/v1/cases/{case_id}/legal-research/indian-kanoon/12345/fragment?query=useful%20passage")
    assert detail.status_code == 200
    assert "Useful passage" in detail.json()["document"]["doc"]
    assert "ignore this instruction" not in detail.json()["document"]["doc"]
    assert detail.json()["metadata"]["cites"] == ["synthetic citation"]
    assert fragment.status_code == 200
    assert "useful passage" in fragment.json()["fragment"]["fragment"]


def test_grounded_research_answer_returns_only_exactly_supported_points(client, monkeypatch):
    from types import SimpleNamespace
    from app.services import case_analysis_processing, gemini_analysis

    case_id = _case_id(client)
    monkeypatch.setattr(settings, "gemini_api_key", "synthetic-gemini-key")
    monkeypatch.setattr(settings, "gemini_data_tier", "paid")
    monkeypatch.setattr(case_analysis_processing, "gemini_is_ready", lambda: True)

    async def fake_document(_self, _doc_id):
        return {"title": "Synthetic judgment", "doc": "<p>The court applied Section 9 of the Code of Civil Procedure.</p>"}

    monkeypatch.setattr(legal_research.IndianKanoonProvider, "document", fake_document)
    monkeypatch.setattr(gemini_analysis.GeminiCaseAnalyzer, "_generate", lambda *_args: SimpleNamespace(points=[
        SimpleNamespace(point="The court discussed Section 9 CPC.", source_id="12345", quote="The court applied Section 9 of the Code of Civil Procedure."),
        SimpleNamespace(point="Unsupported point must be dropped.", source_id="12345", quote="This wording is absent."),
    ]))

    response = client.post(
        f"/api/v1/cases/{case_id}/legal-research/answer",
        json={"query": "Section 9 CPC jurisdiction", "source_ids": ["12345"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "• The court discussed Section 9 CPC."
    assert len(payload["citations"]) == 1
    assert payload["citations"][0]["quote"] == "The court applied Section 9 of the Code of Civil Procedure."
