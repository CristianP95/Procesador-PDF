"""Ejemplo de la V2: el mismo núcleo que usa la GUI, llamado desde un script.

Uso:  python ejemplos/automatizar.py carpeta_con_pdfs
Une todos los PDF de la carpeta, censura números de cédula y protege el resultado.
"""
import sys
from pathlib import Path

from pdftaller import core

carpeta = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
pdfs = sorted(p for p in carpeta.glob("*.pdf") if not p.name.startswith("_"))
if not pdfs:
    sys.exit("No hay PDF en la carpeta")

unido = core.merge(pdfs, carpeta / "_unido.pdf")
censurado, n = core.redact(unido, carpeta / "_censurado.pdf", [r"\b\d{6,10}\b"], regex=True)
final = core.protect(censurado, carpeta / "_final.pdf", user_password="cambiar-esta-clave")
print(f"{len(pdfs)} archivos unidos, {n} datos censurados → {final}")
