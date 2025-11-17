# utils/file_validation.py
import zipfile
from pathlib import Path

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from PIL import Image
import magic  # python-magic

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ZIP_EXTS = {".zip"}

ALLOWED_EXTENSIONS = IMAGE_EXTS | ZIP_EXTS

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/zip",
    "application/x-zip-compressed",
}


def validate_uploaded_file(uploaded_file):
    # 1) Size
    if uploaded_file.size > MAX_FILE_SIZE:
        raise ValidationError(_("File too large (max 20MB)."))

    # 2) Extension
    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(_("Unsupported file extension."))

    # 3) Server-side MIME detection
    # Read a small chunk for magic
    sample = uploaded_file.read(4096)
    uploaded_file.seek(0)
    mime = magic.from_buffer(sample, mime=True)

    if mime not in ALLOWED_MIME_TYPES:
        raise ValidationError(_("Unsupported file type."))

    # 4) Extra validation per type
    if ext in IMAGE_EXTS:
        # verify it is a real image
        try:
            img = Image.open(uploaded_file)
            img.verify()
        except Exception:
            uploaded_file.seek(0)
            raise ValidationError(_("Uploaded file is not a valid image."))
        uploaded_file.seek(0)

    elif ext in ZIP_EXTS:
        # verify it is a real zip archive
        try:
            # Temporarily save in memory file location
            # Django's UploadedFile has a file-like obj
            if not zipfile.is_zipfile(uploaded_file):
                raise ValidationError(_("Uploaded file is not a valid ZIP archive."))
        except Exception:
            uploaded_file.seek(0)
            raise ValidationError(_("Uploaded file is not a valid ZIP archive."))
        uploaded_file.seek(0)


def challenge_file_upload_path(instance, filename):
    """
    Upload path: challenges/<challenge_id>/<filename>
    """

    return (
        f"challenges/{instance.challenge.id}/{filename}"
    )
