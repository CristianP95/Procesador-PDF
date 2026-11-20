class PdfTallerError(Exception):
    """Error base de PDF Taller."""


class PasswordError(PdfTallerError):
    """La contraseña falta o es incorrecta."""


class PageRangeError(PdfTallerError, ValueError):
    """El rango de páginas no es válido."""
