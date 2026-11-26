"""Procesador PDF: herramientas PDF de código abierto.

El paquete ``procesador_pdf.core`` contiene toda la lógica y no depende de la GUI,
así la versión 2 (automatización por scripts) reutiliza exactamente el mismo código::

    from procesador_pdf import core
    core.merge(["a.pdf", "b.pdf"], "unido.pdf")
"""

__version__ = "0.6.0"
