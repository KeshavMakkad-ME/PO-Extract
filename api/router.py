import logging
import os

import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from openai import OpenAI

from api.requests import ALLOWED_EXTENSIONS, MAX_FILES, UploadedFiles
from api.responses import AckResponse, HealthResponse
from core.extractor import extract_text_from_csv, extract_text_from_pdf
from core.gemini_client import extract_po_fields
from core.mailer import send_error_email, send_invoice_email
from core.xlsx_builder import build_xlsx

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
            result = extract_po_fields(po_text, config_df, model)
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
        xlsx_bytes, _ = build_xlsx(results, config_df, state_codes, dispatch_from)
        send_invoice_email(
            xlsx_bytes  = xlsx_bytes,
            recipients  = recipients,
            all_results = successful,
            errors      = errors or None,
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
    dispatch_from_idx: int = Form(0),
    recipient_email: str   = Form(...),
) -> AckResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_FILES} files allowed per request")

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

    dispatch_options = request.app.state.dispatch_options
    dispatch_from    = dispatch_options[dispatch_from_idx] if dispatch_options else {}
    recipients       = _build_recipients(recipient_email)

    background_tasks.add_task(
        _process_and_email,
        file_items,
        request.app.state.config_df,
        request.app.state.state_codes,
        dispatch_from,
        request.app.state.model,
        recipients,
    )

    n = len(file_items)
    skipped_note = f" ({len(skipped)} unsupported file(s) skipped)" if skipped else ""
    return AckResponse(
        queued=True,
        message=f"{n} file(s) queued for processing{skipped_note}. Results will be emailed to {', '.join(recipients)}.",
    )
