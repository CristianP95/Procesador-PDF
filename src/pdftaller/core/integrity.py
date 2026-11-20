"""Integridad: certificar un documento con su huella SHA-256 y verificarlo después.

La huella (hash) cambia si se modifica un solo byte del archivo. Se guarda en un
archivo aparte ``<documento>.pdf.sha256.json`` para no alterar el PDF certificado.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ._io import PathLike
from .errors import PdfTallerError

SUFFIX = ".sha256.json"


def file_hash(path: PathLike, algorithm: str = "sha256") -> str:
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def certificate_path(path: PathLike) -> Path:
    p = Path(path)
    return p.with_name(p.name + SUFFIX)


def certify(path: PathLike, author: str | None = None, note: str | None = None,
            output: PathLike | None = None) -> Path:
    """Calcula la huella del PDF y la guarda en un certificado JSON. Devuelve su ruta."""
    p = Path(path)
    data = {
        "archivo": p.name,
        "algoritmo": "sha256",
        "huella": file_hash(p),
        "tamano_bytes": p.stat().st_size,
        "fecha_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "autor": author or "",
        "nota": note or "",
        "herramienta": "PDF Taller",
    }
    out = Path(output) if output else certificate_path(p)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


@dataclass
class VerifyResult:
    ok: bool
    expected: str
    actual: str
    certificate: dict

    def message(self) -> str:
        if self.ok:
            return (f"✔ El documento es ÍNTEGRO: coincide con el certificado del "
                    f"{self.certificate.get('fecha_utc', '?')}.")
        return ("✘ El documento FUE MODIFICADO: su huella no coincide con el certificado.\n"
                f"Esperada: {self.expected}\nActual:   {self.actual}")


def verify(path: PathLike, certificate: PathLike | None = None, expected_hash: str | None = None) -> VerifyResult:
    """Compara la huella actual con un certificado JSON o con una huella escrita a mano."""
    cert: dict = {}
    if expected_hash is None:
        cpath = Path(certificate) if certificate else certificate_path(path)
        if not cpath.exists():
            raise PdfTallerError(f"No se encontró el certificado '{cpath.name}'")
        try:
            cert = json.loads(cpath.read_text(encoding="utf-8"))
            expected_hash = cert["huella"]
        except (ValueError, KeyError) as exc:
            raise PdfTallerError(f"Certificado no válido: {exc}") from exc
    expected = expected_hash.strip().lower()
    actual = file_hash(path, cert.get("algoritmo", "sha256"))
    return VerifyResult(actual == expected, expected, actual, cert)
