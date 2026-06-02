from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

import oracledb
import pandas as pd

from process_files import ProcessedFile, find_files, process_files


ORACLE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")
DATE_ADDED_COLUMN = "DATE_ADDED"

# Add Oracle reserved or project-specific column replacements here.
COLUMN_NAME_REPLACEMENTS = {
    "DATE": "EVENT_DATE",
}


def push_files(
    file_paths: str | Path | Iterable[str | Path],
    oracle_user: str,
    oracle_password: str,
    oracle_dsn: str,
    uploaded_directory: str | Path | None = None,
) -> None:
    """Insert files into Oracle, then optionally move them to an archive folder."""
    source_files = _get_file_paths(file_paths)

    if uploaded_directory:
        source_files, skipped_files = _split_archived_files(
            source_files,
            uploaded_directory,
        )
        archive_files(skipped_files, uploaded_directory)

    processed_files = process_files(source_files)
    if not processed_files:
        return

    with oracledb.connect(
        user=oracle_user,
        password=oracle_password,
        dsn=oracle_dsn,
    ) as connection:
        push_processed_files(connection, processed_files)

    if uploaded_directory:
        archive_processed_files(processed_files, uploaded_directory)


def _get_file_paths(
    file_paths: str | Path | Iterable[str | Path],
) -> list[Path]:
    """Return files from a directory path, a single file path, or many paths."""
    if isinstance(file_paths, (str, Path)):
        path = Path(file_paths)

        if path.is_dir():
            return find_files(path)

        return [path]

    return [Path(path) for path in file_paths]


def _split_archived_files(
    file_paths: list[Path],
    uploaded_directory: str | Path,
) -> tuple[list[Path], list[Path]]:
    """Separate new files from files whose names already exist in the archive."""
    uploaded_path = Path(uploaded_directory)
    uploaded_path.mkdir(parents=True, exist_ok=True)
    new_files = []
    skipped_files = []

    for file_path in file_paths:
        if _is_inside_directory(file_path, uploaded_path):
            continue

        if (uploaded_path / file_path.name).exists():
            print(f"Skipped {file_path.name}: already uploaded to Oracle")
            skipped_files.append(file_path)
        else:
            new_files.append(file_path)

    return new_files, skipped_files


def _is_inside_directory(file_path: Path, directory: Path) -> bool:
    """Return whether one file is already inside a directory."""
    try:
        file_path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def push_processed_files(
    connection,
    processed_files: dict[str, list[ProcessedFile]],
) -> None:
    """Insert all processed files and commit once everything succeeds."""
    try:
        for table_name, files_for_table in processed_files.items():
            for processed_file in files_for_table:
                push_dataframe(connection, table_name, processed_file.data)
                print(
                    f"Inserted {len(processed_file.data)} rows from "
                    f"{processed_file.file_path.name} into {table_name}"
                )

        connection.commit()
    except Exception:
        connection.rollback()
        raise


def archive_processed_files(
    processed_files: dict[str, list[ProcessedFile]],
    uploaded_directory: str | Path,
) -> None:
    """Move successfully uploaded source files into the archive folder."""
    file_paths = [
        processed_file.file_path
        for files_for_table in processed_files.values()
        for processed_file in files_for_table
    ]
    archive_files(file_paths, uploaded_directory)


def archive_files(
    file_paths: Iterable[str | Path],
    uploaded_directory: str | Path,
) -> None:
    """Move source files into the archive folder without overwriting older files."""
    uploaded_path = Path(uploaded_directory)
    uploaded_path.mkdir(parents=True, exist_ok=True)

    for file_path in file_paths:
        source_path = Path(file_path)
        destination = _get_archive_destination(uploaded_path, source_path.name)
        shutil.move(str(source_path), str(destination))
        print(f"Moved {source_path.name} to {destination}")


def _get_archive_destination(uploaded_directory: Path, file_name: str) -> Path:
    """Return an unused archive path without overwriting an older upload."""
    destination = uploaded_directory / file_name
    if not destination.exists():
        return destination

    file_path = Path(file_name)
    uploaded_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = uploaded_directory / f"{file_path.stem}_{uploaded_at}{file_path.suffix}"
    duplicate_number = 1

    while destination.exists():
        destination = uploaded_directory / (
            f"{file_path.stem}_{uploaded_at}_{duplicate_number}{file_path.suffix}"
        )
        duplicate_number += 1

    return destination


def push_dataframe(connection, table_name: str, dataframe: pd.DataFrame) -> None:
    """Create the target table when needed, then insert one DataFrame."""
    if dataframe.empty:
        return

    _validate_identifier(table_name)
    columns = _sanitize_column_names(dataframe.columns)
    _validate_date_added_column(columns)

    if not table_exists(connection, table_name):
        create_table(connection, table_name, dataframe)
    elif not table_column_exists(connection, table_name, DATE_ADDED_COLUMN):
        add_date_added_column(connection, table_name)

    insert_columns = [*columns, DATE_ADDED_COLUMN]
    column_list = ", ".join(insert_columns)
    bind_variables = ", ".join(
        f":{number}" for number in range(1, len(insert_columns) + 1)
    )
    insert_sql = f"INSERT INTO {table_name} ({column_list}) VALUES ({bind_variables})"

    date_added = datetime.now()
    rows = [
        tuple(_to_oracle_value(value) for value in row) + (date_added,)
        for row in dataframe.itertuples(index=False, name=None)
    ]

    with connection.cursor() as cursor:
        cursor.executemany(insert_sql, rows)


def table_exists(connection, table_name: str) -> bool:
    """Return whether the current Oracle user already owns the table."""
    _validate_identifier(table_name)

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM user_tables WHERE table_name = :1",
            [table_name.upper()],
        )
        return cursor.fetchone()[0] > 0


def table_column_exists(connection, table_name: str, column_name: str) -> bool:
    """Return whether an Oracle table already contains one column."""
    _validate_identifier(table_name)
    _validate_identifier(column_name)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM user_tab_columns
            WHERE table_name = :1 AND column_name = :2
            """,
            [table_name.upper(), column_name.upper()],
        )
        return cursor.fetchone()[0] > 0


def add_date_added_column(connection, table_name: str) -> None:
    """Add the load timestamp column to an existing Oracle table."""
    _validate_identifier(table_name)

    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {table_name} ADD {DATE_ADDED_COLUMN} DATE")

    print(f"Added {DATE_ADDED_COLUMN} column to {table_name}")


def create_table(connection, table_name: str, dataframe: pd.DataFrame) -> None:
    """Create an Oracle table using the columns and types in one DataFrame."""
    _validate_identifier(table_name)
    column_definitions = []
    column_names = _sanitize_column_names(dataframe.columns)
    _validate_date_added_column(column_names)

    for column, column_name in zip(dataframe.columns, column_names):
        oracle_type = _get_oracle_type(dataframe[column])
        column_definitions.append(f"{column_name} {oracle_type}")

    column_definitions.append(f"{DATE_ADDED_COLUMN} DATE")
    create_sql = f"CREATE TABLE {table_name} ({', '.join(column_definitions)})"

    with connection.cursor() as cursor:
        cursor.execute(create_sql)

    print(f"Created table {table_name}")


def _get_oracle_type(series: pd.Series) -> str:
    """Map a pandas column to a simple Oracle data type."""
    if pd.api.types.is_bool_dtype(series):
        return "CHAR(1)"
    """
    # Commented these so these should go as VARCHAR2, but can be easily changed back if needed.
    if pd.api.types.is_integer_dtype(series):
        return "NUMBER"

    if pd.api.types.is_float_dtype(series):
        return "NUMBER"
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return "DATE"

    max_length = series.dropna().astype(str).str.len().max()
    max_length = 1 if pd.isna(max_length) else int(max_length)

    if max_length > 4000:
        return "CLOB"

    max_length = max(255, max_length)
    return f"VARCHAR2({max_length})"


def _sanitize_column_names(columns) -> list[str]:
    """Return unique Oracle-friendly column names."""
    sanitized_columns = [_sanitize_column_name(column) for column in columns]

    if len(sanitized_columns) != len(set(sanitized_columns)):
        raise ValueError(
            "Two or more source columns become the same Oracle column name after "
            f"sanitization: {sanitized_columns}"
        )

    return sanitized_columns


def _validate_date_added_column(columns: list[str]) -> None:
    if DATE_ADDED_COLUMN in columns:
        raise ValueError(
            f"Source files cannot contain the reserved column: {DATE_ADDED_COLUMN}"
        )


def _to_oracle_value(value):
    """Convert pandas values into values accepted by Oracle."""
    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()

    return value


def _sanitize_column_name(column) -> str:
    """Convert one source header into an Oracle-friendly column name."""
    column_name = re.sub(r"[^A-Za-z0-9_$#]+", "_", str(column))
    column_name = column_name.strip("_").upper()

    if not column_name:
        raise ValueError(f"Could not create an Oracle column name from: {column}")

    if not column_name[0].isalpha():
        column_name = f"COLUMN_{column_name}"

    column_name = COLUMN_NAME_REPLACEMENTS.get(column_name, column_name)

    _validate_identifier(column_name)
    return column_name


def _validate_identifier(identifier: str) -> None:
    if not ORACLE_IDENTIFIER.fullmatch(identifier):
        raise ValueError(f"Invalid Oracle identifier: {identifier}")
