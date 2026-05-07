from typing import Annotated

from fastapi import File, UploadFile

ALLOWED_EXTENSIONS = {"pdf"}
MAX_FILES = 100

UploadedServicesFiles = Annotated[list[UploadFile], File(...)]
