"""Firma digital con certificado (PAdES) y su verificación, usando pyHanko.

A diferencia de pegar una imagen, la firma digital sella criptográficamente el documento:
cualquier cambio posterior se detecta al verificarla (en PDF Taller, Adobe Reader, etc.).

Medidas de seguridad (v0.4):

- Llave RSA de 3072 bits, resumen SHA-256 y formato PAdES.
- Contraseña robusta obligatoria para los certificados nuevos (protege la llave privada).
- Sello de tiempo opcional de un tercero (RFC 3161): prueba la fecha aunque el reloj del PC mienta.
- Lista de certificados de confianza: compare la huella SHA-256 con el firmante una vez y
  desde entonces sus firmas se ven como verificadas (y las de un impostor, no).
- Autoverificación: tras firmar se valida el resultado antes de guardarlo.
- Bloqueo (certificación DocMDP): cualquier cambio posterior se informa como violación.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import os
from dataclasses import dataclass, field as dc_field
from pathlib import Path

from ._io import PathLike
from .errors import PasswordError, PdfTallerError

DEFAULT_TSA = "http://timestamp.digicert.com"


# ---------------------------------------------------------------- certificados

def check_password_strength(password: str) -> None:
    """La llave privada del certificado se protege con esta contraseña: se exige que sea robusta."""
    problems = []
    if len(password) < 8:
        problems.append("tener al menos 8 caracteres")
    kinds = sum([any(c.islower() for c in password), any(c.isupper() for c in password),
                 any(c.isdigit() for c in password), any(not c.isalnum() for c in password)])
    if kinds < 3:
        problems.append("combinar al menos 3 de: minúsculas, mayúsculas, números y símbolos")
    if problems:
        raise PdfTallerError("Contraseña del certificado débil: debe " + " y ".join(problems) + ".")


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
    check_password_strength(password)
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
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    data = pkcs12.serialize_key_and_certificates(
        name.encode(), key, cert, None, serialization.BestAvailableEncryption(password.encode()))
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out


def _fingerprint(der: bytes) -> str:
    h = hashlib.sha256(der).hexdigest().upper()
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2))


def _load_x509(data: bytes):
    from cryptography import x509
    try:
        return x509.load_der_x509_certificate(data)
    except ValueError:
        return x509.load_pem_x509_certificate(data)


def export_public_certificate(p12: PathLike, password: str, output: PathLike) -> tuple[Path, str]:
    """Exporta el certificado PÚBLICO de un .p12 a un .cer (sin la llave privada) para compartirlo.

    Quien lo reciba puede marcarlo como de confianza y así sus firmas se verán como verificadas.
    Devuelve ``(ruta, huella_sha256)``.
    """
    from cryptography.hazmat.primitives.serialization import Encoding, pkcs12
    try:
        _, cert, _ = pkcs12.load_key_and_certificates(Path(p12).read_bytes(),
                                                      password.encode() if password else None)
    except Exception as exc:
        raise PasswordError(f"No se pudo abrir el certificado: {exc}") from exc
    if cert is None:
        raise PdfTallerError("El archivo no contiene un certificado")
    der = cert.public_bytes(Encoding.DER)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(der)
    return out, _fingerprint(der)


# ---------------------------------------------------------------- lista de confianza

def trust_dir() -> Path:
    """Carpeta con los certificados públicos que el usuario marcó como de confianza.

    Windows: ``%APPDATA%\\PDFTaller\\confianza``. Se puede cambiar con ``PDFTALLER_TRUST_DIR``.
    """
    base = os.environ.get("PDFTALLER_TRUST_DIR")
    if base:
        d = Path(base)
    elif os.name == "nt":
        d = Path(os.environ.get("APPDATA", str(Path.home()))) / "PDFTaller" / "confianza"
    else:
        d = Path.home() / ".config" / "pdftaller" / "confianza"
    d.mkdir(parents=True, exist_ok=True)
    return d


def trusted_certificates() -> list[Path]:
    return sorted(p for p in trust_dir().glob("*") if p.suffix.lower() in (".cer", ".crt", ".pem", ".der"))


def trust_certificate(cert: PathLike | bytes, name: str | None = None) -> Path:
    """Agrega un certificado público (.cer/.pem o bytes DER) a la lista de confianza."""
    from cryptography.hazmat.primitives.serialization import Encoding
    c = _load_x509(cert if isinstance(cert, bytes) else Path(cert).read_bytes())
    der = c.public_bytes(Encoding.DER)
    fp = _fingerprint(der).replace(":", "")[:16]
    label = name or c.subject.rfc4514_string()
    safe = "".join(ch for ch in label if ch.isalnum() or ch in " -_")[:40].strip()
    out = trust_dir() / f"{safe or 'certificado'}_{fp}.cer"
    out.write_bytes(der)
    return out


def untrust_certificate(fingerprint: str) -> bool:
    """Quita de la lista de confianza el certificado con esa huella SHA-256."""
    from cryptography.hazmat.primitives.serialization import Encoding
    target = fingerprint.replace(":", "").upper()
    for p in trusted_certificates():
        try:
            der = _load_x509(p.read_bytes()).public_bytes(Encoding.DER)
        except Exception:
            continue
        if _fingerprint(der).replace(":", "") == target:
            p.unlink()
            return True
    return False


# ---------------------------------------------------------------- firmar

def _load_signer(p12: PathLike, password: str):
    from pyhanko.sign import signers
    try:
        signer = signers.SimpleSigner.load_pkcs12(str(p12), passphrase=password.encode() if password else None)
    except Exception as exc:
        raise PasswordError(f"No se pudo abrir el certificado: {exc}") from exc
    if signer is None:
        raise PasswordError("Contraseña del certificado incorrecta")
    na = signer.signing_cert["tbs_certificate"]["validity"]["not_after"].native
    if na < dt.datetime.now(dt.timezone.utc):
        raise PdfTallerError(f"El certificado venció el {na.date().isoformat()}: no se puede firmar con él")
    return signer


def sign(
    input: PathLike,
    output: PathLike,
    p12: PathLike,
    p12_password: str,
    *,
    reason: str = "",
    location: str = "",
    contact: str = "",
    page: int | None = None,
    rect: tuple[float, float, float, float] | None = None,
    lock: bool = True,
    signature_image: PathLike | None = None,
    timestamp_url: str | None = None,
    timestamper=None,
) -> Path:
    """Firma digitalmente el PDF con el certificado ``p12`` (PAdES, SHA-256).

    - ``page``/``rect`` (base 0, coordenadas PyMuPDF): recuadro visible con el nombre y la fecha.
      Sin ellos la firma es invisible (se ve en el panel de firmas del lector).
    - ``signature_image``: imagen de la firma manuscrita, se dibuja en la parte superior del recuadro.
    - ``lock=True`` certifica el documento sin permitir cambios posteriores (DocMDP).
    - ``timestamp_url``: servidor de sellado de tiempo RFC 3161 (p. ej. :data:`DEFAULT_TSA`).
      Necesita internet. ``timestamper``: objeto de pyHanko ya configurado (alternativa avanzada).

    Tras firmar se verifica el resultado; si no fuera válido no se escribe ``output``.
    La firma debe ser el último paso: cualquier edición posterior la invalida.
    """
    import pymupdf
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers
    from pyhanko.stamp import TextStampStyle

    src = Path(input)
    data = src.read_bytes()
    with pymupdf.open(stream=data, filetype="pdf") as d:
        if d.needs_pass or d.metadata.get("encryption"):
            raise PdfTallerError("Quite la protección con contraseña antes de firmar. "
                                 "La firma digital debe ser el último paso.")
        if page is not None and not 0 <= page < d.page_count:
            raise PdfTallerError(f"La página {page + 1} no existe")
        height = d[page].rect.height if page is not None else 0
        if signature_image and page is not None and rect is not None:
            if d.get_sigflags() > 0:
                raise PdfTallerError("El documento ya tiene firmas: no se puede agregar la imagen sin "
                                     "invalidarlas. Firme sin imagen manuscrita.")
            x0, y0, x1, y1 = rect
            mid = y0 + (y1 - y0) * 0.5
            d[page].insert_image(pymupdf.Rect(x0, y0, x1, mid), filename=str(signature_image),
                                 keep_proportion=True)
            rect = (x0, mid, x1, y1)
            data = d.tobytes(garbage=3, deflate=True)
    signer = _load_signer(p12, p12_password)
    field_name = f"Firma_{dt.datetime.now():%Y%m%d_%H%M%S}"
    if timestamper is None and timestamp_url:
        from pyhanko.sign.timestamps import HTTPTimeStamper
        timestamper = HTTPTimeStamper(timestamp_url, timeout=20)
    meta = signers.PdfSignatureMetadata(
        field_name=field_name, reason=reason or None, location=location or None,
        contact_info=contact or None, md_algorithm="sha256",
        certify=lock, docmdp_permissions=fields.MDPPerm.NO_CHANGES if lock else fields.MDPPerm.FILL_FORMS,
        subfilter=fields.SigSeedSubFilter.PADES,
    )
    w = IncrementalPdfFileWriter(io.BytesIO(data), strict=False)
    style = None
    if page is not None and rect is not None:
        x0, y0, x1, y1 = rect
        box = (int(x0), int(height - y1), int(x1), int(height - y0))  # PDF: origen abajo a la izquierda
        fields.append_signature_field(w, fields.SigFieldSpec(field_name, on_page=page, box=box))
        text = "Firmado digitalmente por:\n%(signer)s\n%(ts)s"
        style = TextStampStyle(stamp_text=text)
    pdf_signer = signers.PdfSigner(meta, signer=signer, stamp_style=style, timestamper=timestamper)
    buf = io.BytesIO()
    try:
        pdf_signer.sign_pdf(w, output=buf)
    except Exception as exc:
        if timestamper is not None and "time" in f"{type(exc).__name__} {exc}".lower():
            raise PdfTallerError(f"No se pudo obtener el sello de tiempo de {timestamp_url or 'el servidor'}: "
                                 f"{exc}\nRevise la conexión a internet o firme sin sello de tiempo.") from exc
        raise PdfTallerError(f"No se pudo firmar: {exc}") from exc
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_bytes(buf.getvalue())
    try:
        st = verify_signatures(tmp)
        if not st or not (st[-1].intact and st[-1].covers_all):
            raise PdfTallerError("La verificación de la firma recién creada falló; no se guardó el archivo")
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)
    return out


# ---------------------------------------------------------------- verificar

@dataclass
class SignatureStatus:
    field: str
    signer: str
    signed_at: str
    intact: bool           # el contenido firmado no cambió
    covers_all: bool       # no hay cambios después de la firma
    trusted: bool          # el certificado está en la lista de confianza
    summary: str
    fingerprint: str = ""          # huella SHA-256 del certificado del firmante
    issuer: str = ""
    valid_from: str = ""
    valid_until: str = ""
    cert_expired: bool = False
    self_signed: bool = False
    timestamp: str = ""            # fecha del sello de tiempo de un tercero ("" si no tiene)
    timestamp_ok: bool = False
    certified: bool = False        # firma de certificación (bloqueo DocMDP)
    changes: str = ""              # tipo de cambios posteriores a la firma, si los hay
    details: list[str] = dc_field(default_factory=list)


def _name(n) -> str:
    try:
        return n.human_friendly.replace("Common Name: ", "").replace("Organization: ", "")
    except Exception:
        return str(n)


_CHANGES = {"NONE": "ninguno", "LTA_UPDATES": "solo datos de validación", "FORM_FILLING": "relleno de formularios",
            "ANNOTATIONS": "comentarios o anotaciones", "OTHER": "cambios de contenido"}


def verify_signatures(path: PathLike, trusted_certs: list[PathLike] | None = None) -> list[SignatureStatus]:
    """Verifica todas las firmas digitales del PDF.

    Se consideran de confianza los certificados de ``trusted_certs`` y los de la lista del usuario
    (:func:`trust_certificate`).
    """
    import logging

    from pyhanko.keys import load_cert_from_pemder
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko.sign.validation.status import SignatureCoverageLevel
    from pyhanko_certvalidator import ValidationContext

    logging.getLogger("pyhanko").setLevel(logging.CRITICAL)  # los avisos se informan abajo
    logging.getLogger("pyhanko_certvalidator").setLevel(logging.CRITICAL)
    roots = []
    for c in list(trusted_certs or []) + trusted_certificates():
        try:
            roots.append(load_cert_from_pemder(str(c)))
        except Exception:
            pass
    vc = ValidationContext(trust_roots=roots, allow_fetching=False)
    now = dt.datetime.now(dt.timezone.utc)
    result = []
    with open(path, "rb") as f:
        reader = PdfFileReader(f, strict=False)
        for sig in reader.embedded_signatures:
            st = validate_pdf_signature(sig, vc, skip_diff=False)
            covers = st.coverage == SignatureCoverageLevel.ENTIRE_FILE
            cert = st.signing_cert
            signer = _name(cert.subject) if cert else "?"
            when = st.signer_reported_dt.isoformat(timespec="seconds") if st.signer_reported_dt else ""
            s = SignatureStatus(sig.field_name, signer, when, False, covers, bool(st.trusted), "")
            if cert:
                validity = cert["tbs_certificate"]["validity"]
                nb, na = validity["not_before"].native, validity["not_after"].native
                s.fingerprint = _fingerprint(cert.dump())
                s.issuer = _name(cert.issuer)
                s.valid_from, s.valid_until = nb.date().isoformat(), na.date().isoformat()
                s.cert_expired = na < now
                s.self_signed = cert.subject == cert.issuer
            ts = getattr(st, "timestamp_validity", None)
            if ts is not None and getattr(ts, "timestamp", None):
                s.timestamp = ts.timestamp.isoformat(timespec="seconds")
                s.timestamp_ok = bool(ts.intact and ts.valid)
            s.certified = sig.docmdp_level is not None
            if not covers:
                s.changes = _CHANGES.get(getattr(getattr(st, "modification_level", None), "name", ""), "cambios")
            ok = bool(st.intact and st.valid)
            s.intact = ok
            docmdp_ok = getattr(st, "docmdp_ok", None)
            if ok and covers:
                msg = "✔ Firma válida: el documento no ha cambiado desde que se firmó."
            elif ok and s.changes in ("ninguno", "solo datos de validación"):
                msg = "✔ Firma válida (después de firmar solo se agregaron datos de validación)."
            elif ok:
                msg = f"⚠ La firma es válida, pero el documento tuvo cambios DESPUÉS de firmarse ({s.changes})."
            else:
                msg = "✘ Firma INVÁLIDA: el contenido firmado fue alterado."
            if ok and not st.trusted:
                msg += " Certificado NO registrado como de confianza: compare la huella con el firmante."
            s.summary = msg
            if ok and s.certified and docmdp_ok is False:
                s.details.append("El firmante bloqueó el documento y aun así fue modificado.")
            if s.cert_expired:
                s.details.append("El certificado del firmante ya venció.")
            if s.timestamp:
                s.details.append(f"Sello de tiempo de un tercero: {s.timestamp} "
                                 f"({'válido' if s.timestamp_ok else 'no verificado'}).")
            else:
                s.details.append("Sin sello de tiempo: la fecha la indicó el equipo del firmante.")
            result.append(s)
    return result


def signer_certificate(path: PathLike, index: int = 0) -> bytes:
    """Certificado (DER) del firmante de la firma ``index``, p. ej. para marcarlo de confianza."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    with open(path, "rb") as f:
        sigs = PdfFileReader(f, strict=False).embedded_signatures
        if not 0 <= index < len(sigs):
            raise PdfTallerError("No existe esa firma")
        return sigs[index].signer_cert.dump()
