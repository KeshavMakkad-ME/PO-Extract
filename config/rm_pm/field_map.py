NUMBER_FIELDS = {
    "billed_quantity", "item_rate", "taxable_amount",
    "invoice_amount", "cgst_amount", "sgst_amount", "igst_amount",
    "freight_charges",
}

HEADERS = ["col_letter", "field_name", "datatype", "source", "hardcoded_value", "description", "mandatory"]

# Fields that belong to individual line items (vs invoice-level)
LINE_ITEM_FIELDS = {
    "item_name", "billed_quantity", "item_rate", "taxable_amount",
    "cgst_name", "sgst_name", "igst_name",
    "cgst_amount", "sgst_amount", "igst_amount",
    "batch_number", "manuf_date", "expire_date",
}
