"""Bounded in-memory document decoding; no receipts are written to disk."""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import warnings

from PIL import Image, ImageOps

from .schema import ReceiptError

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PAGES = 12
MAX_IMAGE_PIXELS = 30_000_000
MAX_SIDE = 2200


@dataclass(frozen=True)
class Document:
    name: str
    fingerprint: str
    pages: tuple[bytes, ...]


def image_bytes(image: Image.Image) -> bytes:
    image = ImageOps.exif_transpose(image)
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    # Composite transparent scans on white rather than black.
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, "white")
    background.alpha_composite(rgba)
    buffer = BytesIO()
    background.convert("RGB").save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def prepare_document(name: str, content: bytes) -> Document:
    if not content or len(content) > MAX_FILE_BYTES:
        raise ReceiptError("Use a non-empty file no larger than 20 MB.")
    suffix = Path(name).suffix.lower()
    pages = []
    try:
        if suffix == ".pdf":
            try:
                import fitz
            except ImportError as exc:
                raise ReceiptError("PDF support could not load. Check the PyMuPDF installation; image uploads remain available.") from exc
            with fitz.open(stream=content, filetype="pdf") as pdf:
                if pdf.needs_pass:
                    raise ReceiptError("This PDF is password-protected. Upload an unlocked copy.")
                if not 1 <= len(pdf) <= MAX_PAGES:
                    raise ReceiptError(f"PDFs must contain 1–{MAX_PAGES} pages. Split larger invoices.")
                for page in pdf:
                    longest = max(page.rect.width, page.rect.height)
                    if longest <= 0:
                        raise ReceiptError("A PDF page has invalid dimensions.")
                    scale = min(2, MAX_SIDE / longest)
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
                    with Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples) as img:
                        pages.append(image_bytes(img))
        elif suffix in (".png", ".jpg", ".jpeg"):
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as img:
                    if img.format not in ("PNG", "JPEG"):
                        raise ReceiptError("Image contents must be PNG or JPEG.")
                    if img.width * img.height > MAX_IMAGE_PIXELS:
                        raise ReceiptError("Image exceeds 30 megapixels. Resize it before uploading.")
                    pages.append(image_bytes(img))
        else:
            raise ReceiptError("Supported files: PNG, JPG, JPEG and PDF.")
    except ReceiptError:
        raise
    except Exception as exc:
        raise ReceiptError("Cannot decode this document. It may be damaged or unsupported.") from exc
    return Document(Path(name).name, sha256(content).hexdigest(), tuple(pages))
