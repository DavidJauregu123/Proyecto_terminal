# 5.3 Motor de Optimización Multiobjetivo y Agente Conversacional

---

## 5.3.5 Generación de recomendaciones académicas

Una vez definido el conjunto de asignaturas elegibles por el sistema experto, se ejecuta el módulo de generación de recomendaciones académicas. Este componente toma como entrada las materias validadas y las cruza con la oferta académica disponible, con el fin de construir cargas posibles para el periodo correspondiente.

Para ello, se implementó un motor de optimización multiobjetivo basado en NSGA-III, orientado a generar combinaciones de secciones que equilibren distintos criterios de decisión. En particular, se busca priorizar las materias más relevantes para la trayectoria del estudiante, favorecer horarios compactos y aproximar la carga al número de asignaturas deseado.

Cada solución propuesta debe cumplir restricciones de validez, como la ausencia de choques de horario, la selección de una sola sección por materia, el respeto al límite de materias y créditos permitidos, y la compatibilidad con la disponibilidad horaria del estudiante. A partir de estas condiciones, el algoritmo genera y depura múltiples combinaciones hasta conservar un conjunto reducido de opciones viables.

Como resultado, el sistema devuelve hasta tres propuestas de carga académica, integradas por una recomendación principal y alternativas complementarias. Estas opciones se presentan junto con indicadores resumidos y una visualización del horario, con el fin de facilitar su interpretación y comparación.

---

### 5.3.5.1 Formulación del problema de optimización

La generación de recomendaciones académicas se formuló como un problema de optimización multiobjetivo, en el que cada solución representa una posible carga académica para el estudiante en un periodo determinado. Este enfoque permite comparar distintas combinaciones de secciones sin depender de un solo criterio de evaluación, lo que resulta adecuado en un contexto donde deben equilibrarse necesidades académicas y condiciones operativas del horario.

La construcción del problema parte de la información previamente validada por el sistema experto y de la oferta académica vigente, a partir de las cuales se define el conjunto de combinaciones que pueden analizarse dentro del proceso de recomendación. La Tabla 7 resume los elementos generales considerados en esta formulación.

**Tabla 7. Elementos generales de la formulación del problema de optimización**

| Elemento | Descripción |
|---|---|
| Entrada del problema | Materias elegibles del sistema experto, oferta académica del periodo y preferencias generales del estudiante. |
| Unidad de análisis | Cada carga académica posible construida mediante la selección de secciones reales. |
| Espacio de búsqueda | Combinaciones generadas a partir de la intersección entre materias elegibles y secciones ofertadas. |
| Mecanismo de comparación | Evaluación multiobjetivo de las cargas generadas para identificar propuestas convenientes. |
| Tipo de salida | Hasta tres recomendaciones de carga académica con distintos compromisos entre los criterios evaluados. |

*Nota. Elaboración propia*

Bajo esta formulación, el objetivo del motor no consiste en obtener una única carga ideal, sino en identificar un conjunto reducido de alternativas viables que ofrezcan diferentes equilibrios entre los criterios considerados. Esto permite que la recomendación final conserve flexibilidad y pueda adaptarse mejor a las necesidades del estudiante.

---

### 5.3.5.2 Funciones objetivo del modelo de optimización

La evaluación de las cargas académicas generadas por el motor de recomendación se basa en tres funciones objetivo, definidas para comparar distintas combinaciones de secciones a partir de criterios relevantes para el proceso de asesoría curricular. Estas funciones permiten valorar cada propuesta no solo por su validez académica, sino también por su conveniencia respecto al avance del estudiante y a la organización del horario.

**Tabla 8. Funciones objetivo del modelo de optimización**

| Función objetivo | Propósito dentro del modelo | Interpretación |
|---|---|---|
| Prioridad académica | Favorecer cargas que incorporen materias con mayor relevancia dentro de la trayectoria del estudiante. | Un mejor valor indica mayor cobertura de asignaturas prioritarias. |
| Compacidad del horario | Reducir la dispersión del horario semanal, penalizando huecos y una distribución extendida en varios días. | Un mejor valor indica un horario más compacto. |
| Cantidad de asignaturas | Aproximar la carga generada al número de materias deseado por el estudiante. | Un mejor valor indica mayor cercanía con la cantidad esperada. |

*Nota. Elaboración propia*

La primera función objetivo corresponde a la **prioridad académica**, la cual busca favorecer las materias que el sistema identifica como más urgentes o estratégicas dentro de la trayectoria escolar del estudiante. De esta manera, el proceso de optimización tiende a privilegiar asignaturas cuyo cursado resulta más conveniente para el avance curricular.

La segunda función objetivo evalúa la **compacidad del horario**, permitiendo diferenciar entre cargas con una distribución más organizada y aquellas que presentan mayor dispersión temporal, ya sea por la presencia de huecos entre clases o por el uso de un mayor número de días en la semana.

La tercera función objetivo considera la **cantidad de asignaturas** incluidas en la propuesta, con el fin de aproximar la carga generada al número de materias deseado por el estudiante. Esto permite que el proceso de recomendación no solo responda a criterios curriculares, sino también a la preferencia general de carga expresada por el usuario.

En conjunto, estas funciones permiten comparar distintas alternativas desde una perspectiva equilibrada, incorporando tanto el valor académico de las materias seleccionadas como la viabilidad práctica de la carga resultante.

---

### 5.3.5.3 Restricciones del modelo de optimización

Además de las funciones objetivo, el proceso de optimización incorpora un conjunto de restricciones que delimitan las combinaciones válidas dentro del espacio de búsqueda. Estas restricciones aseguran que las cargas generadas no solo resulten convenientes desde el punto de vista académico, sino que también puedan cursarse en condiciones reales durante el periodo correspondiente.

Las restricciones aplicadas en el modelo son las siguientes:

- **Ausencia de choques de horario:** No se permite seleccionar secciones cuyos bloques de clase se traslapan en día y hora dentro de una misma carga académica.
- **Selección única por asignatura:** Cada materia puede aparecer como máximo una vez en la propuesta, evitando duplicidades o la inclusión simultánea de varias secciones de una misma asignatura.
- **Límite máximo de materias:** La carga debe respetar el número máximo de asignaturas permitido para el estudiante, considerando los criterios definidos por su situación académica (máximo 7 para alumnos regulares; máximo 4 para alumnos en situación condicional o irregular).
- **Rango de créditos permitido:** La suma total de créditos de la propuesta debe mantenerse dentro del intervalo establecido para la carga académica.
- **Compatibilidad con la disponibilidad horaria:** Todos los bloques de clase de las secciones seleccionadas deben ajustarse a la disponibilidad previamente indicada por el estudiante.

Estas condiciones funcionan como restricciones duras dentro del proceso de optimización. En consecuencia, cualquier combinación que incumpla al menos una de ellas es descartada y no puede formar parte del conjunto final de recomendaciones. Con ello, el modelo reduce el espacio de búsqueda a soluciones factibles y evita generar propuestas inviables para el proceso de inscripción.

---

### 5.3.5.4 Proceso de búsqueda basado en NSGA-III

Una vez definidas las funciones objetivo y las restricciones del modelo, la generación de recomendaciones académicas se realiza mediante un proceso de búsqueda multiobjetivo basado en **NSGA-III** (*Non-dominated Sorting Genetic Algorithm III*). Este enfoque permite explorar distintas combinaciones de secciones y conservar aquellas que presentan mejores equilibrios entre prioridad académica, compacidad del horario y cantidad de asignaturas, sin limitar el resultado a una sola solución.

De manera general, el proceso se desarrolla en las siguientes etapas:

1. **Generación de la población inicial:** Se construye un conjunto inicial de cargas válidas a partir de combinaciones de secciones disponibles, verificando desde el inicio el cumplimiento de las restricciones del modelo.
2. **Evaluación de soluciones:** Cada carga generada se valora con base en las funciones objetivo establecidas, lo que permite medir su conveniencia relativa dentro del proceso de optimización.
3. **Ordenamiento por no dominancia:** Las soluciones se organizan en frentes, de modo que aquellas con mejores compromisos entre los objetivos ocupan los niveles de mayor prioridad dentro de la búsqueda.
4. **Aplicación de operadores evolutivos:** A partir de las soluciones existentes, el algoritmo genera nuevas combinaciones mediante procesos de selección, cruce y mutación, con el fin de ampliar la exploración del espacio de búsqueda.
5. **Depuración y selección final:** Las cargas inválidas o repetidas se eliminan, y se conserva un conjunto reducido de alternativas viables para su presentación al usuario.

Como resultado de este proceso, el sistema obtiene hasta tres propuestas de carga académica con distintos compromisos entre los criterios evaluados. Esto permite ofrecer una recomendación principal y alternativas complementarias, de manera que el estudiante o el asesor dispongan de varias opciones factibles para la toma de decisión.

---

## 5.3.6 Interfaz conversacional e interacción con el usuario

### 5.3.6.1 Descripción general del agente

El sistema incorpora un agente conversacional inteligente cuya función es resolver consultas sobre el expediente académico del estudiante en lenguaje natural. Este componente permite al asesor realizar preguntas específicas — como el avance en créditos, el estado de materias reprobadas o el progreso en las líneas de pre-especialidad — sin necesidad de navegar manualmente entre las distintas secciones del dashboard.

La interfaz se implementó como una pestaña independiente dentro del dashboard de Streamlit, con una ventana de chat que conserva el historial de la conversación durante la sesión activa. Las respuestas emplean formato Markdown con encabezados, listas y barras de progreso textuales, renderizados directamente por el componente `st.markdown`.

---

### 5.3.6.2 Arquitectura del agente

El agente fue construido sobre el framework **LangChain** mediante el patrón **ReAct** (*Reasoning and Acting*), implementado con `create_react_agent` de la biblioteca `langgraph.prebuilt`. Este patrón permite al agente razonar sobre qué herramienta invocar en función de la pregunta recibida, ejecutarla, observar el resultado y decidir si la respuesta es suficiente o si debe invocar herramientas adicionales antes de responder.

La Figura X ilustra el flujo general de procesamiento de una consulta:

```
Pregunta del usuario
        │
        ▼
┌───────────────────────────┐
│   respuesta_local()       │  ← Sin LLM. Responde al instante si
│   Reglas locales + datos  │    coincide con patrones conocidos.
└───────────────────────────┘
        │ None (no coincide)
        ▼
┌───────────────────────────┐
│   Agente ReAct (LLM)      │  ← Razona y decide qué tools invocar.
│   DeepSeek V3 / Gemini    │
└───────────────────────────┘
        │ invoca tools
        ▼
┌───────────────────────────┐
│   Tools (@tool LangChain) │  ← Leen _session_ref (datos reales
│   13 herramientas         │    del alumno en session_state).
└───────────────────────────┘
        │ resultado(s)
        ▼
  Respuesta en Markdown
```

El modelo de lenguaje se accede a través de **OpenRouter**, un proveedor de API que permite utilizar distintos modelos sin cambiar la interfaz de llamada. El modelo activo es `deepseek/deepseek-chat-v3-0324`, configurado con `temperature=0.1` para respuestas deterministas y `max_tokens=1024`. La clave de acceso se gestiona mediante variable de entorno (`OPENROUTER_API_KEY`) y nunca se almacena en el código fuente.

```python
llm = ChatOpenAI(
    model="deepseek/deepseek-chat-v3-0324",
    openai_api_key=settings.OPENROUTER_API_KEY,
    openai_api_base="https://openrouter.ai/api/v1",
    temperature=0.1,
    max_tokens=1024,
)
agent = create_react_agent(model=llm, tools=ALL_TOOLS, prompt=SYSTEM_PROMPT)
```

---

### 5.3.6.3 Mecanismo de compartición de datos (sesión compartida)

El agente no accede directamente a `st.session_state` de Streamlit, ya que los tools de LangChain se ejecutan en un contexto distinto al del componente de UI. Para resolver esto, se implementó un mecanismo de referencia de sesión mediante un diccionario global `_session_ref`, que el dashboard actualiza antes de cada consulta:

```python
# En dashboard/app.py, antes de invocar el agente:
set_session_ref(st.session_state)

# En agents/agente_asesor.py, cada tool lee de _session_ref:
df = _session_ref.get("historial_df")
datos = _session_ref.get("datos_estudiante")
```

Las claves relevantes que los tools consumen de `_session_ref` son:

| Clave | Tipo | Contenido |
|---|---|---|
| `historial_df` | `pd.DataFrame` | Todas las materias del alumno con estatus, calificación y periodo |
| `resultado_experto` | `dict` | Candidatas, semestre detectado, debug del sistema experto |
| `datos_estudiante` | `DatosEstudiante` | Promedio, matrícula, situación académica |
| `creditos_totales` | `int` | Total de créditos del plan (424) |
| `creditos_acumulados` | `int` | Créditos aprobados hasta el momento |

---

### 5.3.6.4 Herramientas disponibles

El agente dispone de 13 herramientas especializadas, cada una decorada con `@tool` de LangChain. El decorador expone la función al agente junto con su docstring, que actúa como descripción semántica para que el modelo decida cuándo invocarla. La Tabla 9 describe las herramientas implementadas.

**Tabla 9. Herramientas del agente conversacional**

| Herramienta | Descripción funcional |
|---|---|
| `resumen_estudiante` | Datos generales: matrícula, nombre, promedio, situación académica, semestre actual. |
| `diagnostico_academico` | Estado completo: aprobadas, reprobadas, en curso, alertas de tercera oportunidad. |
| `buscar_materia` | Busca por clave o nombre; devuelve prerequisitos, materias dependientes e impacto en cascada si se reprueba. |
| `consultar_historial` | Lista materias filtradas por estatus (APROBADA / REPROBADA / EN_CURSO). Sin límite de filas. |
| `consultar_candidatas` | Materias candidatas del sistema experto con su nivel de prioridad (P1–P6) y razón. |
| `comparar_carga` | Compara materias actualmente en curso contra las recomendadas por el sistema experto. |
| `consultar_cargas` | Resumen de créditos e materias en el periodo activo. |
| `consultar_eleccion_libre` | Estado de Elección Libre por ciclo anual: cuota, usadas, disponibles. |
| `consultar_preespecialidades` | Progreso en cada línea de pre-especialidad con barras textuales (`█░`) y listas de materias aprobadas, reprobadas y pendientes. |
| `consultar_por_periodo` | Materias cursadas en un periodo específico (formato AAAAPP). |
| `consultar_cocurriculares` | Estado de inglés (nivel actual / requerido) y actividades extra-curriculares. |
| `consultar_creditos_categoria` | Progreso de créditos por categoría (Básicas, EL, Pre-especialidad, Co-curricular) con barras de progreso y "faltan X". |
| `buscar_por_calificacion` | Busca todas las materias del historial donde la calificación coincide exactamente con un valor numérico dado. |

*Nota. Elaboración propia*

---

### 5.3.6.5 Sistema de respuesta local sin LLM

Con el objetivo de minimizar la latencia y el costo de las consultas frecuentes, el sistema implementa un mecanismo de respuesta local que opera enteramente sin invocar el modelo de lenguaje. Este mecanismo se ejecuta antes de la llamada al agente y, si produce un resultado, lo devuelve de inmediato.

El sistema de respuesta local se organiza en tres capas:

**Capa 1 — Consultas directas de datos del estudiante (`_consulta_datos_local`)**

Responde preguntas cuya respuesta se obtiene directamente del `historial_df` o de las claves de `_session_ref`, sin necesidad de razonamiento:

- *¿Cuántas materias ha reprobado?* → filtra `df[estatus == "REPROBADA"]`
- *¿Cuántos créditos lleva?* → lee `creditos_acumulados / creditos_totales`
- *¿Cuál es su promedio?* → lee `datos_estudiante.promedio_general`
- *¿Qué materias lleva en curso?* → filtra `df[estatus == "EN_CURSO"]`
- *¿Tiene alguna materia donde sacó 7?* → invoca `buscar_por_calificacion` directamente

La detección de preguntas de calificación numérica utiliza una expresión regular que identifica patrones del tipo *"sacó 7"*, *"calificación de 8"* o *"con nota 6"*:

```python
_num_match = re.search(
    r'\b(saco|obtuvo|tiene|calificacion de|nota de)\s*([0-9]+(?:\.[0-9]+)?)\b', q
)
```

**Capa 2 — Simulador de impacto de reprobación (`_detectar_simulacion`)**

Detecta preguntas del tipo *"¿qué pasa si reprueba Álgebra Lineal?"* mediante palabras clave de simulación y extrae la materia mencionada. Calcula el impacto en cascada directamente sobre el mapa curricular, sin consultar el LLM.

**Capa 3 — Reglas del reglamento académico (`_REGLAS_LOCALES`)**

Un conjunto de pares `(palabras_clave, respuesta)` que cubre preguntas frecuentes sobre políticas institucionales: número máximo de materias, oportunidades de reprobación, condiciones de baja definitiva, requisitos de egreso, entre otros. Se expanden mediante un diccionario de sinónimos (`_SINONIMOS`) que permite que el usuario use variantes coloquiales y sean reconocidas.

Si ninguna de las tres capas produce una respuesta, la pregunta es derivada al agente LangChain con el historial completo de la conversación.

---

### 5.3.6.6 Prompt del sistema y base de conocimiento

El comportamiento del agente se guía mediante un prompt de sistema almacenado en `agents/knowledge_base.py` como la constante `SYSTEM_PROMPT`. Este prompt cumple dos funciones: delimitar el rol del agente (asesor curricular del plan IDeIO 2021) y documentar las reglas académicas que el modelo puede utilizar directamente en sus respuestas, sin necesidad de invocar herramientas.

El prompt incluye las siguientes secciones:

- **Instrucciones de respuesta:** idioma, concisión, prohibición de inventar datos, manejo de reglas no documentadas.
- **Estructura del plan 2021ID:** 8 semestres, 86 materias, ~404 créditos, categorías de materias.
- **Reglas de reprobación y oportunidades:** 3 intentos máximos, criterios de tercera oportunidad y baja definitiva.
- **Lógica de seriación:** prerequisitos, materias cuello de botella, impacto en cascada.
- **Situaciones académicas:** Regular, Condicional, Irregular y sus restricciones de carga.
- **Requisitos de egreso:** inglés (Tópicos 2 = nivel 6/6), actividad deportiva, actividad cultural.
- **Guía de razonamiento:** instrucciones sobre cómo combinar datos de herramientas con reglas del prompt para construir respuestas coherentes.

---

### 5.3.6.7 Gestión del historial de conversación

El agente mantiene el historial de la conversación en `st.session_state["chat_history"]` como una lista de objetos `HumanMessage` y `AIMessage` de LangChain. Antes de cada invocación, el historial se pasa al agente para que disponga del contexto de la interacción previa.

Para evitar que el contexto crezca indefinidamente y supere el límite de tokens del modelo, se aplica un mecanismo de recorte (`_trim_history`) que elimina los mensajes más antiguos cuando el tamaño total supera los 12 000 caracteres, conservando siempre los intercambios más recientes.

```python
messages = _trim_history(chat_history) + [HumanMessage(content=pregunta)]
resultado = agent.invoke({"messages": messages})
```

---

### 5.3.6.8 Formato de salida

Las respuestas del agente se procesan mediante la función `_extraer_texto`, que convierte saltos de línea simples (`\n`) en saltos de línea Markdown (`  \n`) para garantizar que el componente `st.markdown` los renderice correctamente. Las herramientas `consultar_preespecialidades` y `consultar_creditos_categoria` producen respuestas con:

- Encabezados `###` por sección o línea de especialidad.
- Barras de progreso textuales con carácter de bloque: `████░░░░░░░░` (llenos = aprobados, vacíos = pendientes).
- Listas de materias con emojis de estado: ✅ aprobada, ❌ reprobada, ○ pendiente.
- Separadores `---` entre secciones.
- Indicadores de estado con emoji: ✅ Completada, 🟡 En progreso, ⚪ Pendiente.

Ejemplo de salida de `consultar_creditos_categoria`:

```
### Progreso hacia la graduación
**180 / 424 créditos acumulados**
`████████░░░░░░░░░░░░` 42.5%
Faltan **244 créditos** para completar la carrera.

---

**Desglose por categoría:**

**Materias Básicas** 🟡 En progreso
`██████░░░░░░` 156/316 cr (49.4%) — faltan 160

**Elección Libre** 🟡 En progreso
`██░░░░░░░░░░` 24/150 cr (16.0%) — faltan 126
```
