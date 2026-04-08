# Profundización del Desarrollo — Sistema Experto de Asesoría Curricular
## Ingeniería en Datos e Inteligencia Organizacional — Plan 2021ID, Universidad del Caribe

---

## 5.2 Técnicas y herramientas empleadas — Justificación técnica

### Por qué Python como lenguaje principal

Python fue elegido no únicamente por su popularidad, sino porque concentra en un solo ecosistema las tres capacidades que este proyecto necesita simultáneamente: procesamiento de texto no estructurado (expresiones regulares, pdfplumber), análisis y transformación de datos tabulares (pandas, dataclasses) y construcción de agentes inteligentes (motor de reglas de producción). Replicar esta combinación en otro lenguaje habría requerido integrar múltiples plataformas o lenguajes, aumentando la complejidad de mantenimiento sin beneficio real para el dominio del problema.

### Por qué pdfplumber para extracción de PDFs

La institución emite el historial académico y el kardex como archivos PDF generados por su sistema de información interno. Estos documentos no son imágenes escaneadas: contienen texto plano subyacente con una disposición específica por columnas. pdfplumber permite extraer ese texto página por página conservando el orden de lectura y accediendo a metadatos de posición si fuera necesario. Alternativas como PyMuPDF o PyPDF2 fueron descartadas porque pdfplumber proporciona un mejor control sobre la extracción de texto cuando el layout tiene columnas y alineaciones no triviales, que es exactamente la estructura del historial académico de la Universidad del Caribe.

Una limitación importante que se detectó durante el desarrollo es que pdfplumber entrega el texto en codificación Unicode NFD (forma de descomposición canónica), mientras que las cadenas de Python se manejan internamente en NFC (forma compuesta). Esto provocaba que palabras acentuadas como "Tópicos" extraídas del PDF no coincidieran con las cadenas de comparación definidas en el código, causando que el nivel de inglés del estudiante se reportara como cero incluso cuando estaba correctamente registrado en el documento. La solución implementada fue normalizar todo el texto extraído a NFC mediante `unicodedata.normalize('NFC', texto)` antes de realizar cualquier comparación de cadenas. Esta normalización se encapsuló en un método estático `_nfc()` dentro de la clase `HistorialParser`, lo que garantiza que la operación se aplique de forma uniforme en todos los puntos del parser donde se comparan cadenas provenientes del PDF.

### Por qué expresiones regulares (regex) para el parsing

El historial académico no tiene una API de acceso ni viene en un formato estructurado como JSON o XML. Es un documento de texto con una disposición semi-estructurada: encabezados de sección, filas de materias con un patrón consistente y bloques de totales al final. Las expresiones regulares son la herramienta adecuada para este escenario porque permiten describir exactamente el patrón de cada tipo de línea y extraer los grupos de interés (clave, nombre, créditos, calificación) en una sola operación, sin depender de la posición absoluta dentro del documento.

Por ejemplo, el patrón para identificar una fila de materia en el historial tiene la forma:

```
^(\d[\d,]* |(?:\d+ al \d+) )([A-Z]{2,4}\d{4})\s+(.+?)\s+(\d+)(?:\s+(\S+))?\s*$
```

Este patrón captura: el semestre en que fue cursada (que puede ser "1,2" o "5 al 8"), la clave oficial de la materia (dos a cuatro letras seguidas de cuatro dígitos), el nombre completo, los créditos y opcionalmente la calificación obtenida.

### Por qué pandas para el procesamiento de datos académicos

Una vez que el parser extrae los registros de materias individuales, se necesita realizar operaciones de agrupación, filtrado y deduplicación sobre ese conjunto. pandas proporciona el DataFrame como estructura central, que permite:

- **Deduplicación con prioridad**: cuando una materia fue reprobada en un periodo y aprobada en otro posterior, el sistema debe conservar únicamente el registro aprobatorio. Esta operación se realiza agrupando por clave y seleccionando el registro con el estatus más favorable.
- **Cálculo de indicadores por ciclo**: para cada semestre se agrupa el conjunto de materias y se calculan las cantidades de aprobadas, en curso, reprobadas, en recursamiento y pendientes, junto con el porcentaje de avance correspondiente.
- **Detección de periodos sabáticos**: se identifican semestres en los que el estudiante no registró actividad académica, distinguiendo entre periodos regulares e intersemestrales.

Usar pandas evita implementar manualmente estas operaciones con estructuras básicas de Python como listas y diccionarios, reduciendo el riesgo de errores y haciendo el código más legible y verificable.

### Por qué dataclasses para las entidades del dominio

Se utilizaron dataclasses de Python para representar las entidades principales:

- `InfoMateria`: contiene clave, nombre, ciclo, categoría, créditos, calificación y estatus de una materia individual.
- Los datos generales del estudiante: matrícula, nombre normalizado, situación (Regular/Irregular), créditos acumulados y nivel de inglés.

Las dataclasses son preferibles a los diccionarios para este propósito porque proveen tipado explícito, valores por defecto claros y un mecanismo de copia segura entre módulos. Esto facilita que el módulo de parsing entregue un objeto con campos bien definidos al sistema experto, en lugar de un diccionario con claves arbitrarias cuya presencia no está garantizada.

### Por qué Streamlit para la interfaz

El sistema está orientado a dos perfiles de usuario: el asesor académico, que necesita cargar documentos y obtener resultados de forma rápida, y el estudiante, que necesita interpretar su trayectoria sin formación técnica. Streamlit permite construir esta interfaz directamente en Python, sin necesidad de desarrollar un frontend separado en HTML/CSS/JavaScript. Esto tiene implicaciones prácticas importantes: los mismos desarrolladores del sistema experto pueden mantener la interfaz, y los cambios en la lógica de negocio se reflejan inmediatamente en la UI sin un paso de compilación adicional.

La interfaz se organiza en pestañas (tabs) que separan conceptualmente: el resumen del historial, el progreso por ciclo, el sistema experto de recomendación y el módulo de inglés. Las columnas y componentes de Streamlit permiten mostrar métricas, tablas interactivas y gráficas sin necesidad de código adicional de presentación.

Un aspecto de usabilidad implementado durante el desarrollo fue eliminar los botones de procesamiento manual. Originalmente el sistema requería que el usuario presionara un botón para procesar el historial después de cargarlo, y otro botón para ejecutar el sistema experto. Esto se reemplazó por procesamiento automático: el sistema detecta cuándo se sube un archivo nuevo comparando el identificador interno del archivo (`file_id`) contra el último procesado almacenado en la variable de sesión `_historial_file_id`. Si son diferentes, el procesamiento se ejecuta automáticamente. Cuando el usuario cambia de pestaña al sistema experto, las recomendaciones ya están calculadas y se muestran de inmediato.

### Por qué Plotly para las visualizaciones

Para mostrar el progreso académico por semestre se eligió Plotly en lugar de matplotlib porque Plotly genera gráficos interactivos directamente en el navegador. Los gráficos de dona por ciclo permiten al usuario ver la proporción de materias según su estatus (aprobada, en curso, reprobada, pendiente) y pasar el cursor sobre cada sección para ver los detalles. Con matplotlib, este nivel de interactividad habría requerido una integración adicional con JavaScript.

La codificación de colores empleada es: verde para materias aprobadas, amarillo para materias en curso, naranja para materias en recursamiento, rojo para materias reprobadas y gris para materias pendientes. Esta convención se mantiene de forma consistente en todos los gráficos del sistema.

### Por qué JSON para la representación del plan de estudios

El mapa curricular del Plan 2021ID se almacena en un archivo `mapa_curricular_2021ID_real_completo.json` donde cada materia se describe con sus atributos académicos y sus relaciones de seriación. Otros formatos considerados fueron bases de datos relacionales directamente y hojas de cálculo (Excel). JSON fue preferido porque:

- Es legible y editable por el equipo sin necesidad de herramientas especializadas.
- Se carga en memoria como un diccionario de Python en una sola operación, sin necesidad de una capa ORM o queries SQL.
- El motor de reglas del sistema experto puede consultarlo de forma declarativa, recorriendo la lista de materias con filtros simples.
- Es portable: el archivo viaja con el código fuente del sistema sin requerir un servidor de base de datos activo durante el desarrollo.

Adicionalmente se mantienen archivos JSON complementarios: `mapeo_especialidades_2021ID.json` que define las materias de cada orientación (TICS e Inteligencia de Negocios), `electivas_clasificadas.json` que organiza las materias de libre elección por ciclo anual, y `equivalencias_legacy_2021ID.json` que establece la correspondencia entre claves de planes anteriores y el plan 2021ID, permitiendo interpretar correctamente historiales de estudiantes que iniciaron con un plan diferente.

### Por qué PostgreSQL con Supabase para la persistencia

Para el almacenamiento de la información procesada se eligió PostgreSQL por ser un sistema relacional maduro, con soporte para tipos de datos complejos y consultas avanzadas que son útiles para análisis académico. La plataforma Supabase fue elegida como host porque provee PostgreSQL en la nube con una capa de API REST integrada, lo que facilita el despliegue sin necesidad de administrar un servidor propio. SQLAlchemy se usa como ORM para abstraer las operaciones de lectura y escritura.

El sistema mantiene una doble vía de acceso configurada mediante variables de entorno: conexión directa vía SQLAlchemy/psycopg2 para entornos de desarrollo locales, y cliente nativo de Supabase para operaciones en la nube. Las credenciales se gestionan únicamente a través de un archivo `.env` cargado con python-dotenv, evitando que datos sensibles aparezcan en el código fuente.

---

## 5.3.2 (Ampliación) — Procesamiento de documentos académicos

### Manejo de ambigüedades en el parsing

El historial académico presenta varios casos ambiguos que el parser debe resolver sin intervención del usuario:

**Materias con nombre que termina en número**: El regex para extraer calificación puede confundirse cuando el nombre de una materia termina en un dígito, como "Movilidad 1". En este caso el parser puede interpretar el dígito como créditos y lo que sigue como calificación, produciendo un resultado incorrecto. El sistema lo detecta verificando si la "calificación" extraída es un número menor a 7: en ese contexto, los créditos válidos de una materia no son menores a 7 en el plan 2021ID, pero las calificaciones sí pueden serlo. Si se detecta esta condición, el parser reinterpreta la fila asignando el dígito al nombre y tomando el siguiente campo como créditos reales.

**Materias con calificación S/A**: El historial institucional usa "S/A" (Suficiencia Aprobada) para materias validadas por mecanismos alternativos al examen. El parser lo trata como calificación aprobatoria equivalente a cualquier nota numérica mayor o igual a 7.

**Clasificación de estatus a partir de calificación**: La Tabla 2 del documento de desarrollo resume la correspondencia entre los valores que aparecen en el PDF y el estatus asignado. Esta clasificación es necesaria porque el historial no incluye explícitamente la etiqueta "Aprobada" o "Reprobada": el sistema la deduce del valor de la calificación, su ausencia, o la presencia de marcadores institucionales como el asterisco (*) al inicio de la línea.

---

## 5.3.3 (Ampliación) — Sistema experto y validación curricular

### Diseño de la base de conocimientos

La base de conocimientos del sistema experto está formada por dos componentes: las reglas de producción codificadas en Python y el mapa curricular almacenado en JSON. Esta separación es deliberada: las reglas de producción contienen la lógica invariante del proceso de asesoría (cómo se valida la seriación, cómo se detecta el ciclo actual, cómo se aplican las cuotas de electivas), mientras que el mapa curricular contiene los hechos específicos del plan de estudios (qué materias existen, cuáles son sus prerrequisitos, a qué ciclo pertenecen). Si en el futuro se adopta un plan de estudios diferente, basta con proporcionar un nuevo archivo JSON sin modificar las reglas.

### Fase 1 — Determinación del ciclo actual

La determinación del semestre en el que se encuentra el estudiante sigue un algoritmo basado en porcentaje de avance, no en el número de periodos cursados. Esto es relevante porque algunos estudiantes toman periodos sabáticos, se inscriben con carga parcial o recursan materias de semestres anteriores, lo que hace que el tiempo transcurrido no sea un indicador confiable del semestre actual.

El algoritmo recorre los semestres del 1 al 8 de forma secuencial. Para cada semestre evalúa si el estudiante ha tenido contacto con él (tiene al menos una materia aprobada o en curso de ese ciclo). Si no hay contacto, el semestre anterior es el actual. Si hay contacto, calcula el porcentaje de avance sobre las materias básicas del semestre y determina si supera el umbral del 75%. Si lo supera, el semestre se considera concluido y el algoritmo avanza al siguiente. Si no lo supera, ese semestre es el actual.

El umbral del 75% es una decisión de diseño que equilibra dos casos extremos: un umbral del 100% requeriría que el estudiante apruebe absolutamente todas las materias básicas antes de avanzar, lo cual es demasiado estricto y no refleja cómo funcionan las asesorías reales; un umbral del 0% haría que cualquier contacto con un semestre lo marque como concluido, lo cual subestimaría el rezago del estudiante. El 75% fue definido en colaboración con las asesoras académicas como el punto que mejor representa la situación en que un estudiante ya puede cargar materias del siguiente ciclo de forma razonable.

Una distinción importante en este cálculo es el tratamiento diferenciado de materias básicas versus electivas y materias de preespecialidad. En semestres 1 a 4, se incluye un crédito adicional por cada materia de elección libre tomada, porque la oferta académica de esos semestres contempla activamente una o dos electivas. En semestres 5 a 8, el cálculo se realiza exclusivamente sobre materias básicas, porque las electivas y materias de preespecialidad de esos semestres se distribuyen de forma más libre y variable entre los estudiantes, y su ausencia no debe penalizar el avance detectado.

Las constantes que rigen este cálculo son:

```python
EL_RECOMENDADAS_POR_CICLO    = {5: 1, 6: 2, 7: 2, 8: 3}
EL_ACUMULADAS_CICLO          = {4: 0, 5: 1, 6: 3, 7: 5, 8: 8}
PREESP_RECOMENDADAS_POR_CICLO = {1: 0, 2: 0, 3: 0, 4: 0, 5: 1, 6: 1, 7: 1, 8: 2}
PREESP_ACUMULADAS_CICLO       = {1: 0, 2: 0, 3: 0, 4: 0, 5: 1, 6: 2, 7: 3, 8: 5}
```

Estas constantes representan el ritmo ideal de avance que describe el plan de estudios 2021ID: cuántas materias de cada tipo debería haber acumulado un estudiante al finalizar cada semestre si siguiera el plan sin rezagos.

### Fase 2 — Generación de candidatas iniciales

Una vez determinado el ciclo actual, el sistema construye el conjunto de materias candidatas iniciales tomando todas las materias del mapa curricular que pertenezcan al ciclo actual o a ciclos anteriores, y que no estén aprobadas ni en curso. Esta fase no aplica ninguna validación de prerrequisitos todavía: simplemente identifica todas las materias que el estudiante aún no ha acreditado y que corresponden a la parte del plan que ya debería haber cursado.

Este conjunto amplio es el punto de partida para las fases de depuración que siguen. La razón de empezar con un conjunto amplio es que es más fácil eliminar materias que no cumplen condiciones que intentar inferir directamente cuáles sí cumplen, que es el principio de funcionamiento de los sistemas expertos basados en reglas de producción.

### Fase 3 — Regla A: Validación de prerrequisitos

La Regla A elimina del conjunto candidato cualquier materia cuyos prerrequisitos no estén completamente aprobados. Para cada candidata se consulta el mapa curricular y se obtiene la lista de claves de materias prerrequisito. Si alguna de ellas no pertenece al conjunto de materias aprobadas del estudiante, la candidata se descarta.

Esta regla implementa directamente la seriación formal del plan de estudios: una materia solo puede cursarse si el estudiante ya acreditó todo lo que el plan establece como previo. La validación es declarativa: el sistema consulta el campo `requisitos` del JSON sin necesidad de lógica adicional para cada par de materias.

### Fase 4 — Regla B: Resolución de cadenas de seriación mediante ordenamiento topológico

Después de la Regla A, pueden quedar en el conjunto candidato varias materias de una misma cadena de seriación que el estudiante no ha cursado aún. Por ejemplo, si el estudiante no ha cursado Programación I ni Programación II, ambas podrían pasar la Regla A (dependiendo de si el prerrequisito de Programación I ya fue aprobado). Sin embargo, no tiene sentido recomendar Programación II si Programación I tampoco ha sido cursada, porque la seriación lo impide.

La Regla B detecta estas situaciones identificando sub-cadenas dentro del conjunto candidato: si hay dos o más materias de la misma cadena de seriación simultáneamente en el conjunto, se mantiene únicamente la materia base (la de menor avance en la cadena) y se eliminan las que dependen de ella.

Para determinar el orden correcto dentro de cada cadena se utiliza el algoritmo de Kahn, que es una implementación del ordenamiento topológico sobre el grafo dirigido de dependencias. Este algoritmo construye el orden de materias desde la que no tiene prerrequisitos dentro de la cadena (la base) hasta la más avanzada, procesando iterativamente los nodos cuyo grado de entrada cae a cero conforme sus predecesores son procesados.

El uso de un algoritmo de grafos en este punto es necesario porque las cadenas de seriación no son siempre lineales: algunas materias tienen múltiples prerrequisitos o son prerrequisito de múltiples materias posteriores, formando una estructura en árbol o en malla que no puede ordenarse correctamente con una comparación simple por número de ciclo.

### Fase 5 — Regla C: Cuota de materias de elección libre por ciclo anual

El plan 2021ID establece cuotas de materias de elección libre que el estudiante debe acumular a lo largo de su trayectoria:

```python
EL_CUOTAS = {
    1: 2,    # Ciclo anual 1 (semestres 1-2): 2 electivas requeridas
    2: 2,    # Ciclo anual 2 (semestres 3-4): 2 electivas requeridas
    "34": 8  # Ciclos anuales 3+4 (semestres 5-8): 8 electivas requeridas
}
```

La Regla C verifica, para cada ciclo anual, cuántas materias de elección libre ya ha aprobado el estudiante. Si la cuota de un ciclo anual ya está cubierta, las materias de elección libre correspondientes a ese ciclo se eliminan del conjunto candidato, evitando que el sistema recomiende más electivas de las necesarias.

### Fase 6 — Regla D: Filtrado de preespecialidad

A partir del sexto semestre el plan contempla materias de preespecialidad que corresponden a dos líneas de profundización: Tecnologías de la Información y Comunicación (TICS) y Business Intelligence (BI). La Regla D determina en cuál de estas líneas se ha comprometido el estudiante, basándose en las materias de preespecialidad que ya aprobó, y filtra el conjunto candidato en consecuencia.

La lógica implementada contempla cuatro casos:

**Caso A**: el estudiante no ha aprobado ninguna materia de preespecialidad. En este caso no es posible inferir ninguna orientación, por lo que se incluyen materias de ambas líneas en el conjunto candidato. El estudiante puede elegir libremente por cuál comenzar.

**Caso B**: el estudiante ha aprobado materias únicamente de una línea. El conjunto candidato conserva las materias pendientes de esa línea y elimina las materias de la otra línea, ya que la seriación propia de la preespecialidad hace inviable iniciar la segunda línea antes de completar la primera.

**Caso C**: el estudiante tiene avance en ambas líneas sin haber completado ninguna. El conjunto candidato conserva las materias de ambas líneas, porque el estudiante está activamente cursando ambas y es válido recomendar continuidad en cualquiera de ellas.

**Caso D**: el estudiante ha completado todas las materias de una línea. En este caso el conjunto candidato muestra únicamente las materias pendientes de la otra línea, ya que la línea completada no tiene pendientes que recomendar.

La detección de una línea completa se realiza mediante el helper `_especialidad_completa()`, que verifica si todas las claves de materias de una especialidad están presentes en el conjunto de aprobadas del estudiante.

La identificación de la especialidad también se ve reflejada en las prácticas profesionales, cuya clave indica el área correspondiente:

```python
PRACTICAS_PREESP_ESPECIALIDAD = {
    "PID0403": "BUSINESS_INTELLIGENCE",
    "PID0404": "TICS",
}
```

### Fase 7 — Regla E: Habilitación de prácticas de especialidad

La Regla E valida que el estudiante haya aprobado al menos tres materias de preespecialidad antes de que las prácticas de especialidad sean habilitadas como candidatas. Si no se cumple este umbral, las claves `PID0403` y `PID0404` se eliminan del conjunto candidato independientemente del ciclo actual del estudiante.

### Explicación generada al usuario

Una característica del sistema es que no solo muestra la tabla de materias recomendadas, sino que también genera una explicación en lenguaje natural de por qué ese conjunto específico de materias fue seleccionado. Esta explicación se construye dinámicamente a partir de los resultados de cada fase, indicando cuántas materias fueron eliminadas por cada regla y cuál es el estado académico detectado respecto a las líneas de especialidad. La explicación se presenta en un componente desplegable de la interfaz, de modo que el asesor puede consultarla cuando necesite justificar la recomendación ante el estudiante.

---

## 5.3.4 Módulo de idioma — Validación del requisito de inglés

El plan 2021ID establece como requisito adicional que el estudiante acredite una cadena secuencial de seis niveles de inglés, desde Nivel 1 hasta Tópicos 2 (ID0606). El parser extrae el último nivel aprobado directamente del campo que el sistema institucional incluye en el historial académico:

```
Último nivel de Inglés aprobado: Tópicos 2
```

La cadena de niveles y sus códigos equivalentes (incluyendo los del plan anterior con prefijo LI) se define en la clase `HistorialParser`:

```python
CADENA_INGLES = [
    {"nivel": 1, "nombres": ["nivel 1"],             "codigos": ["ID0107", "LI1101"]},
    {"nivel": 2, "nombres": ["nivel 2"],             "codigos": ["ID0207", "LI1102"]},
    {"nivel": 3, "nombres": ["nivel 3"],             "codigos": ["ID0307", "LI1103"]},
    {"nivel": 4, "nombres": ["nivel 4"],             "codigos": ["ID0406"]},
    {"nivel": 5, "nombres": ["tópicos 1", ...],      "codigos": ["ID0507"]},
    {"nivel": 6, "nombres": ["tópicos 2", ...],      "codigos": ["ID0606"]},
]
```

A partir del último nivel detectado, el sistema infiere automáticamente todos los niveles anteriores como aprobados, ya que la cadena es estrictamente secuencial: no es posible haber aprobado Tópicos 1 sin haber aprobado los cuatro niveles previos. Esta inferencia se utiliza para enriquecer el conjunto de aprobadas con los códigos de inglés correspondientes, lo que permite que la Regla A del sistema experto no bloquee el avance de materias que tienen algún nivel de inglés como prerrequisito.

El bug de codificación Unicode descrito en la sección de pdfplumber afectaba específicamente a este módulo: la palabra "Tópicos" extraída del PDF en NFD no coincidía con "Tópicos" definido en el código en NFC, produciendo que el nivel detectado fuera siempre cero. La normalización a NFC aplicada mediante `unicodedata.normalize('NFC', texto)` resolvió el problema definitivamente.

---

## Tabla resumen de tecnologías y su justificación

| Tecnología | Propósito en el sistema | Razón de selección |
|---|---|---|
| Python 3 | Lenguaje principal | Ecosistema unificado para parsing, análisis de datos y agentes inteligentes |
| pdfplumber | Extracción de texto de PDFs | Control sobre la extracción por columnas en PDFs institucionales con layout específico |
| unicodedata (stdlib) | Normalización NFD → NFC | Corrección de inconsistencia de codificación entre pdfplumber y Python |
| re (stdlib) | Parsing basado en patrones | Identificación de patrones semi-estructurados en texto del historial académico |
| pandas | Procesamiento de datos tabulares | Deduplicación, agrupación y cálculo de indicadores sobre registros de materias |
| dataclasses (stdlib) | Modelado de entidades del dominio | Tipado explícito y transferencia segura de datos entre módulos |
| JSON | Representación del plan de estudios | Legible, portable, no requiere servidor, cargable en memoria como dict de Python |
| Streamlit | Interfaz web interactiva | Desarrollo de UI en Python sin frontend separado; facilita mantenimiento |
| Plotly | Visualización de progreso | Gráficos interactivos en navegador sin integración adicional de JavaScript |
| PostgreSQL + Supabase | Persistencia de datos | Base de datos relacional en la nube con API REST integrada |
| SQLAlchemy | ORM para acceso a datos | Abstracción de operaciones DB; doble vía local/nube sin cambiar lógica de negocio |
| python-dotenv | Gestión de credenciales | Variables de entorno desde .env; evita exponer credenciales en código fuente |
| Algoritmo de Kahn | Ordenamiento topológico de cadenas de seriación | Ordena correctamente cadenas con dependencias múltiples (no lineales) |
