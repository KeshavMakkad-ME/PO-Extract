import logging
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def _smtp_connection():
    host     = os.environ["SMTP_HOST"]
    port     = int(os.environ.get("SMTP_PORT", 587))
    user     = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]

    server = smtplib.SMTP(host, port)
    server.ehlo()
    server.starttls()
    server.login(user, password)
    return server, user


def send_result_email(
    recipient: str,
    xlsx_bytes: bytes,
    successful: int,
    total_line_items: int,
    errors: list[str],
) -> None:
    server, sender = _smtp_connection()

    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = recipient
    msg["Subject"] = f"E-Invoice Ready — {successful} PO(s), {total_line_items} line item(s)"

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
    msg.attach(MIMEText(body, "plain"))

    attachment = MIMEApplication(xlsx_bytes, _subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    attachment.add_header("Content-Disposition", "attachment", filename="e_invoice_output.xlsx")
    msg.attach(attachment)

    server.sendmail(sender, recipient, msg.as_string())
    server.quit()
    logger.info(f"Result email sent to {recipient}")


def send_error_email(recipient: str, errors: list[str]) -> None:
    server, sender = _smtp_connection()

    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = recipient
    msg["Subject"] = "E-Invoice Processing Failed"

    error_lines = "\n".join(f"  • {e}" for e in errors)
    body = (
        f"Hi,\n\n"
        f"Unfortunately all files failed to process:\n\n"
        f"{error_lines}\n\n"
        f"Please check the files and try again.\n\n"
        f"— PO Converter"
    )
    msg.attach(MIMEText(body, "plain"))

    server.sendmail(sender, recipient, msg.as_string())
    server.quit()
    logger.info(f"Error email sent to {recipient}")
