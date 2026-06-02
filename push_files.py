from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import oracledb
import pandas as pd

from process_files import ProcessedFile, process_directory, process_files


ORACLE_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")

# Add Oracle reserved or project-specific column replacements here.
COLUMN_NAME_REPLACEMENTS = {
    "DATE": "EVENT_DATE",
}


def push_files(
    file_paths: str | Path | Iterable[str | Path],
    oracle_user: str,
    oracle_password: str,
    oracle_dsn: str,
) -> None:
    """Process a folder, one file, or selected files and insert their rows."""
    processed_files = _get_processed_files(file_paths)
    if not processed_files:
        return

    with oracledb.connect(
        user=oracle_user,
        password=oracle_password,
        dsn=oracle_dsn,
    ) as connection:
        push_processed_files(connection, processed_files)


def _get_processed_files(
    file_paths: str | Path | Iterable[str | Path],
) -> dict[str, list[ProcessedFile]]:
    """Process a directory path, a single file path, or multiple file paths."""
    if isinstance(file_paths, (str, Path)):
        path = Path(file_paths)

        if path.is_dir():
            return process_directory(path)

        return process_files([path])

    return process_files(file_paths)


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


def push_dataframe(connection, table_name: str, dataframe: pd.DataFrame) -> None:
    """Create the target table when needed, then insert one DataFrame."""
    if dataframe.empty:
        return

    _validate_identifier(table_name)
    columns = _sanitize_column_names(dataframe.columns)

    if not table_exists(connection, table_name):
        create_table(connection, table_name, dataframe)

    column_list = ", ".join(columns)
    bind_variables = ", ".join(f":{number}" for number in range(1, len(columns) + 1))
    insert_sql = f"INSERT INTO {table_name} ({column_list}) VALUES ({bind_variables})"

    clean_dataframe = dataframe.astype(object).where(pd.notna(dataframe), None)
    rows = [tuple(row) for row in clean_dataframe.itertuples(index=False, name=None)]

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


def create_table(connection, table_name: str, dataframe: pd.DataFrame) -> None:
    """Create an Oracle table using the columns and types in one DataFrame."""
    _validate_identifier(table_name)
    column_definitions = []
    column_names = _sanitize_column_names(dataframe.columns)

    for column, column_name in zip(dataframe.columns, column_names):
        oracle_type = _get_oracle_type(dataframe[column])
        column_definitions.append(f"{column_name} {oracle_type}")

    create_sql = f"CREATE TABLE {table_name} ({', '.join(column_definitions)})"

    with connection.cursor() as cursor:
        cursor.execute(create_sql)

    print(f"Created table {table_name}")


def _get_oracle_type(series: pd.Series) -> str:
    """Map a pandas column to a simple Oracle data type."""
    if pd.api.types.is_bool_dtype(series):
        return "NUMBER(1)"

    if pd.api.types.is_integer_dtype(series):
        return "NUMBER"

    if pd.api.types.is_float_dtype(series):
        return "NUMBER"

    if pd.api.types.is_datetime64_any_dtype(series):
        return "TIMESTAMP"

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
