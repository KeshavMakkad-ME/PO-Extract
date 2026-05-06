import logging
import os

import requests
from fastapi import APIRouter, HTTPException, Request

from utils.rm_pm.gsheet import load_rm_pm_options
from utils.po.gsheet import load_dispatch_options, load_state_codes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin")

GSHEET_ID    = os.environ.get("TEMPLATE_GSHEET_ID", "1GbomN6aiYPMTFVJ1z50SzSNSL3wO_lLUd8AO4nhU570")
TEMPLATE_PATH = os.environ.get("TEMPLATE_PATH", "templates/Finance_XLSX_Templates_new_new.xlsx")
EXPORT_URL   = f"https://docs.google.com/spreadsheets/d/{GSHEET_ID}/export?format=xlsx"


@router.post("/refresh-template")
async def refresh_template(request: Request) -> dict:
    """Download the latest template from Google Sheets and reload all cached app state."""
    logger.info(f"Downloading template from Google Sheets (id={GSHEET_ID})...")

    try:
        resp = requests.get(EXPORT_URL, timeout=60)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download template: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to download template from Google Sheets: {e}")

    content_type = resp.headers.get("content-type", "")
    if "spreadsheet" not in content_type and "excel" not in content_type and "octet-stream" not in content_type:
        raise HTTPException(
            status_code=502,
            detail=f"Unexpected content-type from Google Sheets: {content_type}. Is the sheet publicly accessible?",
        )

    with open(TEMPLATE_PATH, "wb") as f:
        f.write(resp.content)

    size_kb = len(resp.content) // 1024
    logger.info(f"Template saved to {TEMPLATE_PATH} ({size_kb} KB) — reloading app state...")

    try:
        request.app.state.state_codes      = load_state_codes()
        request.app.state.dispatch_options = load_dispatch_options()
        request.app.state.rm_pm_options    = load_rm_pm_options()
    except Exception as e:
        logger.error(f"Template saved but state reload failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Template saved ({size_kb} KB) but failed to reload app state: {e}",
        )

    logger.info("Template refresh complete")
    return {
        "success":         True,
        "size_kb":         size_kb,
        "template_path":   TEMPLATE_PATH,
        "dispatch_options": len(request.app.state.dispatch_options),
        "state_codes":     len(request.app.state.state_codes),
        "voucher_types":   len(request.app.state.rm_pm_options.get("voucher_type_names", [])),
        "purchase_ledgers": len(request.app.state.rm_pm_options.get("purchase_ledgers", [])),
    }
