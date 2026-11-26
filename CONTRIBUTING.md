# Cómo contribuir

Gracias por su interés en el proyecto. Se reciben reportes de errores, ideas y cambios de código.

## Reportar un error

Abra un *issue* con:

- la versión (menú Ayuda, Acerca de) y el sistema operativo;
- los pasos para reproducirlo y lo que esperaba que ocurriera;
- el mensaje de error completo, si lo hubo.

No adjunte documentos con datos personales. Si el error depende de un PDF concreto, comparta
una copia sin información sensible.

## Proponer cambios

1. Cree una rama a partir de `main`.
2. Instale el entorno de desarrollo:

   ```bat
   python -m venv .venv
   .venv\Scripts\python -m pip install -e ".[gui,dev]"
   ```

3. Haga el cambio. La lógica va en `src/procesador_pdf/core` (sin dependencias de la interfaz) y la
   interfaz en `src/procesador_pdf/gui`.
4. Agregue o actualice las pruebas en `tests/` y ejecútelas:

   ```bat
   .venv\Scripts\python -m pytest
   ```

5. Describa el cambio en `CHANGELOG.md`, en la sección de la próxima versión.
6. Abra un *pull request* explicando qué cambia y por qué.

## Estilo

- Código, nombres visibles y mensajes en español; nombres de funciones del núcleo en inglés,
  como los actuales.
- Mensajes de error pensados para personas sin conocimientos técnicos.
- Comentarios solo cuando expliquen algo que el código no muestra por sí mismo.

## Licencia

Al contribuir acepta que su aporte se distribuya bajo la licencia AGPL-3.0 del proyecto.
