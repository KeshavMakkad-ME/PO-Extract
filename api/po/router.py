import logging
import os

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from openai import OpenAI

from api.po.requests import ALLOWED_EXTENSIONS, MAX_FILES, UploadedFiles
from api.common.responses import AckResponse, HealthResponse
from core.extractor import extract_text_from_csv, extract_text_from_pdf
from services.po.gemini_client import extract_po_fields
from services.po.verifier import build_verification_prompt
from core.verifier import verify_extraction
from core.mailer import send_error_email, send_invoice_email
from services.po.xlsx_builder import build_xlsx
from utils.po.gsheet import load_field_config

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_recipients(submitted_email: str) -> list[str]:
    """Merge the submitted email with any configured FINANCE_EMAILS, deduped."""
    finance = [e.strip() for e in os.environ.get("FINANCE_EMAILS", "").split(",") if e.strip()]
    seen = set()
    result = []
    for email in [submitted_email] + finance:
        if email and email not in seen:
            seen.add(email)
            result.append(email)
    return result


def _process_and_email(
    file_items: list[tuple[str, bytes]],
    config_df: pd.DataFrame,
    state_codes: dict,
    dispatch_from: dict,
    model: OpenAI,
    recipients: list[str],
    company: str = "blinkit",
    sku_mapping: dict | None = None,
) -> None:
    results: list     = []
    errors: list[str] = []

    for filename, file_bytes in file_items:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        try:
            po_text = (
                extract_text_from_pdf(file_bytes)
                if ext == "pdf"
                else extract_text_from_csv(file_bytes)
            )
            result = extract_po_fields(po_text, config_df, model, company)
            verification = verify_extraction(build_verification_prompt(po_text, result, config_df, sku_mapping=sku_mapping), model)
            result["_verification"] = verification
            flag_count = len(verification.get("flags", []))
            if flag_count:
                logger.warning(f"{filename} — {flag_count} verification flag(s): {verification.get('summary')}")
            results.append(result)
            logger.info(f"{filename} — {len(result.get('line_items', []))} line item(s)")
        except Exception as e:
            msg = f"{filename}: {e}"
            logger.error(f"Failed to process {filename}: {e}", exc_info=True)
            errors.append(msg)
            results.append({"_error": msg})

    successful = [r for r in results if "_error" not in r]

    if not successful:
        send_error_email(recipients, errors)
        return

    try:
        xlsx_bytes, _, sku_errors = build_xlsx(results, config_df, state_codes, dispatch_from, sku_mapping=sku_mapping)
        send_invoice_email(
            xlsx_bytes  = xlsx_bytes,
            recipients  = recipients,
            all_results = successful,
            errors      = (errors + sku_errors) or None,
        )
    except Exception as e:
        logger.error(f"Failed to build or email XLSX: {e}", exc_info=True)
        send_error_email(recipients, errors + [f"XLSX build failed: {e}"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        ready=hasattr(request.app.state, "model"),
    )


@router.get("/dispatch-options")
async def dispatch_options(request: Request) -> list[dict]:
    return request.app.state.dispatch_options


@router.post("/process", response_model=AckResponse, status_code=202)
async def process_files(
    request: Request,
    background_tasks: BackgroundTasks,
    files: UploadedFiles,
    dispatch_from_idx: int = Form(...),
    recipient_email: str   = Form(...),
    company: str           = Form("blinkit"),
) -> AckResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_FILES} files allowed per request")

    dispatch_options = request.app.state.dispatch_options
    if not dispatch_options:
        raise HTTPException(status_code=503, detail="Dispatch locations not loaded — try again shortly")
    if dispatch_from_idx < 0 or dispatch_from_idx >= len(dispatch_options):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid dispatch location (index {dispatch_from_idx})",
        )

    file_items: list[tuple[str, bytes]] = []
    skipped: list[str] = []

    for upload in files:
        filename = upload.filename or "unknown"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            skipped.append(filename)
            continue
        file_items.append((filename, await upload.read()))

    if not file_items:
        raise HTTPException(status_code=400, detail="No supported files (PDF or CSV) found in upload")

    dispatch_from = dispatch_options[dispatch_from_idx]
    recipients    = _build_recipients(recipient_email)
    config_df     = load_field_config(company)
    sku_mapping   = request.app.state.flipkart_sku_mapping if company == "flipkart" else None

    background_tasks.add_task(
        _process_and_email,
        file_items,
        config_df,
        request.app.state.state_codes,
        dispatch_from,
        request.app.state.model,
        recipients,
        company,
        sku_mapping,
    )

    n = len(file_items)
    skipped_note = f" ({len(skipped)} unsupported file(s) skipped)" if skipped else ""
    return AckResponse(
        queued=True,
        message=f"{n} file(s) queued for processing{skipped_note}. Results will be emailed to {', '.join(recipients)}.",
    )
