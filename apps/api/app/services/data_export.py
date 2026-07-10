from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from app.schemas import Report
from app.services.exporters import safe_filename


def export_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def data_export_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def data_export_zip(payload: dict[str, Any], reports: dict[str, Report]) -> bytes:
    manifest = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "tasks": len(payload.get("tasks", {})),
            "opportunities": len(payload.get("opportunities", {})),
            "reports": len(payload.get("reports", {})),
            "saved": len(payload.get("saved", {})),
            "supplier_catalog": len(payload.get("supplier_catalog", [])),
            "source_health_checks": len(payload.get("source_health_history", [])),
        },
        "files": [
            "store.json",
            "source-health-history.json",
            "reports/*.md",
        ],
    }
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", data_export_json(manifest))
        archive.writestr("store.json", data_export_json(payload))
        archive.writestr("source-health-history.json", data_export_json({"items": payload.get("source_health_history", [])}))
        for report in sorted(reports.values(), key=lambda item: item.created_at, reverse=True):
            filename = safe_filename(f"{report.created_at.date()}-{report.id[:8]}-{report.report_title}", "md")
            archive.writestr(f"reports/{filename}", report.markdown_content)
    return buffer.getvalue()
