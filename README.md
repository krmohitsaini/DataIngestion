# Outlook to Oracle Ingestion Skeleton

This project downloads CSV and Excel attachments from desktop Outlook, groups
them by Oracle table name, and inserts their rows into Oracle.

When a target table already exists, rows are appended to it. When a target
table does not exist, `push_files.py` creates it from the current file before
inserting rows. The inferred Oracle column types are intentionally simple:
`NUMBER`, `NUMBER(1)`, `TIMESTAMP`, `VARCHAR2`, and `CLOB`.

Expected file names use the following pattern:

```text
TABLE_NAMEYYYYMMDD.csv
CUSTOMERS20260602.xlsx
CUSTOMER-ORDERS20260602.csv
```

Hyphens in file names are converted to underscores for Oracle table names. For
example, `CUSTOMER-ORDERS20260602.csv` is inserted into `CUSTOMER_ORDERS`.

Some files can use an additional `APP_` table prefix. Add SQL-style patterns
such as `"sample-file%"` to `APP_PREFIX_FILE_PATTERNS` in `process_files.py`.
The `%` matches the changing date, so `sample-file20260602.csv` is inserted
into `APP_SAMPLE_FILE`.

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
push_files("downloads", oracle_user, oracle_password, oracle_dsn)
push_files("downloads/CUSTOMERS20260602.csv", oracle_user, oracle_password, oracle_dsn)
push_files(downloaded_files, oracle_user, oracle_password, oracle_dsn)
```

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
