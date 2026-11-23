"""PDF Taller: herramientas PDF de código abierto.

El paquete ``pdftaller.core`` contiene toda la lógica y no depende de la GUI,
así la versión 2 (automatización por scripts) reutiliza exactamente el mismo código::

    from pdftaller import core
    core.merge(["a.pdf", "b.pdf"], "unido.pdf")
"""

__version__ = "0.5.0"
