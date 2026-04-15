# Agente Conversacional Inteligente — Notas para la reunión

---

## ¿Qué es un agente inteligente conversacional?

No es un chatbot. Un chatbot solo genera texto basado en lo que el usuario escribe.
Un **agente inteligente** puede tomar decisiones sobre qué acciones ejecutar, en qué orden,
y usar herramientas reales (como el sistema experto o el generador de cargas) para responder.

La diferencia clave:
- Chatbot → responde con texto
- Agente → razona, decide, ejecuta herramientas, interpreta resultados, responde

---

## Conceptos que hay que saber

### LLM (Large Language Model)
Es el "cerebro" del agente. Es un modelo de lenguaje grande (como Claude de Anthropic o GPT-4
de OpenAI) que entiende y genera texto. El agente lo usa para razonar sobre qué herramienta
llamar y cómo interpretar los resultados antes de responder al usuario.

### Herramienta (Tool)
Una función de Python que el LLM puede invocar. Por ejemplo: ejecutar el sistema experto,
generar cargas con NSGA-III, consultar el mapa curricular. El LLM no la ejecuta él mismo —
decide cuándo usarla y con qué parámetros, y el código Python la ejecuta.

### Prompt del sistema (System Prompt)
Instrucciones que se le dan al LLM al inicio para definir su rol, límites y comportamiento.
Ejemplo: "Eres un asesor académico del plan 2021ID. Solo respondes sobre materias, seriación
y carga académica. No inventes información — usa siempre las herramientas disponibles."

### Memoria (Memory)
Mecanismo para que el agente recuerde lo que se dijo antes en la misma conversación.
Sin memoria, cada mensaje se trata como una conversación nueva y el agente olvidaría que
el alumno ya dijo que es de TICS o que solo tiene disponibilidad por las mañanas.

Tipos relevantes:
- **Buffer memory**: guarda toda la conversación textualmente
- **Summary memory**: guarda un resumen de lo hablado (útil si la conversación es larga)

### Razonamiento ReAct (Reason + Act)
Patrón de diseño para agentes. El ciclo es:
1. **Pensar** → el LLM razona sobre qué necesita para responder
2. **Actuar** → llama una herramienta
3. **Observar** → recibe el resultado de la herramienta
4. Repite hasta tener suficiente información para responder

Ejemplo en el proyecto:
> Usuario: "¿Qué materias puedo tomar?"
> Agente piensa: "Necesito el historial del alumno"
> Agente actúa: llama tool_sistema_experto()
> Agente observa: recibe lista de candidatas
> Agente responde: "Puedes tomar estas materias: ..."

### Agente Reflexivo (Reflexion)
Antes de entregar una respuesta, el agente la evalúa críticamente.
Se pregunta: "¿Tiene sentido esto? ¿Estoy recomendando algo que ya cursó el alumno?"
Si detecta inconsistencia, vuelve a consultar herramientas o reformula.

Es valioso en asesoría académica porque un error tiene consecuencias reales
(el alumno podría inscribir mal).

### LangChain
Framework de Python que facilita la construcción de agentes con LLM.
Proporciona las piezas ya construidas: conectores a LLMs, sistema de herramientas,
memoria, patrones de razonamiento. En vez de programar todo desde cero, se configura.

### LangGraph
Extensión de LangChain para agentes más complejos con múltiples componentes.
Modela el flujo del agente como un grafo dirigido con nodos (estados) y aristas (transiciones).
Permite ciclos, condiciones y múltiples agentes coordinados.

---

## Arquitecturas de agentes inteligentes

Existen varias formas de diseñar un agente. Aquí están las principales:

---

### 1. Agente Reactivo Simple (ReAct)
**¿Qué hace?** Recibe un mensaje, razona un paso, ejecuta una herramienta, observa el resultado y repite hasta poder responder.

**Ciclo:** Pensar → Actuar → Observar → Pensar → Actuar → ... → Responder

**Ventaja:** Sencillo de implementar, funciona bien para preguntas directas.
**Limitación:** No recuerda nada de mensajes anteriores. Cada consulta es independiente.

**Ejemplo:**
> "¿Qué materias puedo tomar?" → llama sistema experto → responde → fin.
> Si en el siguiente mensaje dices "y en vespertino" no sabe a qué te refieres.

---

### 2. Agente con Memoria (ReAct + Memory)
**¿Qué hace?** Igual que ReAct pero mantiene el hilo de la conversación. Recuerda lo que se dijo antes: que el alumno es de TICS, que prefiere turno matutino, que ya se revisó su historial.

**Tipos de memoria:**
- *Buffer*: guarda toda la conversación (costoso si es muy larga)
- *Summary*: guarda un resumen comprimido de lo hablado (más eficiente)
- *Entity*: extrae y guarda datos clave mencionados (nombre del alumno, especialidad, etc.)

**Ventaja:** El usuario no tiene que repetir contexto en cada mensaje.
**Limitación:** Sin reflexión, puede responder con confianza aunque el resultado de una herramienta sea inconsistente.

---

### 3. Agente Reflexivo (Reflexion)
**¿Qué hace?** Después de obtener una respuesta, el agente la evalúa críticamente antes de entregarla. Se pregunta si tiene sentido, si hay inconsistencias, si debería volver a consultar alguna herramienta.

**Ciclo extra:** ... → Respuesta borrador → ¿Es correcta? → Si no: revisar → Respuesta final

**Ventaja:** Reduce errores en dominios donde equivocarse tiene consecuencias (como asesoría académica). Si el sistema experto devuelve una materia que el alumno ya cursó, el agente lo detecta antes de decírselo.
**Limitación:** Más lento y consume más tokens (más costo) por el paso adicional de autoevaluación.

---

### 4. Plan-and-Execute (Planificador + Ejecutor)
**¿Qué hace?** Separa el razonamiento en dos fases. Primero genera un plan completo de pasos ("paso 1: obtener historial, paso 2: ejecutar sistema experto, paso 3: filtrar por disponibilidad...") y luego los ejecuta uno por uno.

**Ventaja:** Bueno para consultas complejas que requieren muchas operaciones dependientes. El plan es visible e interpretable.
**Limitación:** Si el plan falla a la mitad (por ejemplo una herramienta devuelve algo inesperado), replanificar puede ser difícil.

---

### 5. Multi-Agente con Orquestador (LangGraph)
**¿Qué hace?** Varios agentes especializados coordinados por un agente orquestador. Cada agente domina un área: uno el sistema experto, otro el generador de cargas, otro preguntas generales sobre el plan de estudios. El orquestador decide a cuál delegar según la pregunta.

**Diagrama:**
```
Usuario → Orquestador → Agente Sistema Experto
                      → Agente Generador de Cargas
                      → Agente Mapa Curricular
                      → Agente Preguntas Generales
```

**Ventaja:** Cada agente está muy enfocado, menor probabilidad de confusión. Escala bien si el sistema crece.
**Limitación:** Mayor complejidad de implementación y mantenimiento. El orquestador también puede equivocarse al delegar.

---

### 6. Agente con RAG (Retrieval-Augmented Generation)
**¿Qué hace?** Antes de responder, el agente busca en una base de documentos (reglamentos, plan de estudios, fichas de materias) los fragmentos más relevantes y los incluye como contexto para el LLM.

**Ventaja:** El agente puede responder sobre documentos específicos sin necesidad de haberlos "memorizado" en el entrenamiento del LLM.
**Limitación:** Requiere construir y mantener una base de vectores (vector store) con los documentos del dominio.

---

## Arquitectura propuesta para el proyecto

### Opción A — Un agente general (recomendada para empezar)

Un solo agente con acceso a todas las herramientas del sistema.
El usuario puede preguntar cualquier cosa desde cualquier pestaña
y el agente decide qué herramienta usar.

```
Usuario pregunta
      ↓
  Agente ReAct + Memoria
      ↓
¿Qué herramienta necesito?
  ├── Sistema Experto → ¿qué materias puedo tomar?
  ├── Generador NSGA-III → ¿cómo quedaría mi carga?
  ├── Mapa Curricular → ¿qué requisitos tiene esta materia?
  └── Estado del Alumno → ¿cuántos créditos lleva?
      ↓
Interpreta el resultado
      ↓
Responde en lenguaje natural
```

**Ventaja**: más simple de implementar, todo el contexto en un solo lugar.
**Desventaja**: el prompt puede volverse complejo si se especializa mucho.

---

### Opción B — Un agente por sección

Cada pestaña del dashboard tiene su agente especializado:
- Agente del Sistema Experto: solo responde sobre candidatas y seriación
- Agente del Generador: solo responde sobre horarios y cargas
- Agente del Mapa: solo responde sobre el plan curricular

Un orquestador decide a cuál agente delegar según la pregunta del usuario.

**Ventaja**: cada agente está muy enfocado, menos probabilidad de confusión.
**Desventaja**: mayor complejidad, más difícil de implementar en el tiempo disponible.

---

### Recomendación

Para el proyecto terminal, **Opción A con reflexión ligera**:
- Un agente general con ReAct + Memoria
- Antes de responder verifica que la información que da sea consistente con el historial real
- Se conecta a Claude o GPT-4o vía API
- Las herramientas son las funciones Python que ya existen en el proyecto

La Opción B se puede mencionar como trabajo futuro o como arquitectura escalable.

---

## ¿Cómo se conecta al LLM?

Se necesita una API key del proveedor (Anthropic para Claude, OpenAI para GPT-4).
El agente envía llamadas HTTP al servicio del LLM — no corre el modelo localmente.
Para demostraciones locales sin internet existe Ollama (modelos que corren en la máquina),
aunque con menor calidad de razonamiento.

Costo estimado para pruebas y demo: muy bajo, unos pocos dólares en total.

---

## Qué decirle al asesor hoy

1. Se investigó el patrón ReAct como base del agente (Reason + Act)
2. Se agregará memoria de conversación para que el agente recuerde el contexto del alumno
3. Se puede implementar reflexión para validar las recomendaciones antes de entregarlas
4. Las herramientas del agente son las funciones ya existentes: sistema experto y generador de cargas
5. La discusión es si va un agente general o uno por sección — ambas son viables
6. Se usará LangChain como framework, conectado a Claude o GPT-4o
7. La Opción B (multi-agente con LangGraph) es una arquitectura escalable para trabajo futuro

---

## Lecturas de referencia

- ReAct: Synergizing Reasoning and Acting in Language Models (Yao et al., 2022)
- Reflexion: Language Agents with Verbal Reinforcement Learning (Shinn et al., 2023)
- Documentación LangChain Agents: https://python.langchain.com/docs/modules/agents/
- LangGraph: https://langchain-ai.github.io/langgraph/

---

## Lo que decirle al asesor (guión para la reunión)

---

Asesor, estuve investigando sobre las arquitecturas de agentes inteligentes y encontré
varias opciones relevantes para el proyecto.

La primera es el **agente reactivo simple, o ReAct**. Este recibe un mensaje, hace un
razonamiento, actúa — lo cual puede ser ejecutar una herramienta como el sistema experto —,
observa el resultado y repite el ciclo hasta tener una respuesta. Es simple pero tiene una
limitación importante: no recuerda mensajes anteriores, cada consulta es independiente.
Funcionaría para preguntas directas como "¿qué materias puedo tomar?", donde llama al
sistema experto y responde. Pero si en el siguiente mensaje el alumno dice algo que hace
referencia al mensaje anterior, como "¿y cuáles hay en vespertino?", el agente no sabría
a qué se refiere.

Por eso existe el **agente con memoria**, que es ReAct más un componente de memoria.
Este sí mantiene el hilo de la conversación. La limitación es que no tiene reflexión,
o sea que puede responder con confianza aunque el resultado no sea del todo correcto.

Ahí entraría el **agente reflexivo**: antes de entregar una respuesta, la evalúa
críticamente. Si detecta alguna inconsistencia — por ejemplo, que está recomendando
una materia que el alumno ya cursó — vuelve a revisar antes de responder. Esto es
importante en un sistema de asesoría porque un error tiene consecuencias reales.

También está el **multi-agente con orquestador**, que usa LangGraph. Aquí varios agentes
especializados son coordinados por un agente orquestador. Cada agente domina un área:
uno el sistema experto, otro el generador de cargas, otro el mapa curricular. El
orquestador decide a cuál delegar según la pregunta del usuario. Es la arquitectura
más potente pero también la más compleja.

Y por último el **agente con RAG** (Retrieval-Augmented Generation): antes de responder,
el agente busca en una base de documentos — como el reglamento o las fichas de materias —
los fragmentos más relevantes y los incluye como contexto para el LLM.

---

Después de revisar todo esto, creo que una buena opción para el proyecto sería un
**agente general con ReAct más memoria**, donde el agente tiene acceso a todas las
herramientas del sistema ya existente: el sistema experto, el generador de cargas,
el mapa curricular. Sería un solo agente que razona sobre cuál herramienta usar según
lo que pregunta el alumno o el asesor.

La duda que me queda es si conviene tener un agente general para todo el sistema o
uno por sección. Técnicamente ambas son viables — la de un agente general es más
sencilla de implementar; la de uno por sección permite que cada agente sea más
especializado pero requiere más trabajo. Lo dejo a su consideración para ver qué
enfoque prefiere.

---

**Nota aclaratoria (para no confundirse en la reunión):**
El "agente general con ReAct + memoria" NO es lo mismo que el orquestador.
En ReAct hay un solo agente que tiene varias herramientas y decide internamente cuál usar.
En el orquestador hay múltiples agentes separados y un agente adicional cuyo único trabajo
es decidir a cuál de los otros delegar la pregunta. Son niveles de complejidad distintos.

