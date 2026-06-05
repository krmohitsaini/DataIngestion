# Outlook to Oracle Ingestion Skeleton

This project downloads CSV and Excel attachments from desktop Outlook, groups
them by Oracle table name, and inserts their rows into Oracle.

When a target table already exists, rows are appended to it. When a target
table does not exist, `push_files.py` creates it from the current file before
inserting rows. The inferred Oracle column types are intentionally simple:
`NUMBER`, `NUMBER(1)`, `DATE`, `VARCHAR2`, and `CLOB`.

Each inserted row includes a `DATE_ADDED` Oracle `DATE` value showing when its
source file was pushed. Newly created tables include this audit column.
Existing tables receive the column automatically if it is missing. Source
files cannot contain a column named `DATE_ADDED`, because that name is reserved
for the ingestion timestamp.

Expected file names use the following pattern:

```text
TABLE_NAMEYYYYMMDD.csv
CUSTOMERS20260602.xlsx
CUSTOMER-ORDERS20260602.csv
```

Hyphens in file names are converted to underscores for Oracle table names. For
example, `CUSTOMER-ORDERS20260602.csv` is inserted into `CUSTOMER_ORDERS`.
Trailing and repeated underscores are cleaned up, so
`CUSTOMER_ORDERS_20260602.csv` and `CUSTOMER_-_ORDERS20260602.csv` both use
`CUSTOMER_ORDERS`.

Some files can use an additional `APP_` table prefix. Add SQL-style patterns
such as `"sample-file%"` to `APP_PREFIX_FILE_PATTERNS` in `process_files.py`.
The `%` matches the changing date, so `sample-file20260602.csv` is inserted
into `APP_SAMPLE_FILE`.

CSV and Excel headers are sanitized before Oracle tables are created or rows
are inserted. For example, `BP Account v111 (evar111)` becomes
`BP_ACCOUNT_V111_EVAR111`. Reserved or project-specific replacements can be
added to `COLUMN_NAME_REPLACEMENTS` in `push_files.py`. By default, `DATE`
becomes `EVENT_DATE`.

Add source-file date headers to `DATE_COLUMN_NAMES` in `process_files.py`.
Matching is case-insensitive and ignores surrounding spaces. Configured
columns accept Excel datetime values and these text formats:

```text
YYYY-MM-DD
YYYYMMDD
DD-MM-YYYY
DD/MM/YYYY
Month DD, YYYY
```

Each text format may also include `HH:MM` or `HH:MM:SS`. Blank values become
Oracle nulls. Invalid non-empty values stop ingestion with the file name,
column name, and invalid value in the error message.

Configured date columns use Oracle `DATE` for newly created tables. Existing
tables are not altered automatically. Manually alter or recreate older tables
that were previously created with `VARCHAR2` date columns.

`process_files.py` converts each file into a `ProcessedFile` dataclass. The
`process_files()` and `process_directory()` functions return a dictionary keyed
by target table name:

```python
{
    "CUSTOMERS": [
        ProcessedFile(
            file_path=Path("downloads/CUSTOMERS20260602.xlsx"),
            table_name="CUSTOMERS",
            file_date="20260602",
            data=<pandas DataFrame>,
        )
    ]
}
```

`push_files()` accepts a folder, one file, or a list of files:

```python
push_files("Download", oracle_user, oracle_password, oracle_dsn, "Uploaded", "Log")
push_files("Download/CUSTOMERS20260602.csv", oracle_user, oracle_password, oracle_dsn)
push_files(downloaded_files, oracle_user, oracle_password, oracle_dsn, "Uploaded", "Log")
```

When `uploaded_directory` is provided, source files move to that folder only
after all Oracle inserts commit successfully. Existing archived files are not
overwritten; a timestamp is added to duplicate file names.

Before ingestion, source file names are checked against the archive folder. If
the same file name already exists in `Uploaded`, that source file is skipped
with a message and moved into `Uploaded` using a timestamp suffix. Other files
continue processing normally.

When `log_directory` is provided, successful uploads are appended to
`Log/upload_log.txt`:

```text
2026-06-05 13:30:00 : CUSTOMERS20260602.csv -> Created table -> CUSTOMERS
2026-06-05 13:31:00 : ORDERS20260602.csv -> Appended -> ORDERS
2026-06-05 13:32:00 : CUSTOMERS20260602.csv -> Skipped
```

Before ingestion, source file names are also checked against this log. If the
same file name already exists in the log, the file is skipped, moved to
`Uploaded` when an archive folder is configured, and other files continue.

Passing a folder scans CSV and Excel files recursively, including nested
subfolders. Successfully uploaded files move into the configured archive
folder.

## Setup

Install the packages:

```bash
pip install -r requirements.txt
```

Update the Oracle settings in `main.py`, then run:

```bash
python main.py
```

`download_files.py` uses `pywin32`, so Outlook downloading requires Windows and
the desktop Outlook application. The processing and Oracle modules can be used
separately on other operating systems.
