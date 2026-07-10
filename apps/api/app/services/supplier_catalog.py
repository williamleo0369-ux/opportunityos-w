from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from uuid import uuid4

from app.services.database_store import load_supplier_catalog_payloads
from app.services.real_sources import SupplySignal


CSV_HEADERS = [
    "关键词",
    "供应商名称",
    "产品名称",
    "平台",
    "最低单价USD",
    "最高单价USD",
    "MOQ",
    "地区",
    "供应商链接",
    "备注",
]

FIELD_ALIASES = {
    "keyword": ("keyword", "关键词", "产品关键词"),
    "supplier_name": ("supplier_name", "供应商名称", "供应商", "公司名称"),
    "product_title": ("product_title", "产品名称", "产品标题", "产品"),
    "platform": ("platform", "平台", "来源"),
    "unit_price_min": ("unit_price_min", "最低单价usd", "最低单价", "最低价格"),
    "unit_price_max": ("unit_price_max", "最高单价usd", "最高单价", "最高价格"),
    "moq": ("moq", "起订量", "最小起订量"),
    "location": ("location", "地区", "国家/地区", "产地"),
    "supplier_url": ("supplier_url", "供应商链接", "链接", "网址"),
    "notes": ("notes", "备注", "说明"),
}


def supplier_catalog_template() -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_HEADERS)
    return "\ufeff" + output.getvalue()


def _row_value(row: dict[str, str], field: str) -> str:
    normalized = {str(key).strip().lower(): str(value or "").strip() for key, value in row.items() if key}
    for alias in FIELD_ALIASES[field]:
        if alias.lower() in normalized:
            return normalized[alias.lower()]
    return ""


def _number(value: str, *, integer: bool = False) -> float | int:
    if not value.strip():
        return 0 if integer else 0.0
    cleaned = re.sub(r"[^\d.\-]", "", value.replace(",", ""))
    try:
        parsed = max(0.0, float(cleaned))
    except ValueError as exc:
        raise ValueError(f"无法识别数值：{value}") from exc
    return int(parsed) if integer else round(parsed, 2)


def parse_supplier_catalog_csv(csv_text: str, *, max_rows: int = 500) -> list[dict[str, object]]:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff").strip()))
    if not reader.fieldnames:
        raise ValueError("CSV 缺少表头")
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    imported_at = datetime.now(timezone.utc).isoformat()
    for line_number, source in enumerate(reader, start=2):
        if not any(str(value or "").strip() for value in source.values()):
            continue
        supplier_name = _row_value(source, "supplier_name")
        product_title = _row_value(source, "product_title")
        if not supplier_name or not product_title:
            raise ValueError(f"第 {line_number} 行缺少供应商名称或产品名称")
        keyword = _row_value(source, "keyword")
        dedupe_key = (keyword.lower(), supplier_name.lower(), product_title.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        supplier_url = _row_value(source, "supplier_url")
        if supplier_url and not supplier_url.lower().startswith(("http://", "https://")):
            raise ValueError(f"第 {line_number} 行供应商链接必须以 http:// 或 https:// 开头")
        try:
            price_min = _number(_row_value(source, "unit_price_min"))
            price_max = _number(_row_value(source, "unit_price_max"))
            moq = _number(_row_value(source, "moq"), integer=True)
        except ValueError as exc:
            raise ValueError(f"第 {line_number} 行：{exc}") from exc
        if price_min and price_max and price_min > price_max:
            price_min, price_max = price_max, price_min
        rows.append(
            {
                "id": str(uuid4()),
                "keyword": keyword,
                "supplier_name": supplier_name,
                "product_title": product_title,
                "platform": _row_value(source, "platform") or "Supplier Catalog",
                "unit_price_min": price_min,
                "unit_price_max": price_max,
                "moq": moq,
                "location": _row_value(source, "location") or "Unknown",
                "supplier_url": supplier_url,
                "notes": _row_value(source, "notes"),
                "imported_at": imported_at,
            }
        )
        if len(rows) > max_rows:
            raise ValueError(f"单次最多导入 {max_rows} 条供应商记录")
    if not rows:
        raise ValueError("CSV 中没有可导入的供应商记录")
    return rows


def _matches_keyword(row: dict[str, object], keyword: str) -> bool:
    target = keyword.strip().lower()
    configured = str(row.get("keyword", "")).strip().lower()
    title = str(row.get("product_title", "")).strip().lower()
    if configured:
        return configured in target or target in configured
    if target in title or title in target:
        return True
    tokens = [token for token in re.split(r"[^\w\u4e00-\u9fff]+", target) if len(token) >= 3]
    return any(token in title for token in tokens)


def collect_supplier_catalog(user_id: str, keyword: str, limit: int = 8) -> list[SupplySignal]:
    signals: list[SupplySignal] = []
    for row in load_supplier_catalog_payloads(user_id):
        if not _matches_keyword(row, keyword):
            continue
        price_min = float(row.get("unit_price_min", 0) or 0)
        price_max = float(row.get("unit_price_max", 0) or 0)
        moq = int(row.get("moq", 0) or 0)
        score = 54 + (15 if price_min or price_max else 0) + (12 if moq else 0) + (8 if row.get("supplier_url") else 0)
        signals.append(
            SupplySignal(
                supplier_name=str(row.get("supplier_name", "")),
                platform=str(row.get("platform", "Supplier Catalog")),
                product_title=str(row.get("product_title", "")),
                unit_price_min=price_min,
                unit_price_max=price_max,
                moq=moq,
                location=str(row.get("location", "Unknown")),
                supplier_url=str(row.get("supplier_url", "")),
                product_url=str(row.get("supplier_url", "")),
                production_maturity_score=min(95, score),
                logistics_note=str(row.get("notes", "")) or "用户导入的真实供应商资料，采购前需复核报价有效期",
                raw_data={
                    "source": "supplier_catalog",
                    "catalog_id": row.get("id"),
                    "imported_at": row.get("imported_at"),
                },
            )
        )
        if len(signals) >= limit:
            break
    return signals
