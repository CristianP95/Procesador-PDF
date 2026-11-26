# Automatización con `procesador_pdf.core`

El paquete `procesador_pdf.core` contiene toda la lógica de la aplicación y no depende de la interfaz
gráfica. Es la base de la versión 2 (automatización): un programa en Python puede ejecutar las
mismas operaciones que la interfaz.

```python
from procesador_pdf import core
```

## Convenciones

- Las rutas pueden ser `str` o `pathlib.Path`. Las funciones escriben un archivo nuevo en
  `output` y lo devuelven como `Path`; el original no se modifica (salvo que `output` sea la
  misma ruta). Se guarda primero en un archivo temporal, así un error no deja archivos a medias.
- Páginas en texto: base 1 (`"1-3, 5, 8-"`). Páginas en listas de enteros: base 0.
- Coordenadas de zonas: `(x0, y0, x1, y1)` en puntos PDF (1/72 de pulgada), origen arriba a la
  izquierda, sobre la página sin girar.
- `password`: contraseña del documento de entrada, si está protegido.
- Los errores se informan con `core.ProcesadorPdfError` (y sus subclases `PasswordError` y
  `PageRangeError`), con mensajes en español pensados para mostrarse al usuario.

## Ordenar

| Función | Descripción |
|---|---|
| `merge(inputs, output, page_ranges=None, passwords=None)` | Une varios PDF; `page_ranges` permite tomar solo algunas páginas de cada uno. |
| `split(input, output_dir, *, every=None, ranges=None, prefix=None)` | Divide en partes de `every` páginas o por grupos `"1-13; 14-31"`. |
| `extract_pages(input, output, pages)` | Copia las páginas indicadas (`"1-3,7"`) a un PDF nuevo. |
| `reorder(input, output, order)` | Reescribe con las páginas en `order` (base 0). |
| `delete_pages(input, output, pages)` | Elimina páginas (base 0). |
| `rotate_pages(input, output, pages, degrees)` | Gira páginas en múltiplos de 90 grados (`pages=None`: todas). |
| `page_count(path)` | Número de páginas. |

## Optimizar

| Función | Descripción |
|---|---|
| `analyze(input)` | Qué ocupa espacio (imágenes, fuentes, contenido); `.message()` y `.recommendation()`. |
| `compress(input, output, level="media", *, gray, dpi, quality, strip)` | Niveles `"baja"`, `"media"`, `"alta"` o ajuste propio con `dpi` y `quality`. Devuelve un informe con `.before`, `.after` y `.message()`. |
| `estimate_compression(input)` | Tamaño que daría cada nivel, sin modificar nada. |
| `recognize_text(input, output, *, language="spa+eng", dpi=300, only_without_text=True, keep_original=True, progress=None)` | Reconoce el texto de páginas escaneadas (alias de `ocr`). `progress(i, total)` puede devolver `False` para cancelar. |
| `repair(input, output)` | Reconstruye un PDF dañado. |
| `find_tessdata()`, `ocr_languages()` | Ubicación de los datos de Tesseract e idiomas disponibles. |

## Convertir

| Función | Descripción |
|---|---|
| `images_to_pdf(images, output, *, page_size=None, margin=0)` | Una imagen por página; `page_size` `"A4"`, `"letter"` o igual a la imagen. |

## Editar

| Función | Descripción |
|---|---|
| `watermark(input, output, text=None, *, image=None, pages=None, opacity=0.25, rotation=45, fontsize=None, color="#808080", position="centro", behind=False, scale=0.5)` | Marca de agua de texto o imagen. `position`: `"centro"`, `"mosaico"`, `"arriba"`, `"abajo"`. Devuelve `(ruta, páginas_marcadas)`. |
| `list_fields(input)` | Campos de formulario: nombre, tipo (`texto`, `casilla`, `opción`, `lista`), valor, opciones, página. |
| `fill_form(input, output, values, *, flatten=False, strict=True)` | Diligencia el formulario con `{campo: valor}`; `flatten` deja los datos fijos. |
| `fill_from_csv(template, csv_path, output_dir, *, name_column=None, flatten=False)` | Un PDF diligenciado por fila del CSV (separador `,` o `;` detectado automáticamente). |
| `insert_images(input, output, placements)` | Inserta imágenes: `[(página_base0, rect, ruta_imagen), ...]`. |

## Seguridad

| Función | Descripción |
|---|---|
| `find_text(input, terms, *, regex=False)` | Zonas donde aparecen los textos, por página. |
| `redact(input, output, terms=(), *, regex=False, areas=None, remove_metadata=True)` | Censura definitiva: borra el contenido bajo las zonas. Devuelve `(ruta, zonas)`. |
| `protect(input, output, user_password, owner_password=None, *, allow_print, allow_copy, allow_modify, allow_annotate)` | Cifrado AES-256. Para aplicar restricciones, la contraseña de permisos debe ser distinta de la de apertura. |
| `generate_password(length=16)` | Contraseña aleatoria fuerte. |
| `permissions(path, password=None)` | Permisos efectivos con esa contraseña. |
| `unlock(input, output, password)` | Quita la protección (requiere la contraseña de permisos). |
| `compare(a, b, *, visual=False)` | Diferencias de texto (y de imagen) por página; `.summary()`. |
| `certify(path, author=None, note=None)` / `verify(path, certificate=None, expected_hash=None)` | Huella SHA-256 guardada en `documento.pdf.sha256.json` y su verificación. |

## Firma digital

| Función | Descripción |
|---|---|
| `create_certificate(output, name, password, *, email=None, organization=None)` | Certificado personal autofirmado (.p12, RSA 3072). |
| `sign(input, output, p12, p12_password, *, reason, location, page=None, rect=None, lock=True, signature_image=None, timestamp_url=None)` | Firma PAdES. `timestamp_url` agrega sello de tiempo (p. ej. `core.DEFAULT_TSA`). El resultado se verifica antes de guardarse. |
| `verify_signatures(path)` | Estado de cada firma: integridad, cambios posteriores, confianza, huella, sello de tiempo. |
| `export_public_certificate(p12, password, output)` | Exporta el certificado público (.cer) y devuelve su huella. |
| `trust_certificate(cert)`, `untrust_certificate(huella)`, `trusted_certificates()` | Lista de certificados de confianza del equipo. |

## Ejemplo: constancias para un grupo

```python
from pathlib import Path
from procesador_pdf import core

salida = Path("constancias")
pdfs = core.fill_from_csv("plantilla.pdf", "estudiantes.csv", salida, name_column="archivo", flatten=True)
for pdf in pdfs:
    core.watermark(pdf, pdf, "ORIGINAL", position="abajo", rotation=0, opacity=0.3)
    core.sign(pdf, pdf.with_name(pdf.stem + "_firmado.pdf"), "mi_certificado.p12", "Clave-segura1",
              reason="Constancia de participación")
```
