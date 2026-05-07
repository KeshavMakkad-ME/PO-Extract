import json

import pandas as pd


def build_verification_prompt(po_text: str, extracted_data: dict, config_df: pd.DataFrame) -> str:
    verifiable = config_df[config_df["source"] == "extracted"]
    verifiable_names = set(verifiable["field_name"].tolist())

    field_ctx = "\n".join(
        f'  - {row["field_name"]}: {row["description"]}'
        for _, row in verifiable.iterrows()
    )

    po_vals = {
        k: v for k, v in extracted_data.items()
        if k not in ("line_items",) and k in verifiable_names
    }

    items_parts = []
    for i, item in enumerate(extracted_data.get("line_items", []), 1):
        item_vals = {k: v for k, v in item.items() if k in verifiable_names}
        if item_vals:
            items_parts.append(f"Line Item {i}: {json.dumps(item_vals, ensure_ascii=False)}")

    extracted_block = json.dumps(po_vals, ensure_ascii=False, indent=2)
    if items_parts:
        extracted_block += "\n\n" + "\n".join(items_parts)

    return f"""You are a strict financial data auditor verifying AI-extracted Purchase Order (PO) data.
This data will be used to generate Indian GST e-invoices — every field directly affects legal tax filings.

You are specifically auditing a Purchase Order. Pay close attention to:
- invoice_number / PO number: must match digit-for-digit as printed on the PO
- party_gstin: 15-character alphanumeric GSTIN — any single character mismatch is critical
- invoice_date and dispatch_date: must correspond to the dates printed on the PO
- HSN codes: must match exactly — wrong HSN codes cause GST classification errors
- unit_price: must be the Basic Cost Price, NOT landing rate or MRP
- Dispatch address and party address fields: verify against the "Ship To" / "Bill To" sections

FIELD REFERENCE (what each field is supposed to contain):
{field_ctx}

EXTRACTED DATA:
{extracted_block}

ORIGINAL PURCHASE ORDER TEXT:
{po_text}

VERIFICATION RULES:
1. ACCEPTABLE format differences — do NOT flag:
   - Dates reformatted to DD/MM/YYYY from any source format (including timestamps, written months)
   - Capitalisation, punctuation, extra whitespace
   - Address abbreviations or well-known city-level variants (e.g. "Bengaluru" for "Bengaluru Urban")
   - Partial addresses that capture the essential identifying information
2. MUST flag — critical differences:
   - Wrong PO/invoice number digits
   - Any character mismatch in a GSTIN
   - Wrong HSN code
   - A unit price that clearly differs from the Basic Cost Price printed in the PO
   - Bill To / Ship To section mixing: if a party_* field (party_gstin, party_trade_name,
     party_address1, party_location, party_pincode) contains a value that appears under the
     "Ship To" heading in the source, flag it as critical — and vice versa for ship_to_* fields.
     To check: locate the extracted value in the source text and confirm which section heading
     ("Bill To" or "Ship To") precedes it.
3. Do NOT flag empty string values ("") — they legitimately mean the field was absent
4. ANTI-HALLUCINATION — most important rule: before flagging any field, you MUST quote the exact
   verbatim text from the source document that contradicts the extracted value.
   Include it as: 'Source text: "..."'. If you cannot find and quote conflicting source text,
   do NOT flag under any circumstances.
5. Only flag what the document actually says — never infer or assume what it "should" say.
6. Do NOT reason about plausibility of dates, years, or amounts. Your only job is text comparison.
7. FLAGS ARRAY = PROBLEMS ONLY. It is NOT a verification log.
   Before writing your response, scan every entry you planned to put in flags.
   DELETE any entry whose issue text contains "matches", "no issue", "consistent",
   "correct", "appears under", "matching", or any synonym meaning "this is fine".
   If that removes all entries, output "flags": [].
   A flags entry that says anything other than a genuine problem MUST be removed.

Return ONLY valid JSON, no explanation, no markdown:
{{
  "passed": true,
  "flags": [],
  "summary": "All PO fields verified against source document"
}}

If issues are found:
{{
  "passed": false,
  "flags": [
    {{
      "field": "party_gstin",
      "extracted_value": "29AAFCG9846E1Z7",
      "issue": "Source text: \\"GSTIN: 29AAFCG9846E1Z8\\" — last character differs",
      "severity": "critical"
    }}
  ],
  "summary": "1 critical issue found"
}}
"""
