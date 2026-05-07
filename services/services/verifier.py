import json

import pandas as pd


def build_verification_prompt(invoice_text: str, extracted_data: dict, config_df: pd.DataFrame) -> str:
    verifiable = config_df[config_df["source"] == "extracted"]
    verifiable_names = set(verifiable["field_name"].tolist())

    field_ctx = "\n".join(
        f'  - {row["field_name"]}: {row["description"]}'
        for _, row in verifiable.iterrows()
    )

    inv_vals = {
        k: v for k, v in extracted_data.items()
        if k not in ("line_items",) and k in verifiable_names
    }

    items_parts = []
    for i, item in enumerate(extracted_data.get("line_items", []), 1):
        item_vals = {k: v for k, v in item.items() if k in verifiable_names}
        if item_vals:
            items_parts.append(f"Line Item {i}: {json.dumps(item_vals, ensure_ascii=False)}")

    extracted_block = json.dumps(inv_vals, ensure_ascii=False, indent=2)
    if items_parts:
        extracted_block += "\n\n" + "\n".join(items_parts)

    return f"""You are a strict financial data auditor verifying AI-extracted service invoice data.
This data will be recorded in Tally for GST accounting — accuracy directly affects
tax credits and financial reporting.

You are auditing a service invoice (e.g. Meta Ads, cloud services, professional fees).
Pay close attention to:
- supplier_invoice_number: must match the invoice number exactly as printed by the vendor
- supplier_invoice_date: must match the date printed on the vendor's invoice
- party_name: must match the supplier/vendor name as printed on the invoice
- purchase_amount: pre-tax amount per line item — verify it matches what is printed
- igst_amount: must match the IGST amount shown on the invoice

FIELD REFERENCE (what each field is supposed to contain):
{field_ctx}

EXTRACTED DATA:
{extracted_block}

ORIGINAL INVOICE TEXT:
{invoice_text}

VERIFICATION RULES:
1. ACCEPTABLE format differences — do NOT flag:
   - Dates reformatted to DD/MM/YYYY from any source format
   - Capitalisation, punctuation, extra whitespace
   - Minor vendor name variations (e.g. "Meta Platforms Inc" vs "Meta Platforms, Inc.")
   - Tax name formatting variations
2. MUST flag — critical differences:
   - Wrong supplier invoice number (any character mismatch)
   - Amount that clearly differs from what is printed on the invoice
3. Do NOT flag empty string values ("") — they legitimately mean the field was absent
4. ANTI-HALLUCINATION — most important rule: before flagging any field, you MUST quote the exact
   verbatim text from the invoice that contradicts the extracted value.
   Include it as: 'Source text: "..."'. If you cannot find and quote conflicting source text,
   do NOT flag under any circumstances.
5. Only flag what the invoice actually says — never infer or assume what it "should" say.
6. FLAGS MUST CONTAIN ONLY REAL DISCREPANCIES — if you verified a field and it matches,
   do NOT add it to the flags array at all. Never write an entry with words like "matches",
   "no issue", "consistent with", or "correct" in the issue field. If a field is correct,
   simply leave it out of flags entirely. A flag = a genuine problem only.

Return ONLY valid JSON, no explanation, no markdown:
{{
  "passed": true,
  "flags": [],
  "summary": "All invoice fields verified against source document"
}}

If issues are found:
{{
  "passed": false,
  "flags": [
    {{
      "field": "supplier_invoice_number",
      "extracted_value": "ADS607-105342671",
      "issue": "Source text: \\"Invoice No: ADS607-105342672\\" — last digit differs",
      "severity": "critical"
    }}
  ],
  "summary": "1 critical issue found"
}}
"""
