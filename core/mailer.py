import base64
import logging
import os

import resend

logger = logging.getLogger(__name__)


def _send(to: str, subject: str, body: str, xlsx_bytes: bytes | None = None) -> None:
    resend.api_key = os.environ["RESEND_API_KEY"]
    sender = os.environ.get("EMAIL_FROM", "finance@doveriye.com")

    params: dict = {
        "from": sender,
        "to":   [to],
        "subject": subject,
        "text": body,
    }

    if xlsx_bytes:
        params["attachments"] = [{
            "filename": "e_invoice_output.xlsx",
            "content":  base64.b64encode(xlsx_bytes).decode(),
        }]

    resend.Emails.send(params)


def send_result_email(
    recipient: str,
    xlsx_bytes: bytes,
    successful: int,
    total_line_items: int,
    errors: list[str],
) -> None:
    error_section = ""
    if errors:
        error_lines = "\n".join(f"  • {e}" for e in errors)
        error_section = f"\n\nThe following files could not be processed:\n{error_lines}"

    body = (
        f"Hi,\n\n"
        f"Your E-Invoice file is ready.\n\n"
        f"  POs processed : {successful}\n"
        f"  Line items    : {total_line_items}\n"
        f"  Errors        : {len(errors)}"
        f"{error_section}\n\n"
        f"The XLSX is attached. Upload it directly to the GST portal.\n\n"
        f"— PO Converter"
    )

    _send(
        to=recipient,
        subject=f"E-Invoice Ready — {successful} PO(s), {total_line_items} line item(s)",
        body=body,
        xlsx_bytes=xlsx_bytes,
    )
    logger.info(f"Result email sent to {recipient}")


def send_error_email(recipient: str, errors: list[str]) -> None:
    error_lines = "\n".join(f"  • {e}" for e in errors)
    body = (
        f"Hi,\n\n"
        f"Unfortunately all files failed to process:\n\n"
        f"{error_lines}\n\n"
        f"Please check the files and try again.\n\n"
        f"— PO Converter"
    )

    _send(
        to=recipient,
        subject="E-Invoice Processing Failed",
        body=body,
    )
    logger.info(f"Error email sent to {recipient}")
