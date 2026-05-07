import logging
import os

import openpyxl
import pandas as pd

logger = logging.getLogger(__name__)

TEMPLATE_PATH = os.environ.get("TEMPLATE_PATH", "templates/Finance_XLSX_Templates_new_new.xlsx")


def load_field_config() -> pd.DataFrame:
    wb = openpyxl.load_workbook(TEMPLATE_PATH, read_only=True, data_only=True)
    ws = wb["field_config_services"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    headers = [str(h) for h in rows[0]]
    data = [[str(v) if v is not None else "" for v in row] for row in rows[1:]]
    df = pd.DataFrame(data, columns=headers)
    df = df[df["field_name"].notna() & (df["field_name"] != "")].reset_index(drop=True)
    logger.info(f"Loaded field_config_services: {len(df)} fields")
    return df
