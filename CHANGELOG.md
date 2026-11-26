# Historial de versiones

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto usa
[versionado semántico](https://semver.org/lang/es/). Mientras la versión sea 0.x la interfaz
de programación (`procesador_pdf.core`) puede cambiar entre versiones.

## [0.6.0] - 2026-11-25

### Agregado
- Ventana «Acerca de» (menú Ayuda) con logo, versión, autor, licencia, componentes usados
  e historial de versiones.
- Icono de la aplicación en la ventana, la barra de tareas y el ejecutable; logo del autor
  en «Acerca de».
- En la vista previa, la rueda del ratón pasa a la página siguiente o anterior al llegar al
  borde de la página; Re Pág / Av Pág también cambian de página.
- Documentación para publicación: guía de uso, guía de automatización y guía de contribución.

### Cambiado
- La aplicación pasa a llamarse Procesador PDF; el paquete de Python es `procesador_pdf`
  (antes `pdftaller`) y el ejecutable `ProcesadorPDF.exe`.
- LICENSE contiene el texto completo de la GNU AGPL-3.0.

## [0.5.0] - 2026-11-22

### Agregado
- Marca de agua de texto o imagen: centro, mosaico, arriba o abajo; color, tamaño, giro,
  opacidad, detrás del contenido y rango de páginas, con vista previa.
- Diligenciar formularios: texto, casillas, listas y grupos de opciones; aplanar; lote desde
  CSV (`core.fill_from_csv`).
- Pantalla de inicio con las acciones más usadas.

### Cambiado
- «OCR» pasa a llamarse «Reconocer texto» en la interfaz (`core.recognize_text` como alias).
- Menús simplificados: seis menús cortos con submenús para lo poco frecuente; la barra queda
  con Abrir, Guardar, Deshacer, Rehacer y un botón por grupo.

## [0.4.0] - 2026-11-20

### Agregado
- Panel único de censura (texto y zonas), lista de zonas marcadas y vista del resultado final.
- Deshacer y rehacer en la barra, también después de guardar.
- Firma digital: sello de tiempo RFC 3161, lista de certificados de confianza, exportar
  certificado público, imagen de firma manuscrita, autoverificación y verificación detallada.
- Análisis de tamaño, compresión personalizada y estimación de tamaño por nivel.
- Operaciones largas en segundo plano con progreso y cancelación.

### Cambiado
- El reconocimiento de texto conserva la página original y agrega texto invisible.
- Proteger permite restricciones sin contraseña de apertura; la contraseña de permisos puede
  generarse automáticamente.

### Corregido
- Arrastrar páginas hacia posiciones anteriores las enviaba al final.
- Con una sola contraseña, las restricciones de un PDF protegido no tenían efecto.

## [0.3.0] - 2026-11-20

### Agregado
- Comprimir (baja, media, alta), reparar y reconocer texto con Tesseract.
- Firma digital con certificado .p12/.pfx (PAdES) y verificación.
- Contraseña de apertura opcional y contraseña de permisos separada.
- Deshacer y rehacer cambios de páginas.
- Ejecutable para Windows con los idiomas español e inglés incluidos.

## [0.2.0] - 2026-11-20

### Agregado
- Vista previa de página con zoom y menú contextual sobre las miniaturas.
- Dividir con vista previa de los archivos que se crearán.
- Censurar por zona dibujada sobre la página.
- Certificar y verificar integridad con huella SHA-256.
- Insertar firma desde imagen e imágenes a PDF.

## [0.1.0] - 2026-11-20

### Agregado
- Primera versión: núcleo separado de la interfaz (`core`) e interfaz gráfica PySide6 con una
  pestaña por documento.
- Ordenar: unir, dividir, reordenar, rotar, eliminar y extraer páginas.
- Seguridad: proteger con AES-256, desbloquear, comparar y censurar texto.
- Scripts para ejecutar y construir el ejecutable en Windows.
