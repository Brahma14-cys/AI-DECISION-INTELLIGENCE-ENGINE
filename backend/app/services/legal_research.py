"""Provider adapters for case-scoped Indian legal research.

Queries sent to external legal databases are advocate-supplied legal research
queries only; uploaded pleadings and other case documents are never forwarded.
"""

from __future__ import annotations

import asyncio
import base64
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
import uuid

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.core.config import settings


INDIACODE_PROVIDER = "india_code"
INDIANKANOON_PROVIDER = "indian_kanoon"
TIMEOUT_SECONDS = 12.0
_CACHE: OrderedDict[tuple, tuple[datetime, object]] = OrderedDict()
_CACHE_MAX = 256


def _cache_get(key: tuple):
    entry = _CACHE.get(key)
    if not entry:
        return None
    expires, value = entry
    if expires <= datetime.now(timezone.utc):
        _CACHE.pop(key, None)
        return None
    _CACHE.move_to_end(key)
    return value


def _cache_set(key: tuple, value):
    ttl = settings.legal_research_cache_ttl_seconds
    if ttl <= 0:
        return
    _CACHE[key] = (datetime.now(timezone.utc) + timedelta(seconds=ttl), value)
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    enabled: bool
    configured: bool
    message: str

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "provider": self.provider,
            "enabled": self.enabled,
            "configured": self.configured,
            "message": self.message,
        }


def _has_indiankanoon_private_key_source() -> bool:
    if settings.indiankanoon_private_key or settings.indiankanoon_private_key_path:
        return True
    default_path = Path(__file__).resolve().parents[2] / "secrets" / "indiankanoon_private.pem"
    return default_path.is_file()


def provider_status() -> list[ProviderStatus]:
    private_key_valid = False
    if _has_indiankanoon_private_key_source():
        try:
            private_key_valid = isinstance(_load_indiankanoon_private_key(), rsa.RSAPrivateKey)
        except (OSError, TypeError, ValueError):
            private_key_valid = False
    ik_configured = bool(settings.indiankanoon_api_token) or bool(
        private_key_valid and settings.indiankanoon_customer_email
    )
    if ik_configured:
        ik_message = "Ready for advocate-initiated judgment searches."
    elif _has_indiankanoon_private_key_source() and not private_key_valid:
        ik_message = "The Indian Kanoon private key could not be loaded as RSA PEM. Check INDIANKANOON_PRIVATE_KEY_PATH and its file permissions."
    elif private_key_valid:
        ik_message = "Set INDIANKANOON_CUSTOMER_EMAIL to the email registered with Indian Kanoon."
    else:
        ik_message = "Set an Indian Kanoon API token, or its private key and registered customer email."
    return [
        ProviderStatus(INDIACODE_PROVIDER, True, True, "No key required; statute search is available."),
        ProviderStatus(INDIANKANOON_PROVIDER, True, ik_configured, ik_message),
    ]


def _text(value: object, limit: int = 4_000) -> str | None:
    if not isinstance(value, str):
        return None
    clean = " ".join(value.split())
    return clean[:limit] if clean else None


def _load_indiankanoon_private_key() -> rsa.RSAPrivateKey:
    private_key_value = (settings.indiankanoon_private_key or "").replace("\\n", "\n").strip()
    if "BEGIN" in private_key_value:
        key_bytes = private_key_value.encode("utf-8")
    else:
        configured_path = settings.indiankanoon_private_key_path
        key_path = configured_path or (Path(private_key_value).expanduser() if private_key_value else None)
        if key_path is None:
            key_path = Path("secrets") / "indiankanoon_private.pem"
        if not key_path.is_absolute():
            backend_root = Path(__file__).resolve().parents[2]
            key_path = backend_root / key_path
        key_bytes = key_path.read_bytes()
    key = serialization.load_pem_private_key(key_bytes, password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("Indian Kanoon signing key must be RSA.")
    return key


def _result(
    *, provider: str, title: object, url: object, snippet: object = None,
    citation: object = None, court: object = None, date: object = None,
    result_type: object = None, source_id: object = None,
) -> dict[str, object] | None:
    clean_title, clean_url = _text(title, 500), _text(url, 2_000)
    if not clean_title or not clean_url or not clean_url.startswith("https://"):
        return None
    return {
        "provider": provider,
        "title": clean_title,
        "url": clean_url,
        "snippet": _text(snippet),
        "citation": _text(citation, 500),
        "court": _text(court, 250),
        "date": _text(date, 80),
        "result_type": _text(result_type, 100),
        "source_id": _text(source_id, 200),
    }


class IndiaCodeProvider:
    """Query-driven access to the unauthenticated India Code JSON API."""

    async def search(self, query: str, limit: int, page: int = 0) -> list[dict[str, object]]:
        cache_key = (INDIACODE_PROVIDER, "search", query, limit, page)
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
        url = f"{settings.indiacode_api_base_url.rstrip('/')}/search"
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
            response = await client.get(url, params={"q": query, "limit": min(limit, 20), "offset": page * limit})
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise ValueError("India Code returned an unexpected search response.")
        records: list[dict[str, object]] = []
        for item in payload["results"][:limit]:
            if not isinstance(item, dict):
                continue
            record = _result(
                provider=INDIACODE_PROVIDER,
                title=item.get("title"),
                url=item.get("url"),
                snippet=item.get("snippet") or item.get("text"),
                citation=item.get("citation"),
                result_type=item.get("kind"),
                source_id=item.get("ref"),
            )
            if record:
                records.append(record)
        _cache_set(cache_key, records)
        return records

    async def judgments(
        self, *, act: str, section: str, limit: int = 8, page: int = 0,
        court: str | None = None, precedential: bool | None = None,
    ) -> list[dict[str, object]]:
        cache_key = (INDIACODE_PROVIDER, "judgments", act, section, limit, page, court, precedential)
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
        params: dict[str, object] = {"act": act, "section": section, "limit": min(limit, 20), "offset": page * limit}
        if court:
            params["court"] = court
        if precedential is not None:
            params["precedential"] = str(precedential).lower()
        url = f"{settings.indiacode_api_base_url.rstrip('/')}/judgments"
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        items = (
            next((payload[key] for key in ("results", "judgments", "items", "data") if isinstance(payload.get(key), list)), [])
            if isinstance(payload, dict) else payload
        )
        if not isinstance(items, list):
            raise ValueError("India Code returned an unexpected judgments response.")
        records = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            record = _result(
                provider=INDIACODE_PROVIDER, title=item.get("title"), url=item.get("url"),
                snippet=item.get("ratio_decidendi") or item.get("snippet") or item.get("applied_to_this_section"),
                citation=item.get("citation"), court=item.get("court") or item.get("court_name"),
                date=item.get("date"), result_type="judgment", source_id=item.get("cnr") or item.get("ref"),
            )
            if record:
                record["precedential_value"] = _text(item.get("precedential_value"), 250)
                records.append(record)
        _cache_set(cache_key, records)
        return records

    async def section(self, act: str, section: str) -> dict[str, object]:
        cache_key = (INDIACODE_PROVIDER, "section", act, section)
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
        url = f"{settings.indiacode_api_base_url.rstrip('/')}/{act.strip('/')}/section/{section.strip('/')}/"
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("India Code returned an unexpected section response.")
        _cache_set(cache_key, payload)
        return payload

    async def mappings(self, from_act: str, section: str | None = None) -> dict[str, object]:
        cache_key = (INDIACODE_PROVIDER, "mappings", from_act, section)
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
        params: dict[str, str] = {"from": from_act}
        if section:
            params["section"] = section
        url = f"{settings.indiacode_api_base_url.rstrip('/')}/mappings"
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("India Code returned an unexpected statutory-mapping response.")
        _cache_set(cache_key, payload)
        return payload


class IndianKanoonProvider:
    """Search reported judgments using API-token or RSA/HMAC authentication."""

    def _authorization_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if settings.indiankanoon_api_token:
            headers["Authorization"] = f"Token {settings.indiankanoon_api_token}"
            return headers
        if not (settings.indiankanoon_customer_email and (
            settings.indiankanoon_private_key or settings.indiankanoon_private_key_path
            or (Path(__file__).resolve().parents[2] / "secrets" / "indiankanoon_private.pem").is_file()
        )):
            raise RuntimeError("Indian Kanoon is not configured with its registered customer identity.")

        # Never return or log the signing key; it remains server-side.
        private_key = _load_indiankanoon_private_key()
        message = f"legal-engine:{uuid.uuid4()}:{int(datetime.now(timezone.utc).timestamp())}".encode("utf-8")
        signature = private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
        headers.update({
            "X-Customer": settings.indiankanoon_customer_email,
            "X-Message": base64.b64encode(message).decode("ascii"),
            "Authorization": f"HMAC {base64.b64encode(signature).decode('ascii')}",
        })
        return headers

    async def search(self, query: str, limit: int, page: int = 0, court: str | None = None,
                     from_date: str | None = None, to_date: str | None = None) -> list[dict[str, object]]:
        cache_key = (INDIANKANOON_PROVIDER, "search", query, limit, page, court, from_date, to_date)
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
        headers = self._authorization_headers()
        url = f"{settings.indiankanoon_api_base_url.rstrip('/')}/search/"
        params: dict[str, object] = {"formInput": query, "pagenum": page, "maxcites": 10, "doctypes": "judgments"}
        if court:
            params["court"] = court
        if from_date:
            params["fromdate"] = from_date
        if to_date:
            params["todate"] = to_date
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
            response = await client.post(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()
        docs = payload.get("docs", []) if isinstance(payload, dict) else []
        if not isinstance(docs, list):
            raise ValueError("Indian Kanoon returned an unexpected search response.")
        records: list[dict[str, object]] = []
        for item in docs[:limit]:
            if not isinstance(item, dict):
                continue
            doc_id = item.get("tid") or item.get("docid")
            doc_url = f"https://indiankanoon.org/doc/{doc_id}/" if doc_id else item.get("url")
            record = _result(
                provider=INDIANKANOON_PROVIDER,
                title=item.get("title"),
                url=doc_url,
                snippet=item.get("headline") or item.get("fragment"),
                citation=item.get("citation"),
                court=item.get("docsource"),
                date=item.get("date"),
                result_type="judgment",
                source_id=str(doc_id) if doc_id is not None else None,
            )
            if record:
                records.append(record)
        _cache_set(cache_key, records)
        return records

    async def document(self, doc_id: str) -> dict[str, object]:
        return await self._get_json(
            f"doc/{doc_id}/", (INDIANKANOON_PROVIDER, "doc", doc_id),
            params={"maxcites": 10, "maxcitedby": 10},
        )

    async def metadata(self, doc_id: str) -> dict[str, object]:
        return await self._get_json(f"docmeta/{doc_id}/", (INDIANKANOON_PROVIDER, "meta", doc_id))

    async def fragment(self, doc_id: str, query: str) -> dict[str, object]:
        return await self._get_json(f"docfragment/{doc_id}/", (INDIANKANOON_PROVIDER, "fragment", doc_id, query),
                                    params={"formInput": query})

    async def _get_json(self, path: str, cache_key: tuple, params: dict | None = None) -> dict[str, object]:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
        url = f"{settings.indiankanoon_api_base_url.rstrip('/')}/{path}"
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=False) as client:
            response = await client.post(url, params=params, headers=self._authorization_headers())
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Indian Kanoon returned an unexpected document response.")
        _cache_set(cache_key, payload)
        return payload


async def run_legal_research(query: str, limit: int = 8, *, page: int = 0,
                             court: str | None = None, from_date: str | None = None,
                             to_date: str | None = None, act: str | None = None,
                             section: str | None = None, precedential: bool | None = None) -> dict[str, object]:
    """Search configured providers independently and preserve partial results."""
    statuses = {item.provider: item for item in provider_status()}
    providers = {
        INDIACODE_PROVIDER: IndiaCodeProvider(),
        INDIANKANOON_PROVIDER: IndianKanoonProvider(),
    }
    ready = [(name, provider) for name, provider in providers.items() if statuses[name].configured]
    search_calls = []
    for name, provider in ready:
        if name == INDIACODE_PROVIDER:
            call = provider.search(query, limit) if page == 0 else provider.search(query, limit, page)
        elif page == 0 and court is None and from_date is None and to_date is None:
            call = provider.search(query, limit)
        else:
            call = provider.search(query, limit, page, court, from_date, to_date)
        search_calls.append(call)
    outcomes = await asyncio.gather(
        *search_calls,
        return_exceptions=True,
    )
    outcome_by_provider = {name: outcome for (name, _), outcome in zip(ready, outcomes, strict=True)}
    result_groups: list[dict[str, object]] = []
    merged: list[dict[str, object]] = []
    for name in providers:
        status = statuses[name]
        if not status.configured:
            result_groups.append({"provider": name, "status": "not_configured", "message": status.message, "count": 0})
            continue
        outcome = outcome_by_provider[name]
        if not isinstance(outcome, BaseException):
            results = outcome
            merged.extend(results)
            result_groups.append({"provider": name, "status": "ok", "message": "Search completed.", "count": len(results)})
        else:
            error = outcome
            # Return a bounded generic status; do not expose URLs with query data,
            # credentials, raw vendor payloads, or exception internals.
            code = getattr(getattr(error, "response", None), "status_code", None)
            message = f"Provider request failed (HTTP {code})." if code else "Provider request failed; check network and provider settings."
            result_groups.append({"provider": name, "status": "error", "message": message, "count": 0})
    if act and section and statuses[INDIACODE_PROVIDER].configured:
        try:
            additional = await providers[INDIACODE_PROVIDER].judgments(
                act=act, section=section, limit=limit, page=page, court=court, precedential=precedential
            )
            merged.extend(additional)
            next(item for item in result_groups if item["provider"] == INDIACODE_PROVIDER)["count"] += len(additional)
        except Exception:
            pass  # Keep the broad search results if this optional endpoint is unavailable.
    return {
        "query": query,
        "results": merged[: limit * len(providers)],
        "providers": result_groups,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "notice": "Research results are candidate authorities. Verify the current text, amendments, jurisdiction, and precedential status before relying on them.",
    }
