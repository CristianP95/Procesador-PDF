# PDF Taller

Herramienta de código abierto (AGPL-3.0) en Python para manipular documentos PDF.
Motor: [PyMuPDF](https://pymupdf.readthedocs.io). Interfaz: PySide6. Plataforma principal: Windows.

## Estado (v0.1, prototipo)

| Grupo | Función | Núcleo | GUI |
|---|---|---|---|
| Ordenar | Unir | Sí | Sí |
| Ordenar | Dividir (cada N páginas o por rangos) | Sí | Sí |
| Ordenar | Reordenar (arrastrar miniaturas), rotar, eliminar, extraer | Sí | Sí |
| Seguridad | Proteger (AES-256, permisos) | Sí | Sí |
| Seguridad | Desbloquear (con contraseña conocida) | Sí | Sí |
| Seguridad | Comparar (texto y, opcional, imagen) | Sí | Sí |
| Seguridad | Censurar (borra el texto de verdad; texto o regex) | Sí | Sí |
| Optimizar | Comprimir, reparar, OCR | — | — |
| Convertir | PDF ↔ DOC | — | — |
| Editar | Marca de agua, formularios | — | — |

## Ejecutar en Windows

Requiere Python 3.10 o superior. Doble clic en `ejecutar.bat`
(la primera vez crea `.venv` e instala todo). O a mano:

```bat
py -m venv .venv
.venv\Scripts\pip install -e .[gui,dev]
.venv\Scripts\python -m pdftaller  archivo.pdf
```

## Crear el ejecutable (sin Python)

Doble clic en `construir_exe.bat` (en Windows, con Python instalado solo en la máquina que construye).
El resultado es la carpeta `dist\PDFTaller\` con `PDFTaller.exe`; esa carpeta se puede copiar
a cualquier PC con Windows y funciona sin Python.

## Uso de la GUI

- Cada documento se abre en su propia pestaña (Ctrl+O o arrastrar archivos a la ventana).
- Arrastre las miniaturas para reordenar; seleccione páginas y use Ctrl+L / Ctrl+R para rotar o Supr para eliminar.
  Los cambios quedan pendientes (● en la pestaña) hasta Guardar (Ctrl+S) o Guardar como.
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
    pages.py      rangos de páginas "1-3, 5"
  gui/         PySide6: ventana con pestañas, diálogos
tests/         pytest del núcleo
```

## Pruebas

```bat
.venv\Scripts\python -m pytest
```
