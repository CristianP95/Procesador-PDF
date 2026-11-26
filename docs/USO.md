# Guía de uso

## Ventana principal

- Cada documento se abre en su propia pestaña: menú Archivo, Ctrl+O o arrastrando archivos a la ventana.
- A la izquierda están las miniaturas de las páginas; a la derecha, la vista previa.
- En la vista previa, la rueda del ratón desplaza la página y, al llegar al borde, pasa a la
  siguiente o a la anterior. Re Pág y Av Pág cambian de página; Ctrl + rueda acerca o aleja.
- Los cambios de páginas, zonas censuradas y firmas quedan pendientes (la pestaña muestra un
  punto) hasta Guardar (Ctrl+S) o Guardar como.
- Deshacer (Ctrl+Z) y Rehacer (Ctrl+Y) funcionan también después de guardar, durante la sesión.
- Las operaciones que producen un documento nuevo (unir, comprimir, proteger, marca de agua,
  formulario, firma) piden dónde guardarlo y lo abren en otra pestaña.

La barra superior tiene Abrir, Guardar, Deshacer, Rehacer y un botón por grupo de herramientas.

## Ordenar

- **Unir PDF**: elija los archivos y ordénelos arrastrándolos en la lista.
- **Dividir**: por rangos separados por punto y coma (`1-13; 14-31`: dos archivos) o en partes iguales.
- **Extraer páginas**: copia las páginas indicadas a un PDF nuevo.
- **Reordenar**: arrastre las miniaturas; una línea azul marca dónde quedarán. Con clic derecho:
  Girar, Mover, Extraer, Eliminar. Atajos: Alt + flechas (mover), Ctrl+L / Ctrl+R (girar), Supr (eliminar).

## Optimizar

- **Comprimir**: muestra qué ocupa espacio en el archivo y recomienda un nivel. «Calcular tamaño
  de cada nivel» estima el resultado antes de guardar. Nivel personalizado: resolución y calidad.
- **Reconocer texto**: convierte páginas escaneadas en texto que se puede buscar, copiar y
  censurar. Por defecto conserva la página original y agrega el texto de forma invisible.
- **Reparar**: reconstruye archivos dañados y omite las páginas ilegibles.

## Convertir

- **Imágenes a PDF**: una imagen por página, con tamaño igual a la imagen, A4 o carta.

## Editar

- **Marca de agua**: texto o imagen, en el centro, repetida, arriba o abajo; color, tamaño,
  giro, opacidad, detrás del contenido y rango de páginas. La vista previa muestra el resultado.
- **Diligenciar formulario**: lista los campos del PDF por página. «Aplanar» deja los datos
  fijos para que no se puedan editar. Si el PDF no tiene campos (por ejemplo, un formulario
  escaneado), use Insertar firma o la marca de agua.
- **Insertar firma (imagen)**: elija la imagen de su firma y dibuje el recuadro donde va.

## Seguridad

- **Censurar**: abre un panel con dos formas de marcar: buscar textos (o expresiones regulares,
  por ejemplo `\d{10}` para 10 dígitos) y dibujar zonas sobre la vista previa. Todas las zonas
  aparecen en una lista donde se pueden revisar y quitar. «Ver cómo quedará» muestra la página
  ya censurada. La censura borra el contenido de verdad al aplicarla.
- **Proteger con contraseña**: contraseña de apertura opcional y permisos (imprimir, copiar,
  modificar, comentar). La contraseña de permisos puede generarse automáticamente; guárdela,
  porque sin ella no se puede quitar la protección. Adobe Reader respeta los permisos; algunos
  visores de navegador ignoran parte de ellos.
- **Comparar con otro PDF**: diferencias de texto y, opcionalmente, de imagen, página por página.
- **Firma digital**: firma con un certificado .p12/.pfx (puede crear uno propio). Opciones:
  bloquear el documento, sello de tiempo de un tercero (necesita internet) e imagen de la firma
  manuscrita. «Verificar firmas» muestra si el documento cambió después de firmarse. Para que
  las firmas de otra persona aparezcan como de confianza, compare con ella la huella SHA-256 y
  agregue su certificado en «Certificados de confianza».
- **Huella de integridad**: guarda la huella SHA-256 del archivo en `documento.pdf.sha256.json`;
  la verificación detecta cualquier modificación posterior.

## Ayuda

- **Acerca de**: versión, autor, licencia, componentes y el historial de versiones.
