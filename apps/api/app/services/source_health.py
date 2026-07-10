from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Callable

from app.services.ai_agent import llm_status
from app.services.real_sources import (
    amazon_suggest,
    collect_alibaba_supply_chain,
    collect_amazon_competitors,
    collect_amazon_product_reviews,
    collect_ec21_supply_chain,
    collect_google_patents,
    collect_reddit_pain_posts,
    google_suggest,
    wikipedia_signal,
)


TTL_SECONDS = 600
PROBE_KEYWORD = "pet water fountain"
_CACHE: dict[str, Any] | None = None
_CACHE_AT = 0.0


def get_source_health(refresh: bool = False) -> dict[str, Any]:
    global _CACHE, _CACHE_AT
    now_ts = time.time()
    if _CACHE and not refresh and now_ts - _CACHE_AT < TTL_SECONDS:
        return {**_CACHE, "cached": True, "cache_age_seconds": round(now_ts - _CACHE_AT)}
    if not refresh and _CACHE is None:
        return _shallow_health()

    started = time.time()
    checks: list[tuple[str, str, str, Callable[[], dict[str, Any]]]] = [
        ("google_suggest", "Google Suggest", "trend", _check_google_suggest),
        ("amazon_suggest", "Amazon Suggest", "trend", _check_amazon_suggest),
        ("wikimedia", "Wikimedia Search/Pageviews", "trend", _check_wikimedia),
        ("google_patents", "Google Patents", "patent", _check_google_patents),
        ("amazon_search", "Amazon Search HTML", "competitor", _check_amazon_search),
        ("amazon_reviews", "Amazon Product Page Reviews", "review", _check_amazon_reviews),
        ("reddit_rss", "Reddit Search RSS", "review", _check_reddit),
        ("alibaba", "Alibaba.com Search HTML", "supply", _check_alibaba),
        ("ec21", "EC21 B2B Market", "supply", _check_ec21),
        ("llm_agent", "LLM Agent", "agent", _check_llm),
    ]
    sources = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_map = {
            executor.submit(_run_check, key, label, category, check): key
            for key, label, category, check in checks
        }
        for future in as_completed(future_map):
            sources.append(future.result())
    sources.sort(key=lambda item: [key for key, *_ in checks].index(item["key"]))
    result = _build_result(sources, started, cached=False)
    _CACHE = result
    _CACHE_AT = time.time()
    return result


def invalidate_source_health_cache() -> None:
    global _CACHE, _CACHE_AT
    _CACHE = None
    _CACHE_AT = 0.0


def health_by_key(refresh: bool = False) -> dict[str, dict[str, Any]]:
    health = get_source_health(refresh=refresh)
    return {source["key"]: source for source in health["sources"]}


def _shallow_health() -> dict[str, Any]:
    ai = llm_status()
    sources = [
        _source("google_suggest", "Google Suggest", "trend", "not_checked", False, "Use refresh=true to probe this source."),
        _source("amazon_suggest", "Amazon Suggest", "trend", "not_checked", False, "Use refresh=true to probe this source."),
        _source("wikimedia", "Wikimedia Search/Pageviews", "trend", "not_checked", False, "Use refresh=true to probe this source."),
        _source("google_patents", "Google Patents", "patent", "not_checked", False, "Use refresh=true to probe this source."),
        _source("amazon_search", "Amazon Search HTML", "competitor", "not_checked", False, "Use refresh=true to probe this source."),
        _source("amazon_reviews", "Amazon Product Page Reviews", "review", "not_checked", False, "Use refresh=true to probe this source."),
        _source("reddit_rss", "Reddit Search RSS", "review", "not_checked", False, "Use refresh=true to probe this source."),
        _source("alibaba", "Alibaba.com Search HTML", "supply", "not_checked", False, "Use refresh=true to probe this source."),
        _source("ec21", "EC21 B2B Market", "supply", "not_checked", False, "Use refresh=true to probe this source."),
        _source("llm_agent", "LLM Agent", "agent", str(ai["status"]), bool(ai["available"]), str(ai["reason"]), provider=ai.get("provider"), model=ai.get("model")),
    ]
    return _build_result(sources, time.time(), cached=False)


def _run_check(key: str, label: str, category: str, check: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    started = time.time()
    try:
        payload = check()
        status = str(payload.pop("status"))
        available = bool(payload.pop("available"))
        reason = str(payload.pop("reason"))
        return _source(key, label, category, status, available, reason, round((time.time() - started) * 1000), **payload)
    except Exception as exc:
        return _source(key, label, category, "error", False, str(exc)[:300], round((time.time() - started) * 1000))


def _source(
    key: str,
    label: str,
    category: str,
    status: str,
    available: bool,
    reason: str,
    latency_ms: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "category": category,
        "status": status,
        "available": available,
        "reason": reason,
        "latency_ms": latency_ms,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }


def _build_result(sources: list[dict[str, Any]], started: float, cached: bool) -> dict[str, Any]:
    summary = {
        "ok": sum(1 for source in sources if source["status"] in {"ok", "configured"}),
        "guarded": sum(1 for source in sources if source["status"] in {"guarded", "missing_session", "missing_credentials"}),
        "error": sum(1 for source in sources if source["status"] == "error"),
        "empty": sum(1 for source in sources if source["status"] in {"empty", "reachable_empty"}),
        "not_checked": sum(1 for source in sources if source["status"] == "not_checked"),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": TTL_SECONDS,
        "cached": cached,
        "duration_ms": round((time.time() - started) * 1000),
        "summary": summary,
        "sources": sources,
    }


def _check_google_suggest() -> dict[str, Any]:
    rows = google_suggest(PROBE_KEYWORD)
    return {"available": bool(rows), "status": "ok" if rows else "empty", "reason": f"{len(rows)} suggestions", "rows": len(rows)}


def _check_amazon_suggest() -> dict[str, Any]:
    rows = amazon_suggest(PROBE_KEYWORD)
    return {"available": bool(rows), "status": "ok" if rows else "empty", "reason": f"{len(rows)} suggestions", "rows": len(rows)}


def _check_wikimedia() -> dict[str, Any]:
    row = wikipedia_signal(PROBE_KEYWORD)
    hits = int(row.get("totalhits", 0) or 0)
    return {"available": hits > 0, "status": "ok" if hits > 0 else "empty", "reason": f"{hits} search hits", "rows": hits}


def _check_google_patents() -> dict[str, Any]:
    rows = collect_google_patents(PROBE_KEYWORD, limit=1)
    return {"available": bool(rows), "status": "ok" if rows else "empty", "reason": f"{len(rows)} patent rows", "rows": len(rows)}


def _check_amazon_search() -> dict[str, Any]:
    rows = collect_amazon_competitors(PROBE_KEYWORD, limit=1)
    return {"available": bool(rows), "status": "ok" if rows else "guarded", "reason": f"{len(rows)} listing rows", "rows": len(rows)}


def _check_amazon_reviews() -> dict[str, Any]:
    competitors = collect_amazon_competitors(PROBE_KEYWORD, limit=1)
    asins = [str(item.raw_data.get("asin", "")) for item in competitors]
    rows = collect_amazon_product_reviews(asins, limit=1, reviews_per_asin=1)
    return {"available": bool(rows), "status": "ok" if rows else "guarded", "reason": f"{len(rows)} review rows", "rows": len(rows)}


def _check_reddit() -> dict[str, Any]:
    rows = collect_reddit_pain_posts(PROBE_KEYWORD, limit=1)
    return {"available": bool(rows), "status": "ok" if rows else "empty", "reason": f"{len(rows)} discussion rows", "rows": len(rows)}


def _check_alibaba() -> dict[str, Any]:
    rows = collect_alibaba_supply_chain(PROBE_KEYWORD, limit=1)
    return {"available": bool(rows), "status": "ok" if rows else "guarded", "reason": f"{len(rows)} supplier rows", "rows": len(rows)}


def _check_ec21() -> dict[str, Any]:
    rows = collect_ec21_supply_chain(PROBE_KEYWORD, limit=1)
    return {"available": bool(rows), "status": "ok" if rows else "guarded", "reason": f"{len(rows)} supplier rows", "rows": len(rows)}


def _check_llm() -> dict[str, Any]:
    status = llm_status()
    return {
        "available": bool(status["available"]),
        "status": str(status["status"]),
        "reason": str(status["reason"]),
        "provider": status.get("provider"),
        "model": status.get("model"),
        "orchestration": status.get("orchestration"),
    }
