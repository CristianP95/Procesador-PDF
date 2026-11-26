class ProcesadorPdfError(Exception):
    """Error base de Procesador PDF."""


class PasswordError(ProcesadorPdfError):
    """La contraseña falta o es incorrecta."""


class PageRangeError(ProcesadorPdfError, ValueError):
    """El rango de páginas no es válido."""


# Nombre anterior (versiones 0.1 a 0.5), se mantiene por compatibilidad.
PdfTallerError = ProcesadorPdfError
