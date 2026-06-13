from __future__ import annotations

import gzip
import html
import json
import os
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.runtime_credentials import get_1688_cookie


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
SSL_CONTEXT = ssl._create_unverified_context()
CNY_TO_USD_ESTIMATE = 0.14


@dataclass
class TrendSignal:
    keyword: str
    source: str
    growth_rate: float
    trend_score: int
    monthly_search_volume: int
    related_keywords: list[str]
    country_distribution: dict[str, int]
    monthly_data: list[dict[str, int | str]]
    raw_data: dict[str, Any]


@dataclass
class PatentSignal:
    title: str
    number: str
    country: str
    applicant: str
    inventor: str
    filing_date: str
    publication_date: str
    grant_date: str | None
    estimated_expiry_date: str
    legal_status: str
    risk_level: str
    abstract: str
    original_url: str
    claims: list[str]
    raw_data: dict[str, Any]


@dataclass
class CompetitorSignal:
    title: str
    platform: str
    brand: str
    price: float
    currency: str
    rating: float
    review_count: int
    estimated_sales: int
    product_url: str
    image_url: str
    main_features: list[str]
    weaknesses: list[str]
    raw_data: dict[str, Any]


@dataclass
class ReviewSignal:
    title: str
    body: str
    source: str
    community: str
    url: str
    published_at: str
    raw_data: dict[str, Any]


@dataclass
class SupplySignal:
    supplier_name: str
    platform: str
    product_title: str
    unit_price_min: float
    unit_price_max: float
    moq: int
    location: str
    supplier_url: str
    product_url: str
    production_maturity_score: int
    logistics_note: str
    raw_data: dict[str, Any]


def _fetch(url: str, timeout: int = 12, headers: dict[str, str] | None = None) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:
        payload = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            return gzip.decompress(payload)
        return payload


def _fetch_json(url: str, timeout: int = 12, headers: dict[str, str] | None = None) -> dict[str, Any] | list[Any]:
    return json.loads(_fetch(url, timeout=timeout, headers=headers).decode("utf-8", errors="replace"))


def _strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _parse_number(value: str | None) -> int:
    if not value:
        return 0
    value = value.replace(",", "").strip()
    match = re.search(r"(\d+(?:\.\d+)?)\s*([KkMm]?)", value)
    if not match:
        return 0
    number = float(match.group(1))
    suffix = match.group(2).lower()
    if suffix == "k":
        number *= 1_000
    elif suffix == "m":
        number *= 1_000_000
    return int(number)


def _parse_price_range(value: str | None) -> tuple[float, float]:
    if not value:
        return 0.0, 0.0
    cleaned = html.unescape(value).replace(",", "")
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", cleaned)]
    if not numbers:
        return 0.0, 0.0
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return min(numbers[:2]), max(numbers[:2])


def _absolute_url(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("/"):
        return f"https://www.alibaba.com{value}"
    return value


def _absolute_1688_url(value: str | None) -> str:
    if not value:
        return ""
    value = html.unescape(value)
    if value.startswith("//"):
        return f"https:{value}"
    if value.startswith("/"):
        return f"https://www.1688.com{value}"
    return value


def _month_keys(count: int = 12) -> list[str]:
    today = datetime.now(timezone.utc).replace(day=1)
    months = []
    for offset in range(count - 1, -1, -1):
        month = today - timedelta(days=offset * 30)
        months.append(month.strftime("%Y-%m"))
    return months


def google_suggest(keyword: str) -> list[str]:
    query = urllib.parse.quote(keyword)
    url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={query}"
    try:
        payload = _fetch_json(url, timeout=8)
    except Exception:
        return []
    if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list):
        return [str(item) for item in payload[1] if isinstance(item, str)]
    return []


def amazon_suggest(keyword: str) -> list[str]:
    query = urllib.parse.quote(keyword)
    url = (
        "https://completion.amazon.com/api/2017/suggestions"
        f"?limit=10&prefix={query}&suggestion-type=KEYWORD&page-type=Gateway"
        "&lop=en_US&site-variant=desktop&client-info=amazon-search-ui"
    )
    try:
        payload = _fetch_json(url, timeout=8)
    except Exception:
        return []
    suggestions = payload.get("suggestions", []) if isinstance(payload, dict) else []
    rows: list[str] = []
    for item in suggestions:
        if isinstance(item, dict) and item.get("value"):
            rows.append(str(item["value"]))
    return rows


def wikipedia_signal(keyword: str) -> dict[str, Any]:
    query = urllib.parse.quote(keyword)
    search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&format=json&origin=*"
    try:
        search_payload = _fetch_json(search_url, timeout=8)
    except Exception as exc:
        return {"totalhits": 0, "page_title": None, "pageviews": [], "error": str(exc)}

    query_data = search_payload.get("query", {}) if isinstance(search_payload, dict) else {}
    search_info = query_data.get("searchinfo", {})
    search_rows = query_data.get("search", [])
    title = search_rows[0].get("title") if search_rows and isinstance(search_rows[0], dict) else None
    pageviews: list[int] = []
    if title:
        start = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y%m%d00")
        end = datetime.now(timezone.utc).strftime("%Y%m%d00")
        encoded_title = urllib.parse.quote(str(title).replace(" ", "_"), safe="")
        views_url = (
            "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            f"en.wikipedia/all-access/user/{encoded_title}/monthly/{start}/{end}"
        )
        try:
            views_payload = _fetch_json(views_url, timeout=8)
            if isinstance(views_payload, dict):
                pageviews = [int(item.get("views", 0)) for item in views_payload.get("items", [])[-12:]]
        except Exception:
            pageviews = []
    return {
        "totalhits": int(search_info.get("totalhits", 0) or 0),
        "page_title": title,
        "pageviews": pageviews,
        "suggestion": search_info.get("suggestion"),
    }


def collect_trend_signal(keyword: str, target_market: str) -> TrendSignal:
    google_terms = google_suggest(keyword)
    amazon_terms = amazon_suggest(keyword)
    wiki = wikipedia_signal(keyword)
    related = []
    for item in [keyword, *google_terms, *amazon_terms, wiki.get("suggestion")]:
        if item and item not in related:
            related.append(str(item))
    related = related[:12]

    pageviews = [int(item) for item in wiki.get("pageviews", []) if isinstance(item, int)]
    if pageviews:
        base = max(1, pageviews[0])
        growth_rate = round(((pageviews[-1] - base) / base) * 100, 1)
        peak = max(pageviews) or 1
        monthly_data = [
            {"month": month, "value": max(1, round((value / peak) * 100))}
            for month, value in zip(_month_keys(len(pageviews)), pageviews)
        ]
    else:
        total_hits = int(wiki.get("totalhits", 0) or 0)
        signal = min(100, 30 + len(related) * 4 + min(30, total_hits // 75))
        monthly_data = [{"month": month, "value": signal} for month in _month_keys()]
        growth_rate = 0.0

    suggestion_strength = min(100, len(google_terms) * 7 + len(amazon_terms) * 6)
    wiki_strength = min(100, int(wiki.get("totalhits", 0) or 0) // 20)
    trend_score = max(25, min(95, round(suggestion_strength * 0.65 + wiki_strength * 0.35)))
    monthly_search_volume = max(0, len(google_terms) * 6_000 + len(amazon_terms) * 4_500 + int(wiki.get("totalhits", 0) or 0) * 20)

    return TrendSignal(
        keyword=keyword,
        source="google_suggest+amazon_suggest+wikimedia",
        growth_rate=growth_rate,
        trend_score=trend_score,
        monthly_search_volume=monthly_search_volume,
        related_keywords=related or [keyword],
        country_distribution={target_market: 55, "United States": 25, "Germany": 8, "United Kingdom": 7, "Canada": 5},
        monthly_data=monthly_data,
        raw_data={"google_suggest": google_terms, "amazon_suggest": amazon_terms, "wikimedia": wiki},
    )


def collect_google_patents(keyword: str, limit: int = 12) -> list[PatentSignal]:
    query = urllib.parse.quote(f"q={keyword}")
    url = f"https://patents.google.com/xhr/query?url={query}&exp="
    try:
        payload = _fetch_json(url, timeout=15)
    except Exception:
        return []
    results = payload.get("results", {}) if isinstance(payload, dict) else {}
    clusters = results.get("cluster", [])
    rows: list[PatentSignal] = []
    for cluster in clusters:
        for result in cluster.get("result", []):
            patent = result.get("patent", {})
            number = str(patent.get("publication_number") or "")
            if not number:
                continue
            metadata = patent.get("family_metadata", {}).get("aggregated", {}).get("country_status", [])
            states = [
                item.get("best_patent_stage", {}).get("state")
                for item in metadata
                if isinstance(item, dict)
            ]
            active_count = sum(1 for state in states if state == "ACTIVE")
            legal_status = "active" if active_count else "expired" if states else "unknown"
            risk_level = "high" if active_count >= 3 else "medium" if active_count else "low"
            filing_date = str(patent.get("filing_date") or patent.get("priority_date") or "")
            expiry = ""
            if re.match(r"^\d{4}-\d{2}-\d{2}$", filing_date):
                expiry = f"{int(filing_date[:4]) + 20}{filing_date[4:]}"
            rows.append(
                PatentSignal(
                    title=_strip_tags(str(patent.get("title") or number)),
                    number=number,
                    country=number[:2] if len(number) >= 2 else "",
                    applicant=_strip_tags(str(patent.get("assignee") or "Unknown")),
                    inventor=_strip_tags(str(patent.get("inventor") or "Unknown")),
                    filing_date=filing_date,
                    publication_date=str(patent.get("publication_date") or ""),
                    grant_date=str(patent.get("grant_date") or "") or None,
                    estimated_expiry_date=expiry,
                    legal_status=legal_status,
                    risk_level=risk_level,
                    abstract=_strip_tags(str(patent.get("snippet") or "")),
                    original_url=f"https://patents.google.com/patent/{urllib.parse.quote(number)}",
                    claims=[],
                    raw_data={"source": "google_patents_xhr", "active_country_count": active_count},
                )
            )
            if len(rows) >= limit:
                return rows
    return rows


def collect_amazon_competitors(keyword: str, limit: int = 6) -> list[CompetitorSignal]:
    query = urllib.parse.quote_plus(keyword)
    url = f"https://www.amazon.com/s?k={query}"
    try:
        text = _fetch(url, timeout=15).decode("utf-8", errors="replace")
    except Exception:
        return []
    if "Robot Check" in text or "Enter the characters you see below" in text:
        return []

    rows: list[CompetitorSignal] = []
    seen_asins: set[str] = set()
    for heading in re.finditer(r"<h2[^>]*>.*?</h2>", text, re.S):
        block = text[max(0, heading.start() - 5000) : heading.end() + 9000]
        title_match = re.search(r"<h2[^>]*>.*?<span[^>]*>(.*?)</span>.*?</h2>", block, re.S)
        asin_match = re.search(r'data-asin="([A-Z0-9]{10})"', block) or re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", block)
        price_match = re.search(r'<span class="a-offscreen">\$(\d[\d,]*(?:\.\d{2})?)</span>', block)
        rating_match = re.search(r'<span class="a-icon-alt">([0-5](?:\.\d)?) out of 5 stars</span>', block)
        review_match = re.search(r'<span class="a-size-base s-underline-text">([\d,]+)</span>', block)
        image_match = re.search(r'<img[^>]+(?:src|data-src)="([^"]+)"', block)
        if not title_match or not price_match:
            continue
        asin = asin_match.group(1) if asin_match else f"SEARCH{len(rows):04d}"
        if asin in seen_asins:
            continue
        seen_asins.add(asin)
        title = _strip_tags(title_match.group(1))
        if not title or "sponsored" in title.lower():
            continue
        price = float(price_match.group(1).replace(",", ""))
        rating = float(rating_match.group(1)) if rating_match else 0.0
        reviews = _parse_number(review_match.group(1) if review_match else None)
        rows.append(
            CompetitorSignal(
                title=title,
                platform="amazon",
                brand=title.split()[0][:30] if title.split() else "Amazon Seller",
                price=price,
                currency="USD",
                rating=rating,
                review_count=reviews,
                estimated_sales=max(0, reviews * 2),
                product_url=f"https://www.amazon.com/dp/{asin}",
                image_url=html.unescape(image_match.group(1)) if image_match else "",
                main_features=["Amazon live listing", "price and rating observed from search result"],
                weaknesses=["Review text not yet collected", "Listing details require deeper product-page crawl"],
                raw_data={"source": "amazon_search_html", "asin": asin},
            )
        )
        if len(rows) >= limit:
            break
    return rows


def collect_amazon_product_reviews(asins: list[str], limit: int = 12, reviews_per_asin: int = 3) -> list[ReviewSignal]:
    rows: list[ReviewSignal] = []
    seen_review_ids: set[str] = set()
    for asin in asins:
        if not asin or asin.startswith("SEARCH"):
            continue
        product_url = f"https://www.amazon.com/dp/{urllib.parse.quote(asin)}"
        try:
            text = _fetch(product_url, timeout=20).decode("utf-8", errors="replace")
        except Exception:
            continue
        if "Robot Check" in text or "Amazon Sign-In" in text or 'data-hook="review"' not in text:
            continue

        matches = list(re.finditer(r'data-reviewid="([^"]+)"', text))
        extracted_for_asin = 0
        for index, match in enumerate(matches):
            review_id = match.group(1)
            if review_id in seen_review_ids:
                continue
            block_end = matches[index + 1].start() if index + 1 < len(matches) else min(len(text), match.start() + 18000)
            block = text[match.start() : block_end]
            title_match = re.search(r'data-hook="reviewTitle"[^>]*>(.*?)</(?:h5|span|a)>', block, re.S)
            body_match = re.search(r'data-hook="reviewRichContentContainer"[^>]*>(.*?)</div>', block, re.S)
            if not body_match:
                body_match = re.search(r'data-hook="reviewText"[^>]*>(.*?)</div>', block, re.S)
            date_match = re.search(r'data-hook="review-date"[^>]*>(.*?)</span>', block, re.S)
            rating_match = re.search(r'data-hook="review-star-rating"[^>]*>.*?<span[^>]*>(.*?)</span>', block, re.S)

            title = _strip_tags(title_match.group(1)) if title_match else "Amazon product review"
            body = _strip_tags(body_match.group(1)) if body_match else ""
            if len(body) < 40:
                continue
            seen_review_ids.add(review_id)
            rows.append(
                ReviewSignal(
                    title=title,
                    body=body[:2000],
                    source="amazon_product_page_reviews",
                    community=f"amazon:{asin}",
                    url=f"{product_url}#customer_review-{review_id}",
                    published_at=_strip_tags(date_match.group(1)) if date_match else "",
                    raw_data={
                        "source": "amazon_product_page_reviews",
                        "asin": asin,
                        "review_id": review_id,
                        "rating": _strip_tags(rating_match.group(1)) if rating_match else "",
                    },
                )
            )
            extracted_for_asin += 1
            if extracted_for_asin >= reviews_per_asin or len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    return rows


def collect_reddit_pain_posts(keyword: str, limit: int = 12) -> list[ReviewSignal]:
    query = urllib.parse.quote(keyword)
    url = f"https://www.reddit.com/search.rss?q={query}&sort=relevance&limit={limit}"
    try:
        payload = _fetch(url, timeout=15)
    except Exception:
        return []

    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []

    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    rows: list[ReviewSignal] = []
    for entry in root.findall("atom:entry", namespace):
        title = entry.findtext("atom:title", default="", namespaces=namespace)
        content = entry.findtext("atom:content", default="", namespaces=namespace)
        link = entry.find("atom:link", namespace)
        category = entry.find("atom:category", namespace)
        published = entry.findtext("atom:published", default=entry.findtext("atom:updated", default="", namespaces=namespace), namespaces=namespace)
        body = _strip_tags(html.unescape(content))
        clean_title = _strip_tags(html.unescape(title))
        community = category.attrib.get("label", category.attrib.get("term", "reddit")) if category is not None else "reddit"
        href = link.attrib.get("href", "") if link is not None else ""
        combined = f"{clean_title} {body}".lower()
        keyword_terms = [term for term in re.split(r"\s+", keyword.lower()) if len(term) > 2]
        if keyword_terms and not any(term in combined for term in keyword_terms):
            continue
        if len(body) < 40 and len(clean_title) < 20:
            continue
        rows.append(
            ReviewSignal(
                title=clean_title,
                body=body[:2000],
                source="reddit_search_rss",
                community=community,
                url=href,
                published_at=published,
                raw_data={"source": "reddit_search_rss"},
            )
        )
        if len(rows) >= limit:
            break
    return rows


def _ec21_keyword_path(keyword: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", keyword.lower()).strip("_")
    return normalized or "product"


def _ec21_extract_title(anchor_html: str, link_text: str) -> str:
    title_match = re.search(r'title="([^"]+)"', anchor_html, re.S)
    title = html.unescape(title_match.group(1)) if title_match else _strip_tags(link_text)
    if ":" in title:
        title = title.split(":", 1)[1]
    return _strip_tags(title)


def _ec21_maturity_score(
    price_min: float,
    price_max: float,
    moq: int,
    supplier_url: str,
    image_url: str,
    location: str,
) -> int:
    score = 45
    if price_min > 0 or price_max > 0:
        score += 18
    if moq > 0:
        score += 16
    if supplier_url:
        score += 8
    if image_url:
        score += 6
    if location:
        score += 5
    return min(95, score)


def _extract_js_object_assignment(text: str, marker: str) -> dict[str, Any] | None:
    marker_index = text.find(marker)
    if marker_index == -1:
        return None
    equals_index = text.find("=", marker_index)
    start = text.find("{", equals_index)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for position in range(start, len(text)):
        char = text[position]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : position + 1])
                    except json.JSONDecodeError:
                        return None
    return None


def _alibaba_price_range(value: str | None) -> tuple[float, float, str, bool]:
    if not value:
        return 0.0, 0.0, "", False
    normalized = html.unescape(value).replace("\u00a0", " ")
    price_min, price_max = _parse_price_range(normalized)
    if "CN¥" in normalized or "CNY" in normalized.upper():
        return round(price_min * CNY_TO_USD_ESTIMATE, 2), round(price_max * CNY_TO_USD_ESTIMATE, 2), "CNY", True
    if "$" in normalized or "US" in normalized.upper():
        return price_min, price_max, "USD", False
    return price_min, price_max, "", False


def _alibaba_maturity_score(row: dict[str, Any], price_min: float, price_max: float, moq: int) -> int:
    score = 48
    if price_min > 0 or price_max > 0:
        score += 16
    if moq > 0:
        score += 14
    if row.get("supplierHref") or row.get("supplierHomeHref"):
        score += 6
    if row.get("goldSupplierYears") or row.get("goldSupplierIcon"):
        score += 5
    if row.get("reviewCount") or row.get("reviewScore"):
        score += 4
    if row.get("tradeProduct"):
        score += 4
    return min(96, score)


def _alibaba_supply_signal(
    *,
    supplier_name: str,
    product_title: str,
    product_url: str,
    supplier_url: str,
    price_text: str,
    moq_text: str,
    location: str,
    image_url: str,
    source: str,
    search_url: str,
    extra: dict[str, Any] | None = None,
) -> SupplySignal | None:
    if not product_title or not product_url:
        return None
    price_min, price_max, currency, converted = _alibaba_price_range(price_text)
    moq = _parse_number(moq_text)
    row_for_score = {
        "supplierHref": supplier_url,
        "goldSupplierYears": (extra or {}).get("supplier_year"),
        "reviewCount": (extra or {}).get("review_count"),
        "reviewScore": (extra or {}).get("review_score"),
        "tradeProduct": (extra or {}).get("trade_product"),
    }
    maturity = _alibaba_maturity_score(row_for_score, price_min, price_max, moq)
    note = "Alibaba.com direct listing"
    if moq_text:
        note += f", {moq_text}"
    if currency:
        note += f", original price {price_text}"
    if converted:
        note += ", unit price converted from CNY estimate"
    return SupplySignal(
        supplier_name=supplier_name or "Alibaba supplier",
        platform="Alibaba.com",
        product_title=product_title,
        unit_price_min=price_min,
        unit_price_max=price_max,
        moq=moq,
        location=location,
        supplier_url=supplier_url,
        product_url=product_url,
        production_maturity_score=maturity,
        logistics_note=note,
        raw_data={
            "source": source,
            "search_url": search_url,
            "product_url": product_url,
            "image_url": image_url,
            "original_price": price_text,
            "original_currency": currency,
            "price_converted_from_cny": converted,
            **(extra or {}),
        },
    )


def _collect_alibaba_showroom_cards(text: str, search_url: str, limit: int) -> list[SupplySignal]:
    rows: list[SupplySignal] = []
    title_matches = list(re.finditer(r'<a[^>]+href="([^"]+)"[^>]+data-component="ProductTitle"[^>]*>(.*?)</a>', text, re.S))
    for index, match in enumerate(title_matches):
        block_start = max(0, match.start() - 4500)
        block_end = title_matches[index + 1].start() if index + 1 < len(title_matches) else min(len(text), match.end() + 4500)
        block = text[block_start:block_end]
        product_url = _absolute_url(match.group(1))
        product_title = _strip_tags(match.group(2))
        price_match = re.search(r'data-component="ProductPrice"[^>]*>(.*?)</div>', block, re.S)
        moq_match = re.search(r'data-component="ProductMoq"[^>]*>(.*?)</div>', block, re.S)
        supplier_match = re.search(r'<a[^>]+href="([^"]+)"[^>]+data-component="SupplierNameLink"[^>]*>(.*?)</a>', block, re.S)
        year_match = re.search(r'(\d+)\s+yrs', block)
        review_match = re.search(r'data-component="ProductReviewsCompact"[^>]*>.*?<span[^>]*>([\d.]+)</span>.*?<span[^>]*>\(([\d,]+)\)</span>', block, re.S)
        image_match = re.search(r'<img[^>]+(?:src|data-src)="([^"]+)"[^>]+(?:alt="[^"]*"[^>]*)?', block, re.S)
        supplier_url = _absolute_url(supplier_match.group(1)) if supplier_match else ""
        signal = _alibaba_supply_signal(
            supplier_name=_strip_tags(supplier_match.group(2)) if supplier_match else "Alibaba supplier",
            product_title=product_title,
            product_url=product_url,
            supplier_url=supplier_url,
            price_text=_strip_tags(price_match.group(1)) if price_match else "",
            moq_text=_strip_tags(moq_match.group(1)) if moq_match else "",
            location="China" if ">CN<" in block or "China flag" in block else "",
            image_url=_absolute_url(image_match.group(1)) if image_match else "",
            source="alibaba_showroom_html",
            search_url=search_url,
            extra={
                "supplier_year": year_match.group(1) if year_match else None,
                "review_score": review_match.group(1) if review_match else None,
                "review_count": review_match.group(2) if review_match else None,
            },
        )
        if signal:
            rows.append(signal)
        if len(rows) >= limit:
            break
    return rows


def collect_alibaba_supply_chain(keyword: str, limit: int = 8) -> list[SupplySignal]:
    query = urllib.parse.quote_plus(keyword)
    urls = [
        f"https://www.alibaba.com/trade/search?SearchText={query}",
        f"https://www.alibaba.com/showroom/{re.sub(r'[^a-zA-Z0-9]+', '-', keyword.lower()).strip('-')}.html",
    ]
    rows: list[SupplySignal] = []
    seen: set[str] = set()
    for url in urls:
        try:
            text = _fetch(url, timeout=20).decode("utf-8", errors="replace")
        except Exception:
            continue
        lowered = text.lower()
        if "captcha" in lowered or "punish" in lowered or "verify you are human" in lowered:
            continue
        payload = _extract_js_object_assignment(text, "window.__page__data_sse10._offer_list")
        offers = []
        if payload:
            offer_data = payload.get("offerResultData", {})
            offers = offer_data.get("offers", []) if isinstance(offer_data, dict) else []
        for item in offers:
            if not isinstance(item, dict):
                continue
            row = item.get("offer") if isinstance(item.get("offer"), dict) else item
            if not isinstance(row, dict):
                continue
            product_url = _absolute_url(str(row.get("productUrl") or ""))
            supplier_url = _absolute_url(str(row.get("supplierHref") or row.get("supplierHomeHref") or ""))
            product_title = _strip_tags(str(row.get("puretitle") or row.get("title") or row.get("image", {}).get("alt", "")))
            supplier = row.get("supplier", {}) if isinstance(row.get("supplier"), dict) else {}
            supplier_name = _strip_tags(str(row.get("companyName") or supplier.get("supplierName") or "Alibaba supplier"))
            if not product_url or product_url in seen or not product_title:
                continue
            seen.add(product_url)

            trade_price = row.get("tradePrice", {}) if isinstance(row.get("tradePrice"), dict) else {}
            price_text = str(trade_price.get("price") or row.get("price") or row.get("lowerPrice") or "")
            moq_text = str(trade_price.get("minOrder") or row.get("moqV2") or row.get("moq") or "")
            country = (
                supplier.get("supplierCountry", {}).get("name")
                if isinstance(supplier.get("supplierCountry"), dict)
                else None
            ) or row.get("countryCode") or ""
            location = "China" if country == "CN" else str(country)
            image = row.get("image", {}) if isinstance(row.get("image"), dict) else {}
            image_url = _absolute_url(
                str(
                    row.get("mainImage")
                    or image.get("mainImage", "")
                    or image.get("productImage", "")
                )
            )
            signal = _alibaba_supply_signal(
                supplier_name=supplier_name,
                product_title=product_title,
                product_url=product_url,
                supplier_url=supplier_url,
                price_text=price_text,
                moq_text=moq_text,
                location=location,
                image_url=image_url,
                source="alibaba_search_html",
                search_url=url,
                extra={
                    "review_count": row.get("reviewCount") or (row.get("reviews", {}).get("reviewCount") if isinstance(row.get("reviews"), dict) else None),
                    "review_score": row.get("reviewScore") or (row.get("reviews", {}).get("reviewScore") if isinstance(row.get("reviews"), dict) else None),
                    "supplier_year": row.get("goldSupplierYears") or supplier.get("supplierYear"),
                    "trade_product": row.get("tradeProduct"),
                },
            )
            if not signal:
                continue
            rows.append(signal)
            if len(rows) >= limit:
                return rows
        if not rows:
            for signal in _collect_alibaba_showroom_cards(text, url, limit):
                if signal.product_url in seen:
                    continue
                seen.add(signal.product_url)
                rows.append(signal)
                if len(rows) >= limit:
                    return rows
    return rows


def _1688_cookie(cookie: str | None = None) -> str:
    return cookie.strip() if cookie is not None else get_1688_cookie()


def has_1688_session(cookie: str | None = None) -> bool:
    return bool(_1688_cookie(cookie))


def _1688_keyword(keyword: str) -> str:
    mapping = {
        "pet water fountain": "宠物饮水机",
        "smart pet water fountain": "智能宠物饮水机",
        "portable pet water fountain": "便携宠物饮水机",
        "quiet pet water fountain": "静音宠物饮水机",
        "camping lantern": "露营灯",
        "kitchen slicer": "切菜器",
        "foldable storage box": "折叠收纳箱",
        "portable fan": "便携风扇",
        "baby bottle warmer": "温奶器",
        "desk organizer": "桌面收纳",
        "cleaning brush": "清洁刷",
        "dog leash": "狗牵引绳",
        "cat litter box": "猫砂盆",
    }
    return mapping.get(keyword.lower().strip(), keyword)


def _1688_headers(cookie: str | None = None) -> dict[str, str]:
    return {
        "Cookie": _1688_cookie(cookie),
        "Referer": "https://www.1688.com/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
    }


def _1688_blocked(text: str) -> bool:
    lowered = text.lower()
    return "punish" in lowered or "captcha" in lowered or "_____tmd_____" in lowered or "x5secdata" in lowered


def _collect_1688_cards(text: str, search_url: str, limit: int) -> list[SupplySignal]:
    rows: list[SupplySignal] = []
    seen: set[str] = set()
    for match in re.finditer(r'(?:"(?:detailUrl|offerUrl|url)"\s*:\s*"|href=")([^"]*detail\.1688\.com/offer/(\d+)\.html[^"]*)', text, re.S):
        product_url = _absolute_1688_url(match.group(1).replace("\\/", "/"))
        if product_url in seen:
            continue
        seen.add(product_url)
        block = text[max(0, match.start() - 3500) : min(len(text), match.end() + 5500)]
        title_patterns = [
            r'"(?:subject|title|offerTitle)"\s*:\s*"([^"]+)"',
            r'title="([^"]{8,180})"',
            r'alt="([^"]{8,180})"',
        ]
        product_title = ""
        for pattern in title_patterns:
            title_match = re.search(pattern, block, re.S)
            if title_match:
                product_title = _strip_tags(title_match.group(1).replace("\\/", "/"))
                break
        if not product_title or "1688" in product_title.lower():
            continue

        supplier_match = (
            re.search(r'"(?:companyName|sellerNick|memberName|shopName)"\s*:\s*"([^"]+)"', block, re.S)
            or re.search(r'title="([^"]{4,120}(?:公司|厂|商行|店))"', block, re.S)
        )
        supplier_name = _strip_tags(supplier_match.group(1)) if supplier_match else "1688 supplier"
        supplier_url_match = re.search(r'(?:"(?:sellerUrl|shopUrl)"\s*:\s*"|href=")([^"]*(?:shop|page|company)[^"]*1688\.com[^"]*)', block, re.S)
        supplier_url = _absolute_1688_url(supplier_url_match.group(1).replace("\\/", "/")) if supplier_url_match else ""
        price_match = (
            re.search(r'"(?:price|priceRange|discountPrice)"\s*:\s*"([^"]+)"', block, re.S)
            or re.search(r'¥\s*([\d.]+(?:\s*[-~]\s*[\d.]+)?)', block)
        )
        price_text = price_match.group(1) if price_match else ""
        price_min, price_max = _parse_price_range(price_text)
        price_min = round(price_min * CNY_TO_USD_ESTIMATE, 2) if price_min else 0.0
        price_max = round(price_max * CNY_TO_USD_ESTIMATE, 2) if price_max else 0.0
        moq_match = (
            re.search(r'"(?:minOrderQuantity|beginAmount|minOrder)"\s*:\s*"?(\d+)', block, re.S)
            or re.search(r'(\d+)\s*(?:件|个|只|套|pcs|pieces)', block, re.I)
        )
        moq = _parse_number(moq_match.group(1) if moq_match else None)
        image_match = re.search(r'(?:"(?:imageUrl|picUrl|imgUrl)"\s*:\s*"|src=")([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)', block, re.I)
        image_url = _absolute_1688_url(image_match.group(1).replace("\\/", "/")) if image_match else ""
        score = 48
        if price_min or price_max:
            score += 16
        if moq:
            score += 14
        if supplier_url:
            score += 6
        if image_url:
            score += 5
        rows.append(
            SupplySignal(
                supplier_name=supplier_name,
                platform="1688",
                product_title=product_title,
                unit_price_min=price_min,
                unit_price_max=price_max,
                moq=moq,
                location="China",
                supplier_url=supplier_url,
                product_url=product_url,
                production_maturity_score=min(94, score),
                logistics_note="1688 session-backed listing, original price converted from CNY estimate",
                raw_data={
                    "source": "1688_search_html",
                    "search_url": search_url,
                    "product_url": product_url,
                    "image_url": image_url,
                    "original_price": price_text,
                    "original_currency": "CNY",
                    "price_converted_from_cny": True,
                },
            )
        )
        if len(rows) >= limit:
            break
    return rows


def collect_1688_supply_chain(
    keyword: str,
    limit: int = 6,
    *,
    cookie: str | None = None,
) -> list[SupplySignal]:
    if not has_1688_session(cookie):
        return []
    query = urllib.parse.quote(_1688_keyword(keyword))
    url = f"https://s.1688.com/selloffer/offer_search.htm?keywords={query}"
    try:
        text = _fetch(url, timeout=18, headers=_1688_headers(cookie)).decode("utf-8", errors="replace")
    except Exception:
        return []
    if _1688_blocked(text):
        return []
    return _collect_1688_cards(text, url, limit)


def probe_1688_supply_status(
    keyword: str,
    *,
    cookie: str | None = None,
) -> dict[str, str | bool]:
    url = f"https://s.1688.com/selloffer/offer_search.htm?keywords={urllib.parse.quote(_1688_keyword(keyword))}"
    if not has_1688_session(cookie):
        return {
            "available": False,
            "status": "missing_session",
            "reason": "连接账户级 1688 会话后可启用真实供应链采集",
            "url": url,
        }
    try:
        text = _fetch(url, timeout=12, headers=_1688_headers(cookie)).decode("utf-8", errors="replace")
    except Exception as exc:
        return {"available": False, "status": "error", "reason": str(exc), "url": url}
    if _1688_blocked(text):
        return {"available": False, "status": "guarded", "reason": "1688 returned anti-bot verification page; refresh the configured session cookie", "url": url}
    rows = _collect_1688_cards(text, url, 1)
    return {
        "available": bool(rows),
        "status": "ok" if rows else "reachable_empty",
        "reason": "session-backed collection available" if rows else "reachable but no structured offer rows parsed",
        "url": url,
    }


def source_health_status() -> dict[str, Any]:
    status_1688 = probe_1688_supply_status("pet water fountain")
    return {"1688": status_1688}


def collect_ec21_supply_chain(keyword: str, limit: int = 8) -> list[SupplySignal]:
    path = _ec21_keyword_path(keyword)
    url = f"https://www.ec21.com/ec-market/{path}.html"
    try:
        text = _fetch(url, timeout=18).decode("utf-8", errors="replace")
    except Exception:
        return []
    blocked_markers = ["Pardon Our Interruption", "captcha", "Access Denied", "verify you are human"]
    if any(marker.lower() in text.lower() for marker in blocked_markers):
        return []

    rows: list[SupplySignal] = []
    seen: set[str] = set()
    for fragment in text.split('<li class="galleryLs')[1:]:
        block = '<li class="galleryLs' + fragment
        h2_match = re.search(r'<h2[^>]*class="pdtName"[^>]*>(.*?)</h2>', block, re.S)
        if not h2_match:
            continue
        anchor_match = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', h2_match.group(1), re.S)
        if not anchor_match:
            continue
        product_url = html.unescape(anchor_match.group(1))
        if product_url in seen:
            continue
        seen.add(product_url)
        product_title = _ec21_extract_title(anchor_match.group(0), anchor_match.group(2))
        if not product_title:
            continue

        image_match = re.search(r'<img[^>]+(?:src|data-src)="([^"]+)"', block, re.S)
        image_url = html.unescape(image_match.group(1)) if image_match else ""

        price_match = re.search(r'itemprop="price"[^>]*>(.*?)</span>', block, re.S)
        price_min, price_max = _parse_price_range(_strip_tags(price_match.group(1)) if price_match else None)

        moq_match = re.search(r'<span[^>]*class="pr5"[^>]*>([\d,]+)</span>\s*<span[^>]*class="pr5"[^>]*>([^<]+)</span>\s*\(Min\. Order\)', block, re.S)
        moq = _parse_number(moq_match.group(1) if moq_match else None)
        moq_unit = _strip_tags(moq_match.group(2)) if moq_match else ""

        company_match = re.search(r'<li[^>]*class="pdtCompany"[^>]*>(.*?)</li>', block, re.S)
        company_block = company_match.group(1) if company_match else ""
        supplier_content = re.search(r'itemprop="name"[^>]*content="([^"]+)"', company_block, re.S)
        supplier_link = re.search(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', company_block, re.S)
        supplier_name = (
            html.unescape(supplier_content.group(1))
            if supplier_content
            else _strip_tags(supplier_link.group(2)) if supplier_link else "EC21 supplier"
        )
        supplier_url = html.unescape(supplier_link.group(1)) if supplier_link else ""
        location_match = re.search(r'(?:title|alt)="([^"]+)"', company_block, re.S)
        location = _strip_tags(location_match.group(1)) if location_match else ""

        maturity = _ec21_maturity_score(price_min, price_max, moq, supplier_url, image_url, location)
        logistics_note = "B2B listing exposes supplier contact page"
        if moq:
            logistics_note += f", MOQ {moq} {moq_unit or 'units'}"
        if location:
            logistics_note += f", origin {location}"

        rows.append(
            SupplySignal(
                supplier_name=_strip_tags(supplier_name),
                platform="EC21",
                product_title=product_title,
                unit_price_min=price_min,
                unit_price_max=price_max,
                moq=moq,
                location=location,
                supplier_url=supplier_url,
                product_url=product_url,
                production_maturity_score=maturity,
                logistics_note=logistics_note,
                raw_data={
                    "source": "ec21_market_html",
                    "search_url": url,
                    "product_url": product_url,
                    "image_url": image_url,
                    "moq_unit": moq_unit,
                },
            )
        )
        if len(rows) >= limit:
            break
    return rows
