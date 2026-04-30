import os
from pathlib import Path

from dotenv import load_dotenv
import requests
import streamlit as st

load_dotenv(Path(__file__).parent / ".env")

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")


@st.cache_data(ttl=300)
def fetch_dispatch_options() -> list[dict]:
    try:
        r = requests.get(f"{API_URL}/dispatch-options", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def _init_state():
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0
    if "submitted" not in st.session_state:
        st.session_state.submitted = None  # dict with message info after submit


def main():
    st.set_page_config(
        page_title="PO → E-Invoice",
        page_icon="📄",
        layout="wide",
    )

    _init_state()

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

    # ── Header ─────────────────────────────────────────────────────────────────
    st.title("PO → E-Invoice Converter")
    st.caption("Convert BlinkIt and Flipkart Purchase Orders into a ready-to-upload E-Invoice Excel file. Results are emailed to you.")

    st.divider()

    left, right = st.columns([3, 2], gap="large")

    with left:
        # ── Dispatch From ───────────────────────────────────────────────────────
        st.subheader("Dispatch Location")
        dispatch_options = fetch_dispatch_options()

        if not dispatch_options:
            st.warning("Could not load dispatch locations — is the backend running?")
            dispatch_idx = 0
        else:
            labels = [
                f"{opt.get('Location', 'Unknown')}  ·  {opt.get('name', '')}"
                for opt in dispatch_options
            ]
            selected = st.selectbox("Ship from", labels, label_visibility="collapsed")
            dispatch_idx = labels.index(selected)
            chosen = dispatch_options[dispatch_idx]
            st.caption(
                f"{chosen.get('Address', '')}  |  "
                f"{chosen.get('State', '')}  —  {chosen.get('Pincode', '')}"
            )

        st.divider()

        # ── Email ───────────────────────────────────────────────────────────────
        st.subheader("Email")
        recipient_email = st.text_input(
            "Send results to",
            placeholder="you@company.com",
            label_visibility="collapsed",
        )

        st.divider()

        # ── Upload ──────────────────────────────────────────────────────────────
        st.subheader("Upload Purchase Orders")
        st.caption("BlinkIt — PDF   ·   Flipkart — PDF or CSV")
        uploaded_files = st.file_uploader(
            "Drop files here",
            type=["pdf", "csv"],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key=f"uploader_{st.session_state.uploader_key}",
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

        # ── Submit ──────────────────────────────────────────────────────────────
        ready = bool(uploaded_files and recipient_email and recipient_email.strip())
        submit_btn = st.button(
            "Process & Email Results",
            type="primary",
            disabled=not ready,
            use_container_width=True,
        )

        if submit_btn and ready:
            with st.spinner(f"Submitting {len(uploaded_files)} file(s)…"):
                try:
                    files_payload = [
                        ("files", (f.name, f.read(), "application/octet-stream"))
                        for f in uploaded_files
                    ]
                    response = requests.post(
                        f"{API_URL}/process",
                        files=files_payload,
                        data={
                            "dispatch_from_idx": dispatch_idx,
                            "recipient_email":   recipient_email.strip(),
                        },
                        timeout=60,
                    )
                    response.raise_for_status()
                    data = response.json()
                    st.session_state.submitted = {
                        "email":   recipient_email.strip(),
                        "message": data.get("message", ""),
                        "count":   len(uploaded_files),
                    }
                    st.session_state.uploader_key += 1
                    st.rerun()

                except requests.exceptions.ConnectionError:
                    st.error("Cannot reach the backend. Make sure the server is running on port 8000.")
                except requests.exceptions.Timeout:
                    st.error("Request timed out.")
                except requests.exceptions.HTTPError as exc:
                    try:
                        detail = exc.response.json().get("detail", str(exc))
                    except Exception:
                        detail = str(exc)
                    st.error(f"Server error: {detail}")
                except Exception as exc:
                    st.error(f"Unexpected error: {exc}")

    with right:
        # ── Status panel ────────────────────────────────────────────────────────
        st.subheader("Status")

        sub = st.session_state.submitted
        if sub is None:
            st.markdown(
                "<div style='color:#adb5bd; margin-top:3rem; text-align:center;'>"
                "Upload files and submit to get started."
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.success(f"Submitted — {sub['count']} file(s) queued for processing.")
            st.info(f"Results will be emailed to **{sub['email']}**.\n\nThis usually takes 1–3 minutes depending on the number of files.")

            if st.button("Submit another batch", use_container_width=True):
                st.session_state.submitted = None
                st.rerun()


if __name__ == "__main__":
    main()
