"""Firma digital con certificado (PAdES) y su verificación, usando pyHanko.

A diferencia de pegar una imagen, la firma digital sella criptográficamente el documento:
cualquier cambio posterior se detecta al verificarla (en PDF Taller, Adobe Reader, etc.).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from ._io import PathLike
from .errors import PasswordError, PdfTallerError


def create_certificate(output: PathLike, name: str, password: str, *, email: str | None = None,
                       organization: str | None = None, days: int = 1825) -> Path:
    """Crea un certificado personal autofirmado (.p12) para firmar documentos.

    Sirve para firmas internas (equipo, universidad). Para validez legal se usa un certificado
    emitido por una entidad certificadora; ``sign`` acepta ambos.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    if not name.strip():
        raise PdfTallerError("Indique el nombre del firmante")
    if len(password) < 4:
        raise PdfTallerError("La contraseña del certificado debe tener al menos 4 caracteres")
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, name.strip())]
    if organization:
        attrs.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization))
    if email:
        attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, email))
    subject = x509.Name(attrs)
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject).issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                     data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                     crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False)
        .sign(key, hashes.SHA256())
    )
    data = pkcs12.serialize_key_and_certificates(
        name.encode(), key, cert, None, serialization.BestAvailableEncryption(password.encode()))
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out


def _load_signer(p12: PathLike, password: str):
    from pyhanko.sign import signers
    try:
        signer = signers.SimpleSigner.load_pkcs12(str(p12), passphrase=password.encode() if password else None)
    except Exception as exc:
        raise PasswordError(f"No se pudo abrir el certificado: {exc}") from exc
    if signer is None:
        raise PasswordError("Contraseña del certificado incorrecta")
    return signer


def sign(
    input: PathLike,
    output: PathLike,
    p12: PathLike,
    p12_password: str,
    *,
    reason: str = "",
    location: str = "",
    page: int | None = None,
    rect: tuple[float, float, float, float] | None = None,
    lock: bool = True,
) -> Path:
    """Firma digitalmente el PDF con el certificado ``p12``.

    - ``page``/``rect`` (base 0, coordenadas PyMuPDF): recuadro visible con el nombre y la fecha.
      Sin ellos la firma es invisible (se ve en el panel de firmas del lector).
    - ``lock=True`` certifica el documento sin permitir cambios posteriores (DocMDP).

    La firma debe ser el último paso: cualquier edición posterior la invalida.
    """
    import pymupdf
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers
    from pyhanko.stamp import TextStampStyle

    src = Path(input)
    with pymupdf.open(src) as d:
        if d.needs_pass or d.metadata.get("encryption"):
            raise PdfTallerError("Quite la protección con contraseña antes de firmar. "
                                 "La firma digital debe ser el último paso.")
        height = d[page].rect.height if page is not None else 0
        page_count = d.page_count
    signer = _load_signer(p12, p12_password)
    field_name = f"Firma_{dt.datetime.now():%Y%m%d_%H%M%S}"
    meta = signers.PdfSignatureMetadata(
        field_name=field_name, reason=reason or None, location=location or None,
        certify=lock, docmdp_permissions=fields.MDPPerm.NO_CHANGES if lock else fields.MDPPerm.FILL_FORMS,
        subfilter=fields.SigSeedSubFilter.PADES,
    )
    out = Path(output)
    data = src.read_bytes()
    import io
    w = IncrementalPdfFileWriter(io.BytesIO(data), strict=False)
    style = None
    if page is not None and rect is not None:
        if not 0 <= page < page_count:
            raise PdfTallerError(f"La página {page + 1} no existe")
        x0, y0, x1, y1 = rect
        box = (int(x0), int(height - y1), int(x1), int(height - y0))  # PDF: origen abajo a la izquierda
        fields.append_signature_field(w, fields.SigFieldSpec(field_name, on_page=page, box=box))
        style = TextStampStyle(stamp_text="Firmado digitalmente por:\n%(signer)s\n%(ts)s")
    pdf_signer = signers.PdfSigner(meta, signer=signer, stamp_style=style)
    buf = io.BytesIO()
    pdf_signer.sign_pdf(w, output=buf)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(buf.getvalue())
    return out


@dataclass
class SignatureStatus:
    field: str
    signer: str
    signed_at: str
    intact: bool           # el contenido firmado no cambió
    covers_all: bool       # no hay cambios después de la firma
    trusted: bool          # el certificado está en la lista de confianza
    summary: str


def verify_signatures(path: PathLike, trusted_certs: list[PathLike] | None = None) -> list[SignatureStatus]:
    """Verifica todas las firmas digitales del PDF."""
    from pyhanko.keys import load_cert_from_pemder
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko.sign.validation.status import SignatureCoverageLevel
    from pyhanko_certvalidator import ValidationContext

    import logging
    logging.getLogger("pyhanko").setLevel(logging.CRITICAL)  # los avisos de certificado propio se informan abajo
    logging.getLogger("pyhanko_certvalidator").setLevel(logging.CRITICAL)
    roots = [load_cert_from_pemder(str(c)) for c in (trusted_certs or [])]
    vc = ValidationContext(trust_roots=roots, allow_fetching=False)
    result = []
    with open(path, "rb") as f:
        reader = PdfFileReader(f, strict=False)
        for sig in reader.embedded_signatures:
            st = validate_pdf_signature(sig, vc, skip_diff=False)
            covers = st.coverage == SignatureCoverageLevel.ENTIRE_FILE
            signer = st.signing_cert.subject.human_friendly if st.signing_cert else "?"
            signer = signer.replace("Common Name: ", "").replace("Organization: ", "")
            when = st.signer_reported_dt.isoformat(timespec="seconds") if st.signer_reported_dt else ""
            ok = st.intact and st.valid
            if ok and covers:
                msg = "✔ Firma válida: el documento no ha cambiado desde que se firmó."
            elif ok:
                msg = "⚠ La firma es válida, pero el documento tuvo cambios DESPUÉS de firmarse."
            else:
                msg = "✘ Firma INVÁLIDA: el contenido firmado fue alterado."
            if ok and not st.trusted:
                msg += " (Certificado no registrado como de confianza: confirme que es de quien dice ser.)"
            result.append(SignatureStatus(sig.field_name, signer, when, bool(ok), covers, bool(st.trusted), msg))
    return result
