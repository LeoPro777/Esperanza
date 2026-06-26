# 3. CATEGORÍA: Especificación Modular y Requerimientos

## 3.1. Listado de Módulos

* **Módulo 01: Buscador Público (Consulta de Personas).**
* **Módulo 02: Panel Administrativo (Autenticación y Carga de Excel).**

## 3.2. Especificación Detallada de Módulos

### 3.2.1. Módulo 01: Buscador Público

* **Requerimientos Funcionales:**
  * El usuario debe poder ingresar un término de búsqueda de mínimo 3 caracteres.
  * El sistema debe mostrar coincidencias si el término concuerda con Nombres, Apellidos o Cédula de Identidad.
  * Si el término es estrictamente numérico y menor a 120, debe evaluar también la coincidencia exacta con la edad.
  * La interfaz debe renderizar una tarjeta con un color visualmente distintivo (Gris Pizarra oscuro `#2c3e50`) si el estado del registro es "Fallecido".

* **Flujo de Datos / Algoritmo:**
  1. El cliente envía un formulario mediante `GET /?q=termino`.
  2. El backend limpia los espacios en blanco del string.
  3. Si es numérico, bifurca la consulta agregando la condición `edad == int(termino)`.
  4. Consulta la base de datos mediante la proyección del índice `$text`.
  5. Retorna la plantilla estructurada con un máximo de 30 resultados ordenados por relevancia.

* **Wireframe / UI Concept:**
  Un encabezado centrado con tipografía del sistema (`sans-serif`), descripción corta de la crisis, barra de búsqueda horizontal con un input nativo y un botón de "Buscar". Abajo, un contenedor vertical inyectando tarjetas apiladas de bordes redondeados con los datos esenciales (Cédula, Ubicación del Hospital, Estado de Salud resaltado en negrita).

### 3.2.2. Módulo 02: Panel Administrativo y Carga Masiva

* **Requerimientos Funcionales:**
  * El operador debe ingresar credenciales válidas en `/admin/login`.
  * El sistema debe persistir el estado de la sesión utilizando cookies seguras.
  * El panel debe permitir arrastrar o seleccionar un archivo en formato `.xlsx` o `.csv`.
  * Al procesar el archivo, debe informar la cantidad exacta de registros agregados con éxito y los errores encontrados fila por fila.

* **Flujo de Datos:**
  1. Operador sube archivo vía `POST /api/admin/cargar-masiva` adjuntando un `multipart/form-data`.
  2. El middleware extrae el token de la cookie de sesión y valida vigencia.
  3. El archivo es mapeado en memoria por `pandas`.
  4. Se limpian los nulos y se estructuran los diccionarios con subdocumentos para la localización.
  5. Se ejecuta el método `insert_many()`.

* **Wireframe / UI Concept:**
  Diseño minimalista. Un botón de "Cerrar sesión". Una caja centralizada con borde discontinuo que dice "Arrastre su archivo Excel aquí o haga clic para buscar". Un botón de acción "Procesar Listado Masivo". Al finalizar, un banner verde con el contador de inserciones exitosas.
