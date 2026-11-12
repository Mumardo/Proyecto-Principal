# Calce + Matices

Aplicación web local que integra el análisis de color de Matices con las
recomendaciones de calce y el catálogo de Calce.

## Flujo integrado

1. Toma una foto con la cámara del dispositivo o selecciona una imagen. Al
   avanzar, la aplicación analiza sus tonos en el navegador y muestra una paleta
   recomendada con una explicación orientativa. Si activas **Recuérdame**, la
   foto se conserva en este navegador; con una sesión iniciada también se guarda
   en el almacenamiento privado de tu cuenta.
2. Ingresa busto, cintura y cadera, y elige tu preferencia de calce y las
   prendas que quieres explorar. Las recomendaciones se calculan con tus
   medidas y el calce elegido.
3. Continúa al catálogo para buscar, filtrar por tipo, ordenar y comparar
   prendas. En la tercera pestaña, **Probador**, puedes iniciar pruebas
   virtuales y consultar las operaciones guardadas en tu cuenta. Las tarjetas y
   la comparación muestran el calce estimado y las medidas referenciales
   disponibles.

La paleta es una orientación visual; no filtra prendas por color, porque el
catálogo no contiene datos de color verificados por producto. Las estimaciones
de calce son orientativas y usan las referencias disponibles, no medidas físicas
verificadas de cada publicación.

## Preparación y ejecución

Se requiere Python 3.9 o posterior. Instala las dependencias y ejecuta la app:

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

Abre <http://127.0.0.1:4173/>. También puedes iniciar con `npm start` después
de instalar las dependencias de Python. Para detener el servidor, presiona
`Ctrl+C` en la terminal.

El acceso a la cámara requiere permiso del navegador y un contexto seguro:
usa `localhost` en este equipo o sirve la aplicación mediante HTTPS.

## Publicación gratuita en Render

El [`render.yaml`](./render.yaml) despliega la app en un servicio web gratuito
con subdominio HTTPS. Está publicado en
<https://calce-matices-publica.onrender.com>. La página es pública; los perfiles
y las fotos de las cuentas siguen protegidos por la autenticación y RLS de
Supabase. Los servicios gratuitos pueden suspenderse tras inactividad y tardar
en reactivarse.

Para desplegar cambios, conecta el repositorio de GitHub en Render mediante
**New → Blueprint** y sincroniza el Blueprint con la rama
`deploy/calce-matices-publica`. Configura `SUPABASE_PUBLISHABLE_KEY` como
variable de entorno en Render. Para habilitar el probador, configura también
`VTON_API_URL` con la URL base permanente de Modal (sin `/try-on`) y
`VTON_API_TOKEN` con el mismo token guardado en el secreto de Modal
`vton-api-auth`. Render solicitará estas variables al sincronizar el Blueprint;
el token no debe publicarse ni guardarse en el repositorio. No publiques `.env`
ni uses la clave `service_role`.

## Integración con Aiuta Virtual Try-On

La llamada a Aiuta se ejecuta en una Edge Function de Supabase, no en el
servidor Python ni en el navegador. Requiere una sesión iniciada. Para
habilitarla:

1. En el panel SQL de Supabase, ejecuta `supabase/schema.sql` para crear la
   tabla de operaciones, las políticas RLS y el bucket privado temporal.
2. Suscríbete al producto Virtual Try-On en el
   [portal de Aiuta](https://developer.aiuta.com/products/digital-try-on/documentation).
   En Supabase, configura `AIUTA_API_KEY` como secreto de Edge Functions; no la
   agregues a `.env`, Render ni al código del cliente.
3. Despliega la función desde `Calce y Matices Integrado`:

   ```bash
   supabase functions deploy aiuta-try-on
   ```

Las operaciones y sus estados, SKU, errores y URLs de resultados se guardan en
`aiuta_try_on_operations`, con acceso de lectura limitado mediante RLS a la
cuenta propietaria. La foto se sube a un bucket privado temporal y la función la
elimina después de enviarla a Aiuta. Solo se admiten fotos JPEG, PNG o WebP de
hasta 10 MB. La retención de los resultados depende de la suscripción de Aiuta.

Los SKU deben existir en el catálogo registrado en Aiuta. El botón
**Probar virtualmente** de cada producto precarga el ID público de la tienda,
que solo funcionará si coincide con un SKU de Aiuta; también puedes editar el
SKU y el nombre del catálogo. Consulta el [flujo y referencia oficial de la
API](https://docs.aiuta.com/api/try-on/).

Para que funcionen las confirmaciones de correo, agrega
`https://calce-matices-publica.onrender.com/**` a **Supabase → Authentication →
URL Configuration → Redirect URLs**.

## Conexión con Supabase

La app puede crear cuentas por correo, iniciar sesión y sincronizar las medidas
y la paleta. Al activar **Recuérdame** en el paso de la foto con una sesión
iniciada, se vinculan a la cuenta la foto, las medidas y la paleta; al volver a
iniciar sesión se recuperan automáticamente. Las fotos se guardan en un bucket
privado de Supabase Storage, con acceso limitado a la cuenta propietaria. Se
admiten fotos JPEG, PNG, WebP, GIF o AVIF de hasta 10 MB.
Sin sesión, las medidas y las fotos recordadas permanecen solo en el navegador.

1. En el panel SQL de Supabase, ejecuta
   [`supabase/schema.sql`](./Calce%20y%20Matices%20Integrado/supabase/schema.sql).
   El esquema actualiza la tabla de perfiles, crea el bucket privado y limita
   mediante RLS el acceso a cada perfil y sus fotos. Si ya ejecutaste una versión
   anterior, vuelve a ejecutar el archivo completo.
2. En la configuración API del proyecto, copia la **publishable key** (o la
   antigua clave `anon`). No uses la clave `service_role`.
3. Copia
   [`.env.example`](./Calce%20y%20Matices%20Integrado/.env.example) como `.env`
   dentro de `Calce y Matices Integrado` y pega allí la
   publishable key. `.env` se excluye de Git. También puedes
   definir `SUPABASE_PUBLISHABLE_KEY` en el entorno; las variables existentes
   del entorno tienen prioridad sobre `.env`.

   ```bash
   cd "Calce y Matices Integrado"
   cp .env.example .env
   # Edita .env y agrega la publishable key del proyecto
   python3 app.py
   ```

   La URL del proyecto ya está configurada como
   `https://twhszjxhmimqlzthlbgy.supabase.co`; se puede cambiar mediante
   `SUPABASE_URL`.
4. En el paso **Medidas**, crea una cuenta o inicia sesión. Si Supabase requiere
   confirmar el correo, revisa el mensaje de confirmación antes de iniciar
   sesión. En el inicio de sesión, **Recuérdame** conserva la sesión entre
   visitas; si lo dejas desmarcado, la sesión termina al cerrar la pestaña.
   Activa **Recordar medidas** para sincronizar las medidas y la paleta.
   **Recuérdame** en el paso de la foto guarda una copia privada en tu cuenta;
   desactivar la opción o eliminar la foto también la borra de Supabase.
5. Si la confirmación por correo está activada, agrega la URL local de la app
   (por ejemplo `http://127.0.0.1:4173/**`) a **Authentication → URL
   Configuration → Redirect URLs** en Supabase.

La publishable key se envía al navegador y no es una clave secreta; la seguridad
depende de RLS y de no exponer nunca una clave `service_role`. La autenticación
usa Supabase JS desde jsDelivr, por lo que requiere conexión a internet.

## API opcional con Modal (pasos 3–5)

El proyecto incluye [`vton_api.py`](./Calce%20y%20Matices%20Integrado/vton_api.py),
una API FastAPI ligera que no carga GPU ni modelos. El botón **Probador**, junto
a **Catálogo**, usa la foto elegida en **Inicio** y permite seleccionar una
prenda del catálogo. Solo las cuentas con sesión iniciada pueden enviar
solicitudes.

**Estado actual:** el endpoint valida las imágenes y devuelve la foto original
con estado `simulation`; todavía no fusiona la prenda. Integrar un modelo VTON
real requerirá una implementación y recursos de cómputo adicionales.

### Paso 3: preparar y configurar la API

Desde la carpeta del proyecto, instala y configura Modal. El token se guarda
como secreto de Modal y protege el endpoint:

```bash
cd "Calce y Matices Integrado"
python3.11 -m pip install --user --upgrade modal fastapi
python3.11 -m modal setup
python3.11 -m modal secret create vton-api-auth VTON_API_TOKEN=elige-un-token-largo
```

Después del despliegue, configura `VTON_API_URL` con la URL base permanente de
Modal (sin `/try-on`) y `VTON_API_TOKEN` con el mismo valor del secreto de Modal
en el `.env` de la app y en las variables de entorno de Render. La clave queda
en el backend; no la publiques en el navegador.

### Paso 4: probar y desplegar

Para obtener una URL temporal que se actualiza al guardar cambios:

```bash
cd "Calce y Matices Integrado"
python3.11 -m modal serve vton_api.py
```

Cuando la inferencia VTON real esté integrada y probada, detén el modo de
desarrollo con `Ctrl+C` y publica la API:

```bash
cd "Calce y Matices Integrado"
python3.11 -m modal deploy vton_api.py
```

Modal entrega una URL permanente con formato
`https://<usuario>--probador-virtual-api-fastapi-app.modal.run`. La ruta de
inferencia es `/try-on`.

### Paso 5: llamar a la API desde el backend

Envía las imágenes de persona y prenda en Base64 junto con la categoría y el
token Bearer. No incluyas el token en el JavaScript público del navegador; llama
a Modal desde un backend propio. El ejemplo Python completo está en la
[guía de Modal del subproyecto](./Calce%20y%20Matices%20Integrado/README.md#api-alternativa-de-probador-virtual-con-modal).
La simulación actual no solicita una GPU, aunque Modal puede cobrar por ejecutar
el endpoint.

Al iniciar, la aplicación intenta abrir la URL en Google Chrome. En VS Code,
selecciona **Medidas: ejecutar en Chrome** en el panel **Ejecutar y depurar** y
presiona `F5`. En macOS también puedes abrir `Iniciar Medidas.command` para
abrir el proyecto en VS Code e iniciar la app; Chrome se abrirá al arrancar el
servidor.

## Estructura del proyecto

- `app.py`: punto de entrada; coordina el inicio del servidor local.
- `medidas/`: perfil corporal, lectura de medidas y recomendación según la tabla estándar.
- `prendas/`: modelo de prenda, catálogo y repositorio Excel.
- `metricas/`: cálculo de holguras, puntuación y diagnóstico.
- `web/`: servidor, plantilla HTML, estilos y recursos de interfaz.
- Las ventanas de bienvenida usan la fuente Rye, incluida en `web/assets/` bajo
  licencia SIL Open Font License; su serif vintage es una alternativa visual,
  no la fuente exacta Fashion Modish de la imagen de referencia.
- `data/Matriz_Medidas_Marcas_Vestua.xlsx`: fuente de productos y variables.
- `data/vestua_images.json`: imágenes de referencia y enlaces a Vestua por marca y categoría.
- `data/vestua_catalog.json`: instantánea de publicaciones únicas de Vestua con título, categoría, talla, precio y URL.
- `data/tiendas_mujer.json`: instantánea de prendas con imagen de Tricot y Paris.
- `scripts/importar_catalogo_mujer.py`: actualiza la instantánea pública de productos.
- `data/Tabla_estandar.xlsx`: tabla estándar de tallas y rangos corporales adjunta.

El catálogo y los factores de calce se cargan desde sus respectivas hojas del
Excel al iniciar la aplicación. Las filas que repiten la misma marca, categoría,
atributos y medidas se cuentan una sola vez, aunque tengan distinta línea o
submarca. La matriz aporta 42 referencias únicas, pero la app solo recomienda
las que tienen una publicación de Vestua enlazada e identificada; actualmente
son 38. El catálogo separado conserva 584 fichas únicas recopiladas el 29 de octubre
de 2026; es una instantánea y no se actualiza automáticamente. La app muestra
solo las publicaciones que tienen una referencia de imagen disponible; el resto
se omite. También se excluye cualquier publicación identificada como calzado.
Desde el catálogo también se puede abrir la colección de mujer de
[Paris](https://www.paris.cl/mujer/) y [Tricot](https://www.tricot.cl/mujer).
La instantánea actual contiene 2.176 fichas con imagen de Tricot y 9.948 de
Paris, recopiladas al recorrer las 304 páginas de la categoría de moda de Paris
(30.349 resultados informados). El importador consulta la API pública de Paris
en lotes de 100 productos y conserva solo fichas con imagen, excluyendo
calzado. Para actualizar los datos públicos, ejecuta
`python3 scripts/importar_catalogo_mujer.py`; el proceso puede tardar varios
minutos debido al volumen de Paris. Al pulsar la imagen de cada tarjeta se abre
la ficha de producto en la tienda de origen.
Las combinaciones sin referencia de medidas no reciben una puntuación de calce.
Los valores de calce provienen de la matriz y son orientativos: no son medidas
verificadas de la publicación enlazada.
El selector de marca comienza en Zara. La marca y el tipo de prenda recomendados
corresponden a una misma referencia elegible: la que obtiene la menor puntuación
al comparar sus medidas con el perfil. Los resultados del carrusel respetan los
filtros seleccionados.
En Inicio, un carrusel adicional recomienda prendas con foto y enlace a su ficha
en Paris y Tricot según el calce estimado y el tipo de prenda seleccionado. Las
medidas se calculan con referencias de la matriz; no son medidas físicas
publicadas por las tiendas.
Las pestañas **Todas**, **Arriba** y **Abajo** filtran por todas las prendas,
prendas superiores (poleras, blusas, tops, blazers y vestidos) o inferiores
(pantalones y jeans), respectivamente. El selector de tipo de prenda muestra
solo las categorías disponibles en el catálogo. Las recomendaciones de
La aplicación pide busto/pecho, cintura y cadera. La tabla estándar usa las
tres medidas para recomendar tallas; la puntuación de calce de las prendas usa
cintura y cadera porque las referencias de Vestua no publican medidas físicas
individuales de busto.
Las medidas de la matriz se repiten entre marcas para cada categoría; por eso,
cuando hay empate, la app muestra todas las marcas con mejor puntuación y no
afirma que una marca ajuste mejor que otra. Estas referencias no sustituyen
medidas verificadas por producto.
Sobre la tabla estándar aparece otro carrusel con las demás prendas cuyo
diagnóstico indica calce compatible o cercano; excluye las opciones ya mostradas
en el carrusel principal y requiere medidas para comparar.
Las tallas se estiman con la tabla estándar adjunta; la matriz no contiene
tablas oficiales específicas por marca, por lo que se debe confirmar la guía
oficial antes de comprar. La conversión a tallas de EE. UU. es aproximada.
Las referencias son orientativas y no garantizan el
calce. Las imágenes enlazan a publicaciones de Vestua de la misma marca y
categoría; son referenciales, no necesariamente la misma prenda de la matriz y
pueden cambiar o dejar de estar disponibles. Si no hay una publicación enlazada
para una combinación, esa referencia no se recomienda.
Junto a cada imagen también se muestra la talla indicada en su publicación
en Vestua; puede ser distinta de la prenda del Excel y cambiar si la publicación
se actualiza.
Los enlaces **Inicio** y **Catálogo** abren vistas separadas; el catálogo
muestra los productos con imagen de las instantáneas de Vestua, Tricot y Paris.
Muestra nueve prendas
por página (3 columnas × 3 filas en
pantallas amplias), con búsqueda, filtro por tipo, paginación y orden por precio
o puntuación. Los filtros y el orden consultan el catálogo completo en el
servidor y solo envían las nueve tarjetas de la página actual al navegador. Las
fichas publicadas no
incluyen medidas físicas cintura/cadera por producto: cuando es posible, la
puntuación usa una referencia del mismo tipo y marca, o una referencia promedio
del catálogo, y se identifica como estimación. No se asignan holguras a
publicaciones sin un tipo comparable. Los precios y tallas proceden de la
consulta del catálogo y pueden cambiar. Se pueden seleccionar varias prendas
para comparar diagnóstico, medidas referenciales y precio; cada enlace lleva a
Vestua para confirmar disponibilidad y completar la compra.
Cada tarjeta indica en la esquina superior derecha el diagnóstico estimado de
calce con las medidas de cintura y cadera ingresadas en Inicio. Si faltan medidas
o una referencia comparable, se informa en la tarjeta en vez de presentar un
resultado como seguro.

La casilla **Recordar** guarda las medidas en el almacenamiento local del
navegador actual. Al desmarcarla, elimina las medidas guardadas en ese navegador.

El filtro de marca y las recomendaciones identifican de forma orientativa el
origen de molde de las marcas incluidas (europeo/Inditex, europeo/británico o
americano). Esta clasificación es informativa: no cambia la comparación ni la
puntuación, que se calculan con las medidas de cada prenda del catálogo. El
catálogo actual no incluye marcas de molde asiático.

## Pruebas

```bash
python3 -m unittest discover -s tests -v
```
