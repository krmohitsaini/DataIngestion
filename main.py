from pathlib import Path

from download_files import download_attachments
from push_files import push_files


DOWNLOAD_DIRECTORY = Path("downloads")
OUTLOOK_SUBJECT_FILTER = None

ORACLE_USER = "your_username"
ORACLE_PASSWORD = "your_password"
ORACLE_DSN = "hostname:1521/service_name"
downloaded_files = "Downloaded"
uploaded_files = "Uploaded"
log_files = "Log"

def main() -> None:
    """
    # Currently testing out with local files
    downloaded_files = download_attachments(
        download_directory=DOWNLOAD_DIRECTORY,
        subject_contains=OUTLOOK_SUBJECT_FILTER,
    )
    print(f"Downloaded {len(downloaded_files)} files")
    """

    push_files(
        file_paths=downloaded_files,
        oracle_user=ORACLE_USER,
        oracle_password=ORACLE_PASSWORD,
        oracle_dsn=ORACLE_DSN,
        uploaded_directory=uploaded_files,
        log_directory=log_files,
    )


if __name__ == "__main__":
    main()
