from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


SUPPORTED_EXTENSIONS = {".csv", ".xls", ".xlsx"}


@dataclass
class ProcessedFile:
    file_path: Path
    table_name: str
    file_date: str
    data: pd.DataFrame


def get_file_details(file_path: str | Path) -> tuple[str, str]:
    """Return the Oracle table name and date from TABLE_NAME_date.csv."""
    path = Path(file_path)

    try:
        table_name, file_date = path.stem.rsplit("_", maxsplit=1)
    except ValueError as error:
        raise ValueError(
            f"Expected a file named TABLE_NAME_date.ext, received: {path.name}"
        ) from error

    if not table_name or not file_date:
        raise ValueError(f"Could not determine table name and date from: {path.name}")

    table_name = table_name.replace("-", "_")
    return table_name.upper(), file_date


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
