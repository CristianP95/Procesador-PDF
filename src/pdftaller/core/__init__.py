"""Núcleo de PDF Taller: funciones puras sobre archivos, sin dependencia de la GUI.

Pensado para usarse igual desde la interfaz gráfica (V1) y desde scripts (V2).
Las páginas en parámetros de texto (``"1-3,5"``) son base 1; en listas de enteros son base 0.
"""
from .errors import PageRangeError, PasswordError, PdfTallerError
from .organize import delete_pages, extract_pages, merge, page_count, reorder, rotate_pages, split
from .pages import parse_page_ranges, parse_range_groups
from .convert import IMAGE_EXTENSIONS, images_to_pdf
from .edit import insert_images, insert_signature
from .optimize import (COMPRESS_LEVELS, OcrReport, RepairReport, SizeAnalysis, SizeReport, analyze, compress,
                       estimate_compression, find_tessdata, ocr, ocr_languages, repair)
from .integrity import VerifyResult, certificate_path, certify, file_hash, verify
from .security import (CompareResult, PageDiff, compare, find_text, find_text_labeled, generate_password,
                       is_encrypted, permissions, protect, redact, unlock)
from .signing import (DEFAULT_TSA, SignatureStatus, check_password_strength, create_certificate,
                      export_public_certificate, sign, signer_certificate, trust_certificate, trust_dir,
                      trusted_certificates, untrust_certificate, verify_signatures)

__all__ = [
    "PdfTallerError", "PasswordError", "PageRangeError",
    "merge", "split", "extract_pages", "reorder", "delete_pages", "rotate_pages", "page_count",
    "parse_page_ranges", "parse_range_groups",
    "protect", "unlock", "is_encrypted", "generate_password", "permissions",
    "compare", "CompareResult", "PageDiff", "find_text", "find_text_labeled", "redact",
    "images_to_pdf", "IMAGE_EXTENSIONS", "insert_images", "insert_signature",
    "compress", "estimate_compression", "analyze", "repair", "ocr", "find_tessdata", "ocr_languages",
    "COMPRESS_LEVELS", "SizeReport", "SizeAnalysis", "RepairReport", "OcrReport",
    "create_certificate", "check_password_strength", "sign", "verify_signatures", "SignatureStatus",
    "export_public_certificate", "trust_certificate", "untrust_certificate", "trusted_certificates",
    "trust_dir", "signer_certificate", "DEFAULT_TSA",
    "file_hash", "certify", "verify", "certificate_path", "VerifyResult",
]
