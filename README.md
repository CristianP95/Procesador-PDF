# PDF Taller

Herramienta de código abierto (AGPL-3.0) en Python para manipular documentos PDF.
Motor: [PyMuPDF](https://pymupdf.readthedocs.io). Interfaz: PySide6. Plataforma principal: Windows.

## Estado (v0.5, prototipo)

| Grupo | Función | Núcleo | GUI |
|---|---|---|---|
| Ordenar | Unir, dividir (rangos o partes iguales), extraer | Sí | Sí |
| Ordenar | Reordenar **arrastrando (también hacia atrás)** o con clic derecho, rotar, eliminar | Sí | Sí |
| Editar | **Deshacer / Rehacer** (Ctrl+Z / Ctrl+Y, botones en la barra), también después de guardar | — | Sí |
| Optimizar | **Comprimir** con análisis de tamaño (baja/media/alta o a medida; grises; quitar metadatos; tamaño estimado) | Sí | Sí |
| Optimizar | **Reparar** PDFs dañados | Sí | Sí |
| Optimizar | **Reconocer texto** de escaneos, sin perder calidad (español/inglés incluidos en el .exe) | Sí | Sí |
| Seguridad | Proteger: contraseña de apertura opcional + permisos con contraseña de propietario (o generada) | Sí | Sí |
| Seguridad | Desbloquear (contraseña de propietario); la app respeta las restricciones | Sí | Sí |
| Seguridad | Comparar (texto e imagen) | Sí | Sí |
| Seguridad | **Censurar en un solo panel**: por texto/regex y por zona, lista de zonas, quitar, vista del resultado | Sí | Sí |
| Seguridad | Certificar y verificar integridad (SHA-256) | Sí | Sí |
| Seguridad | Firma digital (.p12/.pfx, PAdES): **sello de tiempo, certificados de confianza, firma manuscrita, autoverificación** | Sí | Sí |
| Editar | Insertar imagen de firma | Sí | Sí |
| Convertir | Imágenes a PDF | Sí | Sí |
| Convertir | PDF ↔ DOC | — | — |
| Editar | **Marca de agua** (texto o imagen; centro, mosaico, arriba o abajo; giro, color, opacidad; vista previa) | Sí | Sí |
| Editar | **Diligenciar formularios** (texto, casillas, listas, opciones; aplanar; lote desde CSV) | Sí | Sí |

### Novedades de la v0.5

- **Lenguaje sencillo**: «OCR» pasa a llamarse **Reconocer texto** en menús, diálogos y mensajes
  (en Python sigue existiendo `core.ocr` y se añade el alias `core.recognize_text`).
- **Menú simplificado**: seis menús cortos con los grupos del proyecto (Archivo, Ordenar, Optimizar, Convertir,
  Editar, Seguridad). Lo poco frecuente va en submenús (*Páginas seleccionadas*, *Firma digital*,
  *Huella de integridad*); se unieron entradas repetidas (un solo «Censurar…», el análisis de tamaño dentro de
  «Comprimir…»). La barra quedó en 4 botones (Abrir, Guardar, Deshacer, Rehacer) + un botón por grupo que abre
  su menú. El clic derecho sobre páginas usa submenús *Girar* y *Mover*. La pantalla de inicio ofrece Abrir, Unir,
  Imágenes a PDF y Verificar.
- **Marca de agua** (Editar → Marca de agua…): texto (p. ej. CONFIDENCIAL) o imagen (logo), en el centro, repetida
  en toda la hoja, arriba o abajo; color, tamaño automático, giro, opacidad, detrás del contenido y rango de páginas,
  con vista previa en vivo. Respeta las páginas giradas.
- **Diligenciar formularios** (Editar → Diligenciar formulario…): muestra los campos del PDF agrupados por página
  (texto, casillas, listas desplegables y grupos de opciones), valida opciones y longitud, y guarda en un archivo
  nuevo; opción «Aplanar» para que los datos queden fijos. Desde Python: `core.fill_from_csv` genera un PDF por fila
  de un CSV (p. ej. una constancia por estudiante).

### Novedades de la v0.4

- **Censurar**: «Censurar por texto» y «Censurar zona» abren el mismo panel a la derecha. Las coincidencias de texto y
  las zonas dibujadas van a una sola lista (página + texto encontrado); se pueden seleccionar, ver resaltadas, quitar
  (botón o Supr) y activar «Ver cómo quedará» para ver la página ya censurada antes de aplicar.
- **Arrastrar páginas**: antes, si se soltaba entre dos filas o con las miniaturas en una sola columna, la página iba
  al final. Ahora se inserta junto a la miniatura más cercana (izquierda/derecha o arriba/abajo, según la vista), y la
  lista se desplaza sola al acercar el ratón al borde.
- **Deshacer**: botones ↶/↷ en la barra con el nombre de la acción. Después de guardar (incluida la censura), Ctrl+Z
  vuelve a la versión anterior durante la sesión (hay que guardar de nuevo para escribirla en el disco).
- **Proteger**: se puede restringir imprimir/copiar/modificar/comentar **sin** contraseña de apertura. La contraseña de
  permisos es opcional: si se deja vacía se genera una fuerte y se muestra para copiarla. La app comprueba que las
  restricciones quedaron activas al reabrir el archivo. Nota: Adobe Reader y PDF Taller las respetan; los visores de
  los navegadores pueden ignorar algunas.
- **Firmas**: contraseña robusta obligatoria para certificados nuevos; sello de tiempo RFC 3161 opcional
  (`http://timestamp.digicert.com`, necesita internet); lista de certificados de confianza (el propio se agrega solo;
  los de otros se agregan comparando la huella SHA-256); exportar el certificado público (.cer) para compartirlo;
  imagen de la firma manuscrita dentro del sello; el resultado se verifica antes de guardarse; la verificación
  muestra emisor, vigencia, huella, sello de tiempo y tipo de cambios posteriores.
- **Optimizar**: análisis de tamaño, compresión personalizada (ppp y calidad JPEG), estimación de tamaño por nivel,
  quitar metadatos/adjuntos/JavaScript, OCR que conserva la página original y operaciones largas en segundo plano
  (con barra de progreso y Cancelar).

## Crear el ejecutable (sin Python)

Doble clic en `construir_exe.bat` (en Windows, con Python instalado solo en la máquina que construye).
El resultado es la carpeta `dist\PDFTaller\` con `PDFTaller.exe`; esa carpeta se puede copiar
a cualquier PC con Windows y funciona sin Python.

## Uso de la GUI

- Cada documento se abre en su propia pestaña (Ctrl+O o arrastrar archivos a la ventana).
- A la izquierda, miniaturas: arrástrelas para reordenar o use clic derecho (rotar, mover, extraer, eliminar).
  A la derecha, vista previa de la página con zoom (Ctrl+rueda).
- **Censurar** (Ctrl+Shift+C): panel con búsqueda de texto, dibujo de zonas y la lista de todo lo marcado.
  Nada se borra hasta «Aplicar censura y guardar» (por defecto en un archivo nuevo).
- **Firma (imagen)**: elija la imagen y dibuje el recuadro donde va. Todo queda pendiente (● en la pestaña)
  hasta Guardar (Ctrl+S) o Guardar como.
- **Firma digital**: puede crear su propio certificado (.p12) desde el diálogo de firmar.
  Hágalo como último paso: cualquier cambio posterior invalida la firma (Verificar firmas digitales lo detecta).
- **Firma digital**: Seguridad → Firma digital → Firmar…
- **Huella de integridad** (Seguridad): «Crear huella» guarda `documento.pdf.sha256.json`; «Verificar huella» detecta si el PDF cambió.
- **Marca de agua** y **Diligenciar formulario**: menú Editar; ambos guardan un archivo nuevo y lo abren en otra pestaña.
- Las operaciones de Ordenar y Seguridad crean un archivo nuevo y lo abren en otra pestaña.
- Los documentos protegidos piden la contraseña al abrirse; editarlos conserva la protección.

## Uso desde Python (base de la V2)

Toda la lógica está en `pdftaller.core`, que no depende de la GUI:

```python
from pdftaller import core

core.merge(["a.pdf", "b.pdf"], "unido.pdf", page_ranges=[None, "1-3"])
core.split("unido.pdf", "partes/", every=1)
core.reorder("unido.pdf", "ordenado.pdf", [2, 0, 1])          # índices base 0
clave_permisos = core.generate_password()
core.protect("ordenado.pdf", "seguro.pdf", "", clave_permisos, allow_print=True, allow_copy=False)
core.unlock("seguro.pdf", "libre.pdf", clave_permisos)
print(core.analyze("libre.pdf").message())
core.compress("libre.pdf", "liviano.pdf", dpi=110, quality=65)
print(core.compare("a.pdf", "b.pdf").summary())
core.redact("libre.pdf", "censurado.pdf", [r"\d{10}"], regex=True)
core.watermark("libre.pdf", "marcado.pdf", "CONFIDENCIAL", opacity=0.2, position="mosaico")
print([f.name for f in core.list_fields("formulario.pdf")])
core.fill_form("formulario.pdf", "lleno.pdf", {"nombre": "Ana Pérez", "acepta": True}, flatten=True)
core.fill_from_csv("formulario.pdf", "estudiantes.csv", "constancias/", name_column="archivo")
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
    watermark.py  marca de agua de texto o imagen
    forms.py      leer, diligenciar y aplanar formularios; lote desde CSV
    optimize.py   comprimir, analizar, reparar, reconocer texto
    signing.py    firma digital, sello de tiempo, certificados de confianza
    convert.py    imágenes a PDF
    pages.py      rangos de páginas "1-3, 5"
  gui/         PySide6: ventana con pestañas, diálogos
tests/         pytest del núcleo
```

## Pruebas

```bat
.venv\Scripts\python -m pytest
```
