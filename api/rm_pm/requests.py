from typing import Annotated, List

from fastapi import File, UploadFile

MAX_FILES = 100
ALLOWED_EXTENSIONS = frozenset({"pdf"})

UploadedRmPmFiles = Annotated[
    List[UploadFile],
    File(description="RM/PM vendor invoice PDF files — up to 100 files"),
]
