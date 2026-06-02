from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


SUPPORTED_EXTENSIONS = {".csv", ".xls", ".xlsx"}

# Add the special file patterns here. The trailing % matches the changing date.
APP_PREFIX_FILE_PATTERNS = {
    "sample-file%",
    "another_sample_file%",
}


@dataclass
class ProcessedFile:
    file_path: Path
    table_name: str
    file_date: str
    data: pd.DataFrame


def get_file_details(file_path: str | Path) -> tuple[str, str]:
    """Return the Oracle table name and date from TABLE_NAMEYYYYMMDD.csv."""
    path = Path(file_path)
    table_name = path.stem[:-8]
    file_date = path.stem[-8:]

    try:
        datetime.strptime(file_date, "%Y%m%d")
    except ValueError as error:
        raise ValueError(
            f"Expected a file named TABLE_NAMEYYYYMMDD.ext, received: {path.name}"
        ) from error

    if not table_name:
        raise ValueError(f"Could not determine table name from: {path.name}")

    table_name = table_name.replace("-", "_")

    if _needs_app_prefix(path.stem):
        table_name = f"APP_{table_name}"

    return table_name.upper(), file_date


def _needs_app_prefix(file_stem: str) -> bool:
    """Return whether a source file should use an APP_ table prefix."""
    file_stem = file_stem.lower()

    for pattern in APP_PREFIX_FILE_PATTERNS:
        file_name_prefix = pattern.removesuffix("%").lower()

        if file_stem.startswith(file_name_prefix):
            return True

    return False


def read_file(file_path: str | Path) -> pd.DataFrame:
    """Read one CSV or Excel file into a pandas DataFrame."""
    path = Path(file_path)
    extension = path.suffix.lower()

    if extension == ".csv":
        return pd.read_csv(path)

    if extension in {".xls", ".xlsx"}:
        return pd.read_excel(path)

    raise ValueError(f"Unsupported file type: {path.name}")


def process_file(file_path: str | Path) -> ProcessedFile:
    """Read one source file and attach its Oracle table metadata."""
    path = Path(file_path)
    table_name, file_date = get_file_details(path)

    return ProcessedFile(
        file_path=path,
        table_name=table_name,
        file_date=file_date,
        data=read_file(path),
    )


def process_directory(
    input_directory: str | Path,
) -> dict[str, list[ProcessedFile]]:
    """Group processed files by their target Oracle table name."""
    input_path = Path(input_directory)
    file_paths = (
        file_path
        for file_path in sorted(input_path.iterdir())
        if file_path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    return process_files(file_paths)


def process_files(file_paths: Iterable[str | Path]) -> dict[str, list[ProcessedFile]]:
    """Group selected source files by their target Oracle table name."""
    processed_files = {}

    for file_path in file_paths:
        processed_file = process_file(file_path)
        processed_files.setdefault(processed_file.table_name, []).append(processed_file)

    return processed_files
