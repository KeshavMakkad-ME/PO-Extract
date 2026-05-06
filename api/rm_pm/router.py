import logging
import os

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from openai import OpenAI

from api.rm_pm.requests import ALLOWED_EXTENSIONS, MAX_FILES, UploadedRmPmFiles
from api.common.responses import AckResponse
from core.extractor import extract_text_from_pdf
from services.rm_pm.gemini_client import extract_rm_pm_fields
from services.rm_pm.verifier import build_verification_prompt
from services.rm_pm.xlsx_builder import build_xlsx
from core.mailer import send_error_email, send_invoice_email
from core.verifier import verify_extraction
from utils.rm_pm.gsheet import load_field_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rm-pm")


def _build_recipients(submitted_email: str) -> list[str]:
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
    model: OpenAI,
    recipients: list[str],
    voucher_type_name: str,
    purchase_ledger: str,
) -> None:
    config_df = load_field_config()
    results: list     = []
    errors: list[str] = []

    for filename, file_bytes in file_items:
        try:
            text   = extract_text_from_pdf(file_bytes)
            result = extract_rm_pm_fields(text, config_df, model)
            result["voucher_type_name"] = voucher_type_name
            result["purchase_ledger"]   = purchase_ledger
            verification = verify_extraction(build_verification_prompt(text, result, config_df), model)
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
        xlsx_bytes, _ = build_xlsx(results, config_df)
        send_invoice_email(
            xlsx_bytes  = xlsx_bytes,
            recipients  = recipients,
            all_results = successful,
            errors      = errors or None,
            subject     = f"RM/PM Invoices Ready — {len(successful)} invoice(s) processed",
            filename    = "rm_pm_invoices.xlsx",
        )
    except Exception as e:
        logger.error(f"Failed to build or email XLSX: {e}", exc_info=True)
        send_error_email(recipients, errors + [f"XLSX build failed: {e}"])


@router.get("/options")
async def rm_pm_options(request: Request) -> dict:
    return request.app.state.rm_pm_options


@router.post("/process", response_model=AckResponse, status_code=202)
async def process_rm_pm(
    request: Request,
    background_tasks: BackgroundTasks,
    files: UploadedRmPmFiles,
    recipient_email:   str = Form(...),
    voucher_type_name: str = Form(...),
    purchase_ledger:   str = Form(...),
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
        raise HTTPException(status_code=400, detail="No supported files (PDF) found in upload")

    recipients = _build_recipients(recipient_email)

    background_tasks.add_task(
        _process_and_email,
        file_items,
        request.app.state.model,
        recipients,
        voucher_type_name,
        purchase_ledger,
    )

    n = len(file_items)
    skipped_note = f" ({len(skipped)} unsupported file(s) skipped)" if skipped else ""
    return AckResponse(
        queued=True,
        message=f"{n} RM/PM invoice(s) queued for processing{skipped_note}. Results will be emailed to {', '.join(recipients)}.",
    )
