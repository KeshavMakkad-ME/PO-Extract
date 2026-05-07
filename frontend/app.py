import logging
import os
from pathlib import Path

from dotenv import load_dotenv
import requests
import streamlit as st

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).parent / ".env")

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
logger.info(f"Frontend starting — API_URL: {API_URL}")


@st.cache_data(ttl=300)
def fetch_dispatch_options() -> list[dict]:
    try:
        r = requests.get(f"{API_URL}/dispatch-options", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


@st.cache_data(ttl=300)
def fetch_rm_pm_options() -> dict:
    try:
        r = requests.get(f"{API_URL}/rm-pm/options", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {"voucher_type_names": [], "purchase_ledgers": []}


def _init_state(prefix: str):
    defaults = {
        f"{prefix}_uploader_key":        0,
        f"{prefix}_submitted":           None,
        f"{prefix}_is_loading":          False,
        f"{prefix}_pending_submission":  None,
        f"{prefix}_submit_error":        None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _do_submission(endpoint: str, prefix: str) -> None:
    pending = st.session_state[f"{prefix}_pending_submission"]
    try:
        files_payload = [
            ("files", (name, data, mime))
            for name, data, mime in pending["files"]
        ]
        logger.info(f"Submitting {pending['count']} file(s) to {endpoint}")
        response = requests.post(
            endpoint,
            files=files_payload,
            data=pending.get("form_data", {}),
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        st.session_state[f"{prefix}_submitted"] = {
            "email":   pending["email"],
            "message": data.get("message", ""),
            "count":   pending["count"],
        }
        st.session_state[f"{prefix}_submit_error"] = None
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection error — {endpoint}: {e}")
        st.session_state[f"{prefix}_submit_error"] = (
            "Cannot reach the backend. Make sure the server is running on port 8000."
        )
    except requests.exceptions.Timeout:
        st.session_state[f"{prefix}_submit_error"] = "Request timed out."
    except requests.exceptions.HTTPError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        st.session_state[f"{prefix}_submit_error"] = f"Server error: {detail}"
    except Exception as exc:
        st.session_state[f"{prefix}_submit_error"] = f"Unexpected error: {exc}"
    finally:
        st.session_state[f"{prefix}_is_loading"]         = False
        st.session_state[f"{prefix}_pending_submission"] = None


def _render_status_panel(prefix: str):
    st.subheader("Status")

    if st.session_state[f"{prefix}_is_loading"]:
        pending = st.session_state[f"{prefix}_pending_submission"]
        count   = pending["count"] if pending else "your"
        with st.spinner(f"Submitting {count} file(s)… please wait."):
            _do_submission(
                st.session_state[f"{prefix}_endpoint"],
                prefix,
            )
        st.rerun()

    elif st.session_state[f"{prefix}_submit_error"]:
        st.error(st.session_state[f"{prefix}_submit_error"])
        if st.button("Dismiss", key=f"{prefix}_dismiss", use_container_width=True):
            st.session_state[f"{prefix}_submit_error"] = None
            st.rerun()

    else:
        sub = st.session_state[f"{prefix}_submitted"]
        if sub is None:
            st.markdown(
                "<div style='color:#adb5bd; margin-top:3rem; text-align:center;'>"
                "Upload files and submit to get started."
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.success(f"Submitted — {sub['count']} file(s) queued for processing.")
            st.info(
                f"Results will be emailed to **{sub['email']}**.\n\n"
                "This usually takes 1–3 minutes depending on the number of files."
            )
            if st.button("Submit another batch", key=f"{prefix}_another", use_container_width=True):
                st.session_state[f"{prefix}_submitted"] = None
                st.rerun()


def render_po_tab():
    prefix = "po"
    _init_state(prefix)

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.subheader("Dispatch Location")
        dispatch_options = fetch_dispatch_options()

        if not dispatch_options:
            st.warning("Could not load dispatch locations — is the backend running?")
            dispatch_idx = None
        else:
            labels = [
                f"{opt.get('Location', 'Unknown')}  ·  {opt.get('name', '')}"
                for opt in dispatch_options
            ]
            selected     = st.selectbox("Ship from", labels, label_visibility="collapsed", key="po_dispatch")
            dispatch_idx = labels.index(selected)
            chosen       = dispatch_options[dispatch_idx]
            st.caption(
                f"{chosen.get('Address', '')}  |  "
                f"{chosen.get('State', '')}  —  {chosen.get('Pincode', '')}"
            )

        st.divider()

        st.subheader("Email")
        recipient_email = st.text_input(
            "Send results to",
            placeholder="you@company.com",
            label_visibility="collapsed",
            key="po_email",
        )

        st.divider()

        st.subheader("PO Source")
        company = st.selectbox(
            "PO Source",
            options=["blinkit", "flipkart"],
            format_func=lambda x: x.capitalize(),
            label_visibility="collapsed",
            key="po_company",
        )

        st.divider()

        st.subheader("Upload Purchase Orders")
        st.caption("BlinkIt — PDF   ·   Flipkart — PDF or CSV")
        uploaded_files = st.file_uploader(
            "Drop files here",
            type=["pdf", "csv"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key=f"uploader_{st.session_state.po_uploader_key}",
        )

        if uploaded_files:
            pdf_files = [f for f in uploaded_files if f.name.lower().endswith(".pdf")]
            csv_files = [f for f in uploaded_files if f.name.lower().endswith(".csv")]
            badges = "".join(
                f'<span class="file-pill">PDF &nbsp;{f.name}</span>' for f in pdf_files
            ) + "".join(
                f'<span class="file-pill">CSV &nbsp;{f.name}</span>' for f in csv_files
            )
            st.markdown(badges, unsafe_allow_html=True)
            st.caption(f"{len(uploaded_files)} file(s) — {len(pdf_files)} PDF · {len(csv_files)} CSV")

        st.divider()

        ready = bool(
            uploaded_files
            and recipient_email
            and recipient_email.strip()
            and dispatch_idx is not None
        )
        if st.button(
            "Process & Email Results",
            type="primary",
            disabled=not ready or st.session_state.po_is_loading,
            use_container_width=True,
            key="po_submit",
        ):
            st.session_state.po_pending_submission = {
                "files": [(f.name, f.read(), "application/octet-stream") for f in uploaded_files],
                "form_data": {
                    "dispatch_from_idx": dispatch_idx,
                    "recipient_email":   recipient_email.strip(),
                    "company":           company,
                },
                "email": recipient_email.strip(),
                "count": len(uploaded_files),
            }
            st.session_state.po_endpoint   = f"{API_URL}/process"
            st.session_state.po_is_loading = True
            st.session_state.po_submit_error = None
            st.session_state.po_uploader_key += 1
            st.rerun()

    with right:
        _render_status_panel(prefix)


def render_rm_pm_tab():
    prefix = "inv"
    _init_state(prefix)

    inv_options = fetch_rm_pm_options()
    voucher_type_names = inv_options.get("voucher_type_names", [])
    purchase_ledgers   = inv_options.get("purchase_ledgers", [])

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.subheader("Voucher Type")
        if voucher_type_names:
            voucher_type_name = st.selectbox(
                "Voucher Type Name",
                options=voucher_type_names,
                label_visibility="collapsed",
                key="inv_voucher_type",
            )
        else:
            st.warning("Could not load voucher types — is the backend running?")
            voucher_type_name = None

        st.divider()

        st.subheader("Purchase Ledger")
        if purchase_ledgers:
            purchase_ledger = st.selectbox(
                "Purchase Ledger",
                options=purchase_ledgers,
                label_visibility="collapsed",
                key="inv_purchase_ledger",
            )
        else:
            st.warning("Could not load purchase ledgers — is the backend running?")
            purchase_ledger = None

        st.divider()

        st.subheader("Email")
        recipient_email = st.text_input(
            "Send results to",
            placeholder="you@company.com",
            label_visibility="collapsed",
            key="inv_email",
        )

        st.divider()

        st.subheader("Upload Invoices")
        st.caption("Vendor invoices — PDF only")
        uploaded_files = st.file_uploader(
            "Drop PDF invoices here",
            type=["pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key=f"inv_uploader_{st.session_state.inv_uploader_key}",
        )

        if uploaded_files:
            badges = "".join(
                f'<span class="file-pill">PDF &nbsp;{f.name}</span>'
                for f in uploaded_files
            )
            st.markdown(badges, unsafe_allow_html=True)
            st.caption(f"{len(uploaded_files)} file(s)")

        st.divider()

        ready = bool(
            uploaded_files
            and recipient_email
            and recipient_email.strip()
            and voucher_type_name
            and purchase_ledger
        )
        if st.button(
            "Process & Email Results",
            type="primary",
            disabled=not ready or st.session_state.inv_is_loading,
            use_container_width=True,
            key="inv_submit",
        ):
            st.session_state.inv_pending_submission = {
                "files": [(f.name, f.read(), "application/octet-stream") for f in uploaded_files],
                "form_data": {
                    "recipient_email":   recipient_email.strip(),
                    "voucher_type_name": voucher_type_name,
                    "purchase_ledger":   purchase_ledger,
                },
                "email": recipient_email.strip(),
                "count": len(uploaded_files),
            }
            st.session_state.inv_endpoint   = f"{API_URL}/rm-pm/process"
            st.session_state.inv_is_loading = True
            st.session_state.inv_submit_error = None
            st.session_state.inv_uploader_key += 1
            st.rerun()

    with right:
        _render_status_panel(prefix)


def render_services_tab():
    prefix = "svc"
    _init_state(prefix)

    inv_options = fetch_rm_pm_options()
    voucher_type_names = inv_options.get("voucher_type_names", [])

    left, right = st.columns([3, 2], gap="large")

    with left:
        st.subheader("Voucher Type")
        if voucher_type_names:
            voucher_type = st.selectbox(
                "Voucher Type",
                options=voucher_type_names,
                label_visibility="collapsed",
                key="svc_voucher_type",
            )
        else:
            st.warning("Could not load voucher types — is the backend running?")
            voucher_type = None

        st.divider()

        st.subheader("Purchase Ledger")
        purchase_ledger = st.text_input(
            "Purchase Ledger",
            placeholder="e.g. Marketing Exp @ Facebook MC",
            label_visibility="collapsed",
            key="svc_purchase_ledger",
        )

        st.divider()

        st.subheader("Email")
        recipient_email = st.text_input(
            "Send results to",
            placeholder="you@company.com",
            label_visibility="collapsed",
            key="svc_email",
        )

        st.divider()

        st.subheader("Upload Invoices")
        st.caption("Service invoices (Meta Ads, cloud, etc.) — PDF only")
        uploaded_files = st.file_uploader(
            "Drop PDF invoices here",
            type=["pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key=f"svc_uploader_{st.session_state.svc_uploader_key}",
        )

        if uploaded_files:
            badges = "".join(
                f'<span class="file-pill">PDF &nbsp;{f.name}</span>'
                for f in uploaded_files
            )
            st.markdown(badges, unsafe_allow_html=True)
            st.caption(f"{len(uploaded_files)} file(s)")

        st.divider()

        ready = bool(
            uploaded_files
            and recipient_email
            and recipient_email.strip()
            and voucher_type
        )
        if st.button(
            "Process & Email Results",
            type="primary",
            disabled=not ready or st.session_state.svc_is_loading,
            use_container_width=True,
            key="svc_submit",
        ):
            st.session_state.svc_pending_submission = {
                "files": [(f.name, f.read(), "application/octet-stream") for f in uploaded_files],
                "form_data": {
                    "recipient_email": recipient_email.strip(),
                    "voucher_type":    voucher_type,
                    "purchase_ledger": purchase_ledger.strip(),
                },
                "email": recipient_email.strip(),
                "count": len(uploaded_files),
            }
            st.session_state.svc_endpoint   = f"{API_URL}/services/process"
            st.session_state.svc_is_loading = True
            st.session_state.svc_submit_error = None
            st.session_state.svc_uploader_key += 1
            st.rerun()

    with right:
        _render_status_panel(prefix)


def main():
    st.set_page_config(
        page_title="Finance Tools",
        page_icon="📄",
        layout="wide",
    )

    st.markdown("""
    <style>
        .block-container { padding-top: 2rem; }
        div[data-testid="stMetric"] {
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 1rem 1.25rem;
        }
        div[data-testid="stMetric"] label { font-size: 0.8rem; color: #6c757d; }
        .file-pill {
            display: inline-block;
            background: #e7f3ff;
            border: 1px solid #b6d4fe;
            border-radius: 20px;
            padding: 2px 10px;
            margin: 2px;
            font-size: 0.8rem;
            color: #0a58ca;
        }
    </style>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.caption("Backend")
        st.code(API_URL, language=None)
        try:
            r = requests.get(f"{API_URL}/health", timeout=5)
            r.raise_for_status()
            health = r.json()
            if health.get("ready"):
                st.success("Connected & ready")
            else:
                st.warning("Connected but not ready")
        except Exception as e:
            st.error(f"Unreachable — {e}")

        st.divider()
        st.caption("Template")
        if st.button("Refresh from Google Sheets", use_container_width=True):
            with st.spinner("Downloading template…"):
                try:
                    resp = requests.post(f"{API_URL}/admin/refresh-template", timeout=90)
                    resp.raise_for_status()
                    data = resp.json()
                    st.success(
                        f"Updated ({data['size_kb']} KB) — "
                        f"{data['dispatch_options']} dispatch locations, "
                        f"{data['voucher_types']} voucher types, "
                        f"{data['purchase_ledgers']} purchase ledgers"
                    )
                    fetch_dispatch_options.clear()
                    fetch_rm_pm_options.clear()
                    st.rerun()
                except requests.exceptions.HTTPError as exc:
                    try:
                        detail = exc.response.json().get("detail", str(exc))
                    except Exception:
                        detail = str(exc)
                    st.error(f"Refresh failed: {detail}")
                except Exception as exc:
                    st.error(f"Refresh failed: {exc}")

    st.title("Finance Tools")
    st.divider()

    po_tab, rm_pm_tab, services_tab = st.tabs(["PO → E-Invoice", "RM / PM Invoices", "Services Invoices"])

    with po_tab:
        render_po_tab()

    with rm_pm_tab:
        render_rm_pm_tab()

    with services_tab:
        render_services_tab()


if __name__ == "__main__":
    main()
