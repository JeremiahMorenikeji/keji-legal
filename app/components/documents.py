"""Turn an uploaded PDF / Word / text file into plain text. No Streamlit in here, so it is easy to test."""
import hashlib
import io
import re
import zipfile
from pathlib import Path

ALLOWED_TYPES = ["pdf", "docx", "txt", "md"]
MAX_UPLOAD_MB = 10
MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_CHARS = 40000            # what the API accepts
MAX_PDF_PAGES = 200
MAX_ZIP_UNPACKED = 100 * 1024 * 1024   # guards against "zip bomb" Word files


class DocumentError(Exception):
    """The message is always safe and helpful to show to the user."""


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pdf(data: bytes):
    from pypdf import PdfReader

    if not data.startswith(b"%PDF"):
        raise DocumentError("This file is not a valid PDF.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise DocumentError("This PDF is password-protected. Remove the password and upload it again.")
        total = len(reader.pages)
        text = "\n\n".join((reader.pages[i].extract_text() or "") for i in range(min(total, MAX_PDF_PAGES)))
    except DocumentError:
        raise
    except Exception as e:  # damaged file, unsupported encryption, ...
        raise DocumentError("This PDF could not be read (it may be damaged or use unsupported encryption).") from e
    warnings = [f"Only the first {MAX_PDF_PAGES} of {total} pages were read."] if total > MAX_PDF_PAGES else []
    return text, warnings


def _docx(data: bytes):
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise DocumentError("This file is not a valid Word (.docx) document.")
    with zf:
        if "word/document.xml" not in zf.namelist():
            raise DocumentError("This does not look like a Word (.docx) document.")
        if sum(i.file_size for i in zf.infolist()) > MAX_ZIP_UNPACKED:
            raise DocumentError("This document is too large when unpacked.")
    try:
        d = docx.Document(io.BytesIO(data))
        parts = []
        for child in d.element.body.iterchildren():      # keeps paragraphs and tables in reading order
            if child.tag.endswith("}p"):
                parts.append(Paragraph(child, d).text)
            elif child.tag.endswith("}tbl"):
                for row in Table(child, d).rows:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
    except Exception as e:
        raise DocumentError("This Word document could not be read (it may be damaged).") from e
    return "\n".join(parts), []


def _txt(data: bytes):
    if b"\x00" in data[:4000]:
        raise DocumentError("This file does not look like text.")
    try:
        return data.decode("utf-8-sig"), []
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace"), []


def extract_text(name: str, data: bytes):
    """Returns (text, warnings). Raises DocumentError with a friendly message."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if not data:
        raise DocumentError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise DocumentError(f"The file is larger than {MAX_UPLOAD_MB} MB.")
    if ext == "pdf":
        text, warnings = _pdf(data)
    elif ext == "docx":
        text, warnings = _docx(data)
    elif ext in ("txt", "md"):
        text, warnings = _txt(data)
    elif ext == "doc":
        raise DocumentError("Old Word (.doc) files are not supported. Open it in Word, save as .docx, and upload that.")
    else:
        raise DocumentError("Unsupported file type. Upload a PDF, Word (.docx) or text (.txt, .md) file.")
    text = _clean(text)
    if len(text) < 20:
        raise DocumentError("No readable text was found. If this is a scanned document (an image), it needs OCR "
                            "first - that is not supported yet.")
    if len(text) > MAX_CHARS:
        warnings.append(f"The document is long, so only the first {MAX_CHARS:,} of its {len(text):,} characters are used.")
        text = text[:MAX_CHARS]
    return text, warnings


def safe_name(name: str) -> str:
    return re.sub(r"[^\w .()\-]", "_", Path(name.replace("\\", "/")).name)[:120] or "document"


def ingest_upload(name: str, data: bytes, current):
    """Returns (doc, error). Re-uploading the same bytes returns the current doc without re-reading it."""
    digest = hashlib.sha256(data).hexdigest()
    if current and current.get("hash") == digest:
        return current, None
    try:
        text, warnings = extract_text(name, data)
    except DocumentError as e:
        return None, str(e)
    return {"name": safe_name(name), "text": text, "hash": digest, "warnings": warnings}, None
