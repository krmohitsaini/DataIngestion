from __future__ import annotations

from pathlib import Path


ALLOWED_EXTENSIONS = {".csv", ".xls", ".xlsx"}


def download_attachments(
    download_directory: str | Path,
    subject_contains: str | None = None,
    only_unread: bool = True,
    mark_as_read: bool = True,
) -> list[Path]:
    """Download CSV and Excel attachments from the Outlook inbox."""
    try:
        import win32com.client
    except ImportError as error:
        raise RuntimeError(
            "Outlook download requires pywin32 and desktop Outlook on Windows."
        ) from error

    download_path = Path(download_directory)
    download_path.mkdir(parents=True, exist_ok=True)

    outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    inbox = outlook.GetDefaultFolder(6)
    downloaded_files = []

    for message in inbox.Items:
        if only_unread and not message.UnRead:
            continue

        if subject_contains and subject_contains.lower() not in message.Subject.lower():
            continue

        message_downloaded_files = _download_message_attachments(message, download_path)
        downloaded_files.extend(message_downloaded_files)

        if message_downloaded_files and mark_as_read:
            message.UnRead = False
            message.Save()

    return downloaded_files


def _download_message_attachments(message, download_directory: Path) -> list[Path]:
    downloaded_files = []

    for attachment_number in range(1, message.Attachments.Count + 1):
        attachment = message.Attachments.Item(attachment_number)
        file_path = download_directory / attachment.FileName

        if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue

        attachment.SaveAsFile(str(file_path))
        downloaded_files.append(file_path)

    return downloaded_files
