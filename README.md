# Procesador PDF

Aplicación de escritorio de código abierto para trabajar con documentos PDF sin enviarlos a
servicios externos: ordenar, optimizar, convertir, editar y proteger. Escrita en Python con
[PyMuPDF](https://pymupdf.readthedocs.io), [PySide6](https://doc.qt.io/qtforpython-6/) y
[pyHanko](https://pyhanko.readthedocs.io). Plataforma principal: Windows.

Todo el procesamiento ocurre en el equipo del usuario. La única conexión a internet es
opcional: el sello de tiempo de la firma digital.

## Funciones

| Grupo | Funciones |
|---|---|
| Ordenar | Unir, dividir (por rangos o en partes iguales), extraer, reordenar arrastrando, girar, eliminar |
| Optimizar | Comprimir con análisis de tamaño, reconocer texto en escaneos (español e inglés), reparar |
| Convertir | Imágenes a PDF |
| Editar | Marca de agua (texto o imagen), diligenciar formularios, insertar firma manuscrita, deshacer y rehacer |
| Seguridad | Censurar por texto o por zona, proteger con contraseña y permisos, quitar protección, comparar documentos, firma digital PAdES con sello de tiempo, huella de integridad SHA-256 |

Pendiente: conversión PDF a Word y Word a PDF; interfaz de automatización completa (versión 2).

## Instalación

### Ejecutable para Windows

Descargue el archivo `.zip` de la última versión en la sección *Releases* del repositorio,
descomprímalo y abra `ProcesadorPDF.exe`. No necesita Python.

### Desde el código fuente

Requiere Python 3.10 o superior.

```bat
git clone https://github.com/CristianP95/Procesador-PDF.git
cd Procesador-PDF
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[gui]"
.venv\Scripts\python -m procesador_pdf
```

En Windows también puede usar `ejecutar.bat`, que crea el entorno la primera vez.

Para reconocer texto se necesitan los datos de Tesseract: el ejecutable ya los incluye; desde el
código fuente, `construir_exe.bat` los descarga en `tessdata/`, o puede instalar
[Tesseract para Windows](https://github.com/UB-Mannheim/tesseract/wiki) con el idioma español.

## Uso

La guía de la interfaz está en [docs/USO.md](docs/USO.md).

La lógica está en el paquete `procesador_pdf.core`, que no depende de la interfaz y puede usarse
desde scripts:

```python
from procesador_pdf import core

core.merge(["a.pdf", "b.pdf"], "unido.pdf")
core.redact("unido.pdf", "censurado.pdf", [r"\d{10}"], regex=True)
core.watermark("censurado.pdf", "marcado.pdf", "CONFIDENCIAL", opacity=0.2)
core.fill_from_csv("formulario.pdf", "estudiantes.csv", "constancias/", name_column="archivo")
```

Referencia de funciones: [docs/AUTOMATIZACION.md](docs/AUTOMATIZACION.md). Ejemplo completo:
[ejemplos/automatizar.py](ejemplos/automatizar.py).

## Desarrollo

```bat
.venv\Scripts\python -m pip install -e ".[gui,dev]"
.venv\Scripts\python -m pytest
```

Las pruebas de interfaz se ejecutan sin pantalla (`QT_QPA_PLATFORM=offscreen`). La prueba del
sello de tiempo usa internet y solo se ejecuta con `PROCESADOR_PDF_TEST_TSA=1`.

Crear el ejecutable: `construir_exe.bat` (genera `dist\ProcesadorPDF\`).

```
src/procesador_pdf/
  core/          lógica sin interfaz (compartida por la aplicación y los scripts)
  gui/           interfaz PySide6
  branding.py    nombre, versión, autor y logo
tests/           pruebas (pytest)
docs/            documentación
ejemplos/        scripts de automatización
```

Consulte [CONTRIBUTING.md](CONTRIBUTING.md) para proponer cambios y
[CHANGELOG.md](CHANGELOG.md) para el historial de versiones.

## Licencia

[GNU AGPL-3.0](LICENSE). PyMuPDF se distribuye bajo AGPL, por lo que el proyecto usa la misma
licencia: puede usarlo, estudiarlo, modificarlo y compartirlo; las versiones modificadas que se
distribuyan o se ofrezcan como servicio deben publicar su código con la misma licencia.

Desarrollado por Cristian Pineda.
