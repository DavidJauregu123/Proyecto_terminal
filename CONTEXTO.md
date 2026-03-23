# CONTEXTO DEL PROYECTO — Sistema Experto de Seriación Curricular
**Universidad del Caribe · Ingeniería en Datos (Plan 2021ID)**

> Este documento describe la arquitectura, la lógica de negocio y las decisiones técnicas del sistema. Está pensado para que cualquier colaborador pueda incorporarse al proyecto sin necesitar revisar el historial completo de cambios.

---

## 1. ¿Qué hace el sistema?

El sistema analiza el PDF del historial académico (y opcionalmente el kardex) de un alumno de la carrera **Ingeniería en Datos (plan 2021ID)** y produce:

1. **Semestre actual** del alumno (1-8), determinado automáticamente por sus aprobadas.
2. **Materias candidatas** que el alumno puede inscribir en el próximo período, respetando seriación, prerequisitos y cuotas del plan de estudios.
3. **Progreso visual** por semestre y por ciclo anual (donas, tablas).
4. **Estado de requisitos adicionales**: inglés, actividades deportivas, culturales.
5. **Avance en pre-especialidades** y recomendación de línea de titulación.

---

## 2. Estructura del proyecto

```
proyecto terminal/
├── agents/
│   └── sistema_experto_seriacion.py   ← Núcleo del sistema experto
├── dashboard/
│   └── app.py                         ← Aplicación Streamlit (UI)
├── parsers/
│   ├── historial_parser.py            ← Extrae materias del PDF de historial
│   └── kardex_parser.py              ← Extrae materias del PDF de kardex
├── services/
│   ├── processor.py                   ← Calcula progreso por ciclo/semestre
│   ├── local_database.py             ← BD local (SQLite)
│   └── seriacion_service.py          ← Wrapper del sistema experto
├── data/
│   ├── mapa_curricular_2021ID_real_completo.json  ← Fuente de verdad del plan
│   ├── mapeo_especialidades_2021ID.json           ← Claves por especialidad
│   ├── mapeo_cadenas_2021ID.json                  ← Cadenas de seriación
│   └── equivalencias_legacy_2021ID.json           ← Equivalencias plan antiguo
├── config/
│   └── settings.py
└── requirements.txt
```

---

## 3. Flujo de datos

```
PDF Historial ──► HistorialParser ──► materias con estatus (APROBADA/PENDIENTE)
                                   ──► nivel_ingles_aprobado (int 0-6)
                                   ──► ingles_completo (bool)
                                   ──► codigos_ingles_aprobados (set)

PDF Kardex ──► KardexParser ──► materias con periodo, calificación, EN_CURSO

Ambos feeds ──► AcademicProcessor ──► progreso por ciclo/semestre
             ──► sistema_experto   ──► candidatas finales + debug info
```

El sistema da prioridad al **historial académico** como fuente de verdad para las aprobadas. El kardex aporta el detalle de períodos y el estado EN_CURSO del semestre activo.

---

## 4. Lógica del Sistema Experto

### 4.1 Detección del semestre actual (`detectar_ciclo_actual`)

Se recorren los semestres del 1 al 8. Para cada semestre:

- Si el alumno no tiene ninguna materia en contacto (aprobada o en curso) → se detiene. El semestre anterior es el actual.
- Si tiene contacto → se calcula el porcentaje de avance:

**Semestres 1-4:**
```
total_ciclo    = básicas_del_semestre + 1  (una EL entra en el umbral)
cursadas_total = básicas_aprobadas_o_en_curso + crédito_EL
porcentaje     = cursadas_total / total_ciclo
```
El crédito EL es 0 o 1: cuenta 1 si el alumno tiene al menos `ciclo` materias de EL aprobadas de los semestres 1-4.

**Semestres 5-8:**
```
total_ciclo    = básicas_del_semestre  (solo básicas, sin EL ni PREESP)
cursadas_total = básicas_aprobadas_o_en_curso
porcentaje     = cursadas_total / total_ciclo
```

Si `porcentaje < 0.75` → ese es el semestre actual. Si llega a 0.75 → sube al siguiente.

**Razón de diseño:** En los últimos dos ciclos anuales el escenario es muy variable (pre-especialidades, prácticas, EL libres). Usar solo básicas evita que el sistema detecte un semestre inflado por optativas.

### 4.2 Generación de candidatas iniciales

Se toman todas las materias del plan cuyos `ciclo <= ciclo_actual` que no estén aprobadas ni en curso. Esto incluye materias rezagadas de semestres anteriores.

### 4.3 Regla A — Prerequisitos

Se elimina cualquier candidata cuyo prerequisito directo no esté en el conjunto de aprobadas. Los prerequisitos están definidos en `mapa_curricular_2021ID_real_completo.json` bajo la clave `"prerequisitos": [...]`.

### 4.4 Regla B — Cadenas de seriación

Algunas materias forman cadenas secuenciales definidas en `mapeo_cadenas_2021ID.json`. Si en la cadena `[A → B → C]` solo `A` está aprobada, solo `B` es candidata; `C` se elimina aunque técnicamente tenga a `B` como prerequisito cumplido, porque el sistema requiere avanzar de uno en uno dentro de una cadena.

### 4.5 Regla C — Cuota de Elección Libre

El plan tiene cuotas de materias de Elección Libre (EL) por ciclo anual:

| Ciclo anual | Semestres | Cuota EL |
|---|---|---|
| 1 | 1-2 | 2 materias |
| 2 | 3-4 | 2 materias |
| 3+4 | 5-8 | 8 materias |

Si la cuota de un ciclo anual ya está cubierta con aprobadas, se eliminan las candidatas EL de ese mismo ciclo anual para no sobrepasar la cuota.

### 4.6 Regla D — Pre-especialidades

El plan 2021ID tiene dos líneas de titulación:

| Especialidad | Clave PID | Materias propias |
|---|---|---|
| TICS | PID0404 | ID3416, ID3417, ID3418, + 2 más |
| BUSINESS_INTELLIGENCE | PID0403 | ID3420, ID3421, ID3422, + 2 más |

**Lógica de filtrado según avance del alumno:**

| Situación | Qué recomienda el sistema |
|---|---|
| Sin ninguna preesp aprobada | Muestra materias de **ambas** líneas |
| Avance solo en una línea (no terminada) | Solo muestra materias de **esa línea** |
| Avance en **ambas** líneas (ninguna terminada) | Muestra materias de las **dos** |
| Una línea ya **completada** | Solo muestra pendientes de la **otra** (o nada si ambas completas) |

Cuando una línea se completa y el alumno tiene pendientes de la otra, esas pendientes pueden computarse como Elección Libre del ciclo 3/4 según el reglamento.

### 4.7 Regla E — Prácticas de pre-especialidad (PID)

Las prácticas profesionales (PID0403 / PID0404) solo son candidatas si:

1. La especialidad de la práctica coincide con la detectada para el alumno.
2. El alumno tiene ≥ 3 materias de esa pre-especialidad aprobadas o en curso.
3. La práctica de la otra especialidad no está ya en su trayectoria.

---

## 5. Módulo de Inglés

El historial PDF contiene al final la línea:

```
Último nivel de Inglés aprobado: Tópicos 2
```

La cadena de niveles (1 → 6) es:

| Nivel | Nombre | Clave plan |
|---|---|---|
| 1 | Nivel 1 Inglés | ID0107 / LI1101 |
| 2 | Nivel 2 Inglés | ID0207 / LI1102 |
| 3 | Nivel 3 Inglés | ID0307 / LI1103 |
| 4 | Nivel 4 Inglés | ID0406 |
| 5 | Tópicos Selectos I | ID0507 |
| 6 | Tópicos Selectos II | ID0606 |

`nivel_ingles_aprobado` es un `int` (0-6). `ingles_completo = True` cuando el nivel es ≥ 6.

**Bug corregido:** pdfplumber extrae texto en Unicode **NFD** (caracteres acentuados como combinación de base + acento), mientras que las cadenas Python son **NFC** (carácter compuesto). La comparación `"tópicos 2" in texto_pdf` fallaba silenciosamente. La corrección fue normalizar a NFC antes de cualquier comparación (`unicodedata.normalize('NFC', s)`).

**Regla de la escuela:** un alumno puede acreditar varios niveles de golpe si demuestra nivel suficiente. El sistema acepta que "Tópicos 2" en el historial implica que todos los niveles anteriores también están cubiertos, y los marca como aprobados automáticamente.

---

## 6. Progreso por ciclo y semestre

### Constantes activas en `sistema_experto_seriacion.py`

```python
# EL: solo se acumula para semestres 5-8
EL_RECOMENDADAS_POR_CICLO = {5: 1, 6: 2, 7: 2, 8: 3}
EL_ACUMULADAS_CICLO       = {4: 0, 5: 1, 6: 3, 7: 5, 8: 8}

# PREESP: 0,0,0,0,1,1,1,2 materias recomendadas por semestre
PREESP_RECOMENDADAS_POR_CICLO = {1: 0, 2: 0, 3: 0, 4: 0, 5: 1, 6: 1, 7: 1, 8: 2}
PREESP_ACUMULADAS_CICLO       = {1: 0, 2: 0, 3: 0, 4: 0, 5: 1, 6: 2, 7: 3, 8: 5}

# Cuotas de Elección Libre por ciclo anual
EL_CUOTAS = {1: 2, 2: 2, "34": 8}
```

### Split de EL early/late

Para evitar que las EL tomadas en semestres 1-4 inflen el crédito de los semestres 5-8, se separan dos pools:
- `el_claves_early`: EL cuyo `ciclo` en el mapa es ≤ 4
- `el_claves_late`: EL cuyo `ciclo` en el mapa es ≥ 5

### `calcular_progreso_por_ciclo` (processor.py)

Solo las materias con `categoria == "BASICA"` y cuya clave no empiece con `"PID"` se cuentan como pendientes obligatorias. Las EL, PREESP y prácticas tienen su propio seguimiento.

### Visualización en el dashboard

- **Tab Historia Académica → Progreso por Ciclo**: dos secciones
  - "Progreso por Ciclo Anual" → 3 donuts (CA1 = sems 1-2, CA2 = sems 3-4, CA3y4 = sems 5-8)
  - "Progreso por Semestre" → 8 donuts individuales
- Las gráficas usan `textinfo="none"` para no mostrar etiquetas de 0% externas.

---

## 7. Dashboard (Streamlit)

### Pestañas principales

| Pestaña | Contenido |
|---|---|
| Historia Académica | Resumen, progreso por ciclo, EL, pre-especialidades |
| Sistema Experto | Materias candidatas + explicación de la lógica |
| Mapa Curricular | Tabla con avance por semestre + tabla de verificación |
| Pruebas | Sección de debugging |

### Flujo de carga de documentos (sidebar)

1. **Paso 1 — Historial Académico (PDF):** fuente de verdad. Se parsea con `HistorialParser`. Se guardan en `st.session_state`: `aprobadas_historial`, `historial_academico_df`, `codigos_ingles_aprobados`, `nivel_ingles_texto`, `nivel_ingles_aprobado` (int), `ingles_completo` (bool), `creditos_totales`, `creditos_acumulados`.
2. **Paso 2 — Kardex (PDF):** complementa el estado EN_CURSO del período activo.

### Tab Sistema Experto

- El sistema experto se ejecuta automáticamente al entrar a la pestaña (no requiere botón), condicionado a que haya historial cargado.
- Muestra: métricas (semestre, candidatas, analizadas), tabla de candidatas, y debajo un expander colapsado con la explicación en texto plano (sin emojis) de por qué se eligieron esas materias.

---

## 8. Archivos de datos clave

### `mapa_curricular_2021ID_real_completo.json`

Diccionario `{clave: {...}}`. Campos relevantes por materia:

```json
{
  "DP0101": {
    "clave": "DP0101",
    "nombre": "Nombre de la materia",
    "ciclo": 1,
    "ciclo_anual": 1,
    "categoria": "BASICA",
    "creditos": 6,
    "prerequisitos": []
  }
}
```

Categorías posibles: `BASICA`, `ELECCION_LIBRE`, `PREESPECIALIDAD`, `CO_CURRICULAR`.

### `mapeo_especialidades_2021ID.json`

```json
{
  "TICS": ["ID3416", "ID3417", "ID3418", "ID3419", "ID3415"],
  "BUSINESS_INTELLIGENCE": ["ID3420", "ID3421", "ID3422", "ID3423", "ID3424"]
}
```

### `mapeo_cadenas_2021ID.json`

Lista de listas; cada lista es una cadena ordenada:
```json
[["MAT0101", "MAT0201", "MAT0301"], ["DP0201", "DP0301"]]
```

---

## 9. Decisiones de diseño importantes

1. **Normalización de claves a UPPERCASE en todos los puntos de entrada.** Los PDFs a veces extraen claves en mayúsculas y a veces en mezcla. Toda comparación se hace en upper.

2. **El historial es la fuente de verdad para las aprobadas; el kardex para EN_CURSO.** Si el historial dice APROBADA y el kardex no tiene registro → se respeta el historial.

3. **Las prácticas profesionales (PID) no cuentan como pendientes de semestre** en el cálculo de progreso (`calcular_progreso_por_ciclo`). Tienen condiciones propias.

4. **El umbral del 75% en semestres 5-8 usa solo básicas.** Se decidió así porque en esos semestres el alumno tiene mayor libertad para distribuir EL y PREESP, y meterlas en el umbral podía provocar detecciones incorrectas de semestre.

5. **El sistema experto se ejecuta en tiempo real por cada carga de página** (no hay caché persistente). Para el volumen de datos actual (< 200 materias) esto es aceptable.

6. **Los niveles de inglés se infieren del texto del historial**, no del kardex. Esto es porque el kardex no siempre registra todas las materias de inglés correctamente cuando se hicieron por examen de acreditación.

---

## 10. Cómo correr el proyecto

### Requisitos

- Python 3.10+
- Dependencias: `pip install -r requirements.txt` (dentro del venv)

### Inicio

```powershell
# Activar entorno virtual
.\venv\Scripts\Activate.ps1

# Iniciar Streamlit
.\venv\Scripts\streamlit.exe run dashboard/app.py --server.port 8501
```

La app queda disponible en `http://localhost:8501`.

### Comandos útiles

```powershell
# Verificar sintaxis sin correr Streamlit
.\venv\Scripts\python.exe -m py_compile agents/sistema_experto_seriacion.py dashboard/app.py parsers/historial_parser.py

# Ver materias de preespecialidad en el mapa
.\venv\Scripts\python.exe -c "
import json
with open('data/mapa_curricular_2021ID_real_completo.json', encoding='utf-8') as f:
    mapa = json.load(f)
for clave, m in mapa.items():
    if m.get('categoria') == 'PREESPECIALIDAD':
        print(m.get('ciclo'), clave, m.get('nombre','')[:50])
"
```

---

## 11. Puntos de extensión conocidos

- **Soporte multi-plan:** el código ya parametriza el plan (`"2021ID"`), pero solo existe un mapa curricular cargado. Agregar un nuevo plan requiere generar su JSON correspondiente.
- **Notificaciones de alerta académica:** el campo `situacion` del kardex (REGULAR / IRREGULAR / BAJA) se muestra pero no genera lógica adicional todavía.
- **Servicio externo (Supabase):** existe `services/supabase_service.py` para persistir datos en la nube, pero el flujo principal usa `local_database.py` (SQLite). El switch entre ambos está en `config/settings.py`.
- **Parser de oferta académica:** en `agents/OfertaAcademica/` hay trabajo preliminar para cruzar las candidatas con la oferta real de materias del período, pero no está integrado al flujo principal.

---

## 12. Preguntas de análisis para el equipo

Las siguientes preguntas están pensadas para guiar la revisión del proyecto, identificar áreas de mejora y orientar el trabajo de los colaboradores.

---

### Sobre la lógica del sistema experto

1. **Semestres 5-8 usan solo básicas para el umbral del 75%.** ¿Podría esto hacer que un alumno con muchas PREESP aprobadas pero pocas básicas del semestre 8 quede atrapado indefinidamente en semestre 7? ¿Hay un caso borde aquí?

2. **La detección de especialidad depende del conteo de aprobadas por línea.** Si un alumno tomó 2 materias de TICS y 2 de BI en el mismo período y las reprobó todas, ¿cómo queda clasificado? ¿El sistema debería considerar también las EN_CURSO?

3. **La Regla B elimina materias avanzadas de una cadena** si la base no está aprobada. ¿Qué pasa si una materia pertenece a dos cadenas distintas? ¿El sistema lo maneja correctamente o puede eliminarse de más?

4. **Las EL de sems 1-4 tienen cuota hardcoded de 2 por ciclo anual.** Si la escuela cambia esa cuota para un nuevo plan, ¿en cuántos lugares del código habría que actualizar el valor?

5. **El umbral de 75% es fijo.** ¿Debería ser un parámetro configurable en `settings.py` para facilitar pruebas y adaptación a otros planes?

---

### Sobre el parser de PDFs

6. **El parser del historial usa expresiones regulares para detectar ciclos y categorías.** Si la escuela cambia el formato del PDF (por ejemplo, cambia "Elección libre" por "Libre elección"), ¿dónde exactamente habría que actualizar el código?

7. **Se encontró un bug de Unicode NFD/NFC** al comparar texto de Tópicos 2. ¿Hay otras comparaciones de texto en el parser que puedan tener el mismo problema? ¿Vale la pena normalizar el texto completo del PDF al inicio del parseo y no solo en `_extraer_nivel_ingles`?

8. **El kardex no siempre registra todas las materias de inglés.** ¿Sería más robusto combinar la información del historial y del kardex para reconstruir el estado completo de inglés, o eso puede generar contradicciones?

---

### Sobre el dashboard

9. **El sistema experto se ejecuta en cada carga de la pestaña** (sin botón y sin caché). Para el tamaño actual del plan esto es rápido, pero si se escalan a cientos de alumnos simultáneos o a planes más grandes, ¿cómo impactaría esto al rendimiento? ¿Qué estrategia de caché sería adecuada en Streamlit?

10. **La explicación de la lógica es narrativa (texto Markdown).** ¿Sería más útil mostrarla como un log de pasos con las claves exactas de las materias eliminadas en cada regla, para que el asesor pueda verificar manualmente cada decisión del sistema?

---

### Sobre la arquitectura general

11. **No hay pruebas automatizadas del sistema experto con casos reales.** ¿Cuáles serían los 5 casos de prueba más importantes que deberían cubrirse (por ejemplo: alumno de primer semestre, alumno con todas las básicas completas, alumno con rezago, alumno con pre-especialidades de ambas líneas, alumno con inglés incompleto)?

12. **Los datos del plan curricular están en JSON editado a mano.** Si la escuela actualiza el plan de estudios, ¿hay un proceso documentado para regenerar los JSONs de forma confiable? ¿El script `scripts/generar_mapa_curricular.py` está actualizado y probado?

13. **La BD local (SQLite vía `local_database.py`) guarda datos de estudiantes.** ¿Qué sucede si dos personas del equipo cargan el sistema en la misma máquina y uno procesa el kardex del alumno A y el otro el del alumno B en paralelo? ¿Hay riesgo de colisión de datos?
