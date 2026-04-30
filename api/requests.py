from typing import Annotated, List

from fastapi import File, UploadFile

MAX_FILES = 100
ALLOWED_EXTENSIONS = frozenset({"pdf", "csv"})

# Self-documenting type alias used in the router — keeps the route signature clean
UploadedFiles = Annotated[
    List[UploadFile],
    File(description="PDF (BlinkIt) or CSV (Zepto) Purchase Order files — up to 100 files"),
]
