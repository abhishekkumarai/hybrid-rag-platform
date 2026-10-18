"""Turns non-PDF sources (IRA-67) into a PDF so the rest of the pipeline stays PDF-only.

Probe, parsers, bbox citations, /preview and /raw all assume a PDF. Rather than teach each of them
about slides or images, a source is converted once, up front, and the converted PDF is what gets
parsed, previewed and served. Conversions live in `data/converted/<doc_id>.pdf` — deliberately not
beside the original, because the directory scan would otherwise ingest the conversion as a new file.
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import fitz

from services.common.config import load_config
from services.common.logger import get_logger

logger = get_logger("ingestion.normalize")

CONVERTED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "converted"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
TEXT_EXTENSIONS = {".txt", ".md"}
SLIDE_EXTENSIONS = {".pptx"}
NATIVE_EXTENSIONS = {".pdf"}
CONVERTIBLE_EXTENSIONS = IMAGE_EXTENSIONS | TEXT_EXTENSIONS | SLIDE_EXTENSIONS
SUPPORTED_EXTENSIONS = NATIVE_EXTENSIONS | CONVERTIBLE_EXTENSIONS

_SOFFICE_FALLBACKS = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)


class ConversionError(RuntimeError):
    """The source could not be turned into a PDF."""


def converted_path(doc_id: str) -> Path:
    return CONVERTED_DIR / f"{doc_id}.pdf"


def is_supported(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS


def to_pdf(path: Path, doc_id: str) -> Path:
    """The PDF to parse for `path`: the file itself for a PDF, else a (cached) conversion."""
    suffix = path.suffix.lower()
    if suffix in NATIVE_EXTENSIONS:
        return path
    if suffix not in CONVERTIBLE_EXTENSIONS:
        raise ConversionError(f"Unsupported file type '{suffix or path.name}'")

    target = converted_path(doc_id)
    if target.is_file() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)

    if suffix in IMAGE_EXTENSIONS:
        _image_to_pdf(path, target)
    elif suffix in TEXT_EXTENSIONS:
        _text_to_pdf(path, target, markdown=suffix == ".md")
    else:
        _slides_to_pdf(path, target)
    logger.info(f"Converted '{path.name}' -> '{target.name}'")
    return target


def _image_to_pdf(src: Path, target: Path) -> None:
    try:
        with fitz.open(str(src)) as img:
            data = img.convert_to_pdf()
        with fitz.open("pdf", data) as pdf:
            pdf.save(str(target))
    except Exception as exc:
        raise ConversionError(f"Could not read image '{src.name}': {exc}") from exc


def _markdown_to_html(text: str) -> str:
    """Minimal markdown -> HTML (headings, bullets, paragraphs): enough for PyMuPDF's Story layout
    to give headings a larger font, which the layout parser then detects."""
    out: list[str] = []
    para: list[str] = []
    in_list = False

    def flush_para() -> None:
        if para:
            out.append(f"<p>{html.escape(' '.join(para))}</p>")
            para.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        bullet = re.match(r"^\s*[-*+]\s+(.*)$", line)
        if in_list and not bullet:
            out.append("</ul>")
            in_list = False
        if heading:
            flush_para()
            level = len(heading.group(1))
            out.append(f"<h{level}>{html.escape(heading.group(2))}</h{level}>")
        elif bullet:
            flush_para()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{html.escape(bullet.group(1))}</li>")
        elif not line.strip():
            flush_para()
        else:
            para.append(line.strip())
    flush_para()
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _text_to_pdf(src: Path, target: Path, markdown: bool) -> None:
    try:
        text = src.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ConversionError(f"Could not read '{src.name}': {exc}") from exc
    if not text.strip():
        raise ConversionError(f"'{src.name}' is empty")

    if markdown:
        body = _markdown_to_html(text)
    else:
        body = "".join(
            f"<p>{html.escape(' '.join(p.split()))}</p>"
            for p in re.split(r"\n\s*\n", text) if p.strip()
        )
    css = "body{font-family:sans-serif;font-size:11pt} h1{font-size:20pt} h2{font-size:16pt} h3{font-size:13pt}"
    page_rect = fitz.paper_rect("a4")
    content_rect = page_rect + (54, 54, -54, -54)

    story = fitz.Story(html=body, user_css=css)
    writer = fitz.DocumentWriter(str(target))
    more = True
    while more:
        device = writer.begin_page(page_rect)
        more, _ = story.place(content_rect)
        story.draw(device)
        writer.end_page()
    writer.close()


def _find_soffice() -> str | None:
    configured = load_config().ingestion.soffice_path
    for candidate in (configured, shutil.which("soffice"), shutil.which("libreoffice"), *_SOFFICE_FALLBACKS):
        if candidate and Path(candidate).is_file():
            return str(candidate)
        if candidate and shutil.which(candidate):
            return shutil.which(candidate)
    return None


def _is_pptx_package(src: Path) -> bool:
    try:
        with zipfile.ZipFile(src) as pkg:
            return "[Content_Types].xml" in pkg.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def _slides_to_pdf(src: Path, target: Path) -> None:
    soffice = _find_soffice()
    if soffice is None:
        raise ConversionError(
            "PowerPoint conversion needs LibreOffice; install it or set ingestion.soffice_path / SOFFICE_PATH"
        )
    # Some LibreOffice builds open an unrecognised file as plain text and "convert" it, which would index
    # the raw bytes of a corrupt deck as if they were slide content. A .pptx is an OOXML zip, so check.
    if not _is_pptx_package(src):
        raise ConversionError(f"'{src.name}' is not a valid PowerPoint file")
    timeout = load_config().ingestion.convert_timeout_s
    # ignore_cleanup_errors: on Windows soffice.bin can still hold profile files when we clean up, and
    # that PermissionError would otherwise replace the real conversion error.
    with (
        tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as out_dir,
        tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile_dir,
    ):
        # A private user profile lets conversions run concurrently without LibreOffice's profile lock.
        cmd = [
            soffice, f"-env:UserInstallation={Path(profile_dir).as_uri()}",
            "--headless", "--convert-to", "pdf", "--outdir", out_dir, str(src),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise ConversionError(f"Converting '{src.name}' timed out after {timeout:.0f}s") from exc
        produced = Path(out_dir) / f"{src.stem}.pdf"
        if proc.returncode != 0 or not produced.is_file():
            raise ConversionError(
                f"LibreOffice could not convert '{src.name}': {(proc.stderr or proc.stdout).strip()[:300]}"
            )
        shutil.move(str(produced), str(target))
