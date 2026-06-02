from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd


SUPPORTED_EXTENSIONS = {".csv", ".xls", ".xlsx"}
DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y%m%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%B %d, %Y",
    "%b %d, %Y",
)

# Add source-file headers that must be parsed as dates here.
DATE_COLUMN_NAMES = {
    "DATE",
    "POSTING DATE",
    "SAMPLE DATE",
}

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
        dataframe = pd.read_csv(path)
    elif extension in {".xls", ".xlsx"}:
        dataframe = pd.read_excel(path)
    else:
        raise ValueError(f"Unsupported file type: {path.name}")

    return _parse_date_columns(dataframe, path)


def _parse_date_columns(dataframe: pd.DataFrame, file_path: Path) -> pd.DataFrame:
    """Parse configured source headers into pandas datetime columns."""
    configured_columns = {column.strip().upper() for column in DATE_COLUMN_NAMES}

    for column in dataframe.columns:
        if str(column).strip().upper() not in configured_columns:
            continue

        dataframe[column] = pd.to_datetime(
            [
                _parse_date_value(value, file_path, str(column))
                for value in dataframe[column]
            ]
        )

    return dataframe


def _parse_date_value(value, file_path: Path, column_name: str):
    """Parse one configured date value or raise a useful error."""
    if pd.isna(value) or isinstance(value, str) and not value.strip():
        return pd.NaT

    if isinstance(value, datetime):
        return value

    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())

    value_as_text = str(value).strip()

    for date_format in DATE_FORMATS:
        for time_format in ("", " %H:%M", " %H:%M:%S"):
            try:
                return datetime.strptime(value_as_text, date_format + time_format)
            except ValueError:
                continue

    raise ValueError(
        f"Invalid date value in {file_path.name}, column {column_name}: {value!r}"
    )


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
    """Group files from a directory and its subfolders by Oracle table name."""
    return process_files(find_files(input_directory))


def find_files(input_directory: str | Path) -> list[Path]:
    """Return supported files from a directory and its subfolders."""
    input_path = Path(input_directory)
    return [
        file_path
        for file_path in sorted(input_path.rglob("*"))
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]


def process_files(file_paths: Iterable[str | Path]) -> dict[str, list[ProcessedFile]]:
    """Group selected source files by their target Oracle table name."""
    processed_files = {}

    for file_path in file_paths:
        processed_file = process_file(file_path)
        processed_files.setdefault(processed_file.table_name, []).append(processed_file)

    return processed_files
