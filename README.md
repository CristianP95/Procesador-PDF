# PDF Taller

Herramienta de código abierto (AGPL-3.0) en Python para manipular documentos PDF.
Motor: [PyMuPDF](https://pymupdf.readthedocs.io). Interfaz: PySide6. Plataforma principal: Windows.

## Estado (v0.3, prototipo)

| Grupo | Función | Núcleo | GUI |
|---|---|---|---|
| Ordenar | Unir, dividir (rangos o partes iguales), extraer | Sí | Sí |
| Ordenar | Reordenar arrastrando o con clic derecho, rotar, eliminar, **deshacer/rehacer (Ctrl+Z / Ctrl+Y)** | Sí | Sí |
| Optimizar | **Comprimir** (baja/media/alta, grises) | Sí | Sí |
| Optimizar | **Reparar** PDFs dañados | Sí | Sí |
| Optimizar | **OCR** (texto buscable en escaneos; español/inglés incluidos en el .exe) | Sí | Sí |
| Seguridad | Proteger: contraseña de apertura opcional + contraseña de permisos; restricciones reales | Sí | Sí |
| Seguridad | Desbloquear (contraseña de propietario); la app respeta las restricciones | Sí | Sí |
| Seguridad | Comparar (texto e imagen) | Sí | Sí |
| Seguridad | Censurar por texto/regex y por zona, con vista previa y quitar marcas (clic derecho) | Sí | Sí |
| Seguridad | Certificar y verificar integridad (SHA-256) | Sí | Sí |
| Seguridad | **Firma digital con certificado** (.p12/.pfx, PAdES) y verificación | Sí | Sí |
| Editar | Insertar imagen de firma | Sí | Sí |
| Convertir | Imágenes a PDF | Sí | Sí |
| Convertir | PDF ↔ DOC | — | — |
| Editar | Marca de agua, formularios | — | — |

## Crear el ejecutable (sin Python)

Doble clic en `construir_exe.bat` (en Windows, con Python instalado solo en la máquina que construye).
El resultado es la carpeta `dist\PDFTaller\` con `PDFTaller.exe`; esa carpeta se puede copiar
a cualquier PC con Windows y funciona sin Python.

## Uso de la GUI

- Cada documento se abre en su propia pestaña (Ctrl+O o arrastrar archivos a la ventana).
- A la izquierda, miniaturas: arrástrelas para reordenar o use clic derecho (rotar, mover, extraer, eliminar).
  A la derecha, vista previa de la página con zoom (Ctrl+rueda).
- **Censurar zona**: active el botón y dibuje recuadros sobre la vista previa. **Firmar**: elija la imagen y dibuje
  el recuadro donde va. Todo queda pendiente (● en la pestaña) hasta Guardar (Ctrl+S) o Guardar como.
- **Censurar por texto** marca las coincidencias en la vista previa (rojo oscuro); revíselas y quite las que
  no correspondan con clic derecho. Nada se borra hasta guardar.
- **Firma digital**: Seguridad → Firmar digitalmente. Puede crear su propio certificado (.p12) desde el diálogo.
  Hágalo como último paso: cualquier cambio posterior invalida la firma (Verificar firmas digitales lo detecta).
- **Certificar** guarda `documento.pdf.sha256.json` con la huella; **Verificar integridad** detecta si el PDF cambió.
- Las operaciones de Ordenar y Seguridad crean un archivo nuevo y lo abren en otra pestaña.
- Los documentos protegidos piden la contraseña al abrirse; editarlos conserva la protección.

## Uso desde Python (base de la V2)

Toda la lógica está en `pdftaller.core`, que no depende de la GUI:

```python
from pdftaller import core

core.merge(["a.pdf", "b.pdf"], "unido.pdf", page_ranges=[None, "1-3"])
core.split("unido.pdf", "partes/", every=1)
core.reorder("unido.pdf", "ordenado.pdf", [2, 0, 1])          # índices base 0
core.protect("ordenado.pdf", "seguro.pdf", "clave", allow_print=True)
core.unlock("seguro.pdf", "libre.pdf", "clave")
print(core.compare("a.pdf", "b.pdf").summary())
core.redact("libre.pdf", "censurado.pdf", [r"\d{10}"], regex=True)
```

Ver `ejemplos/automatizar.py`. En texto las páginas son base 1 (`"1-3,5"`, `"8-"`);
en listas de enteros son base 0.

## Estructura

```
src/pdftaller/
  core/        lógica pura (V1 y V2 la comparten)
    organize.py   unir, dividir, reordenar, rotar, eliminar, extraer
    security.py   proteger, desbloquear, comparar, censurar
    integrity.py  certificar / verificar con SHA-256
    edit.py       insertar firmas (imágenes)
    convert.py    imágenes a PDF
    pages.py      rangos de páginas "1-3, 5"
  gui/         PySide6: ventana con pestañas, diálogos
tests/         pytest del núcleo
```

## Pruebas

```bat
.venv\Scripts\python -m pytest
```
