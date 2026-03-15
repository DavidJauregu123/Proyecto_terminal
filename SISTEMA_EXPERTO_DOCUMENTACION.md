# Sistema Experto de Seriación Curricular - Documentación

## Estado: ✅ COMPLETADO

El Sistema Experto de Seriación está **100% funcional** y validado con tests.

---

## 📋 Lo que se construyó

### 1. **Mapa Curricular Real** (mapa_curricular_2021ID_real_completo.json)
- **78 materias** distribuidas en 8 semestres (4 ciclos anuales)
- Estructura alineada al Excel oficial del plan 2021 IDeIO
- Requisitos migrados desde el mapa legacy cuando hubo equivalencia segura
- Complementado con `mapa_curricular_2021ID_real.json` y `equivalencias_legacy_2021ID.json`

**Semestres:**
- Semestres 1-8 con progresión semestral real del plan
- Cobertura de claves mixtas (DP, II, ID, IT, IL, IA, NI)

### 2. **Motor de Inferencia Nativo** (agents/sistema_experto_seriacion.py)

**Características:**
- Implementación **100% nativa** (sin dependencias externas complejas)
- Compatible con Python 3.13
- Soporta la lógica exacta que explicó el profesor:

#### **Algoritmo de Seriación:**

1. **Detección de Ciclo Actual**
   - Calcula % de créditos completados por ciclo
   - Si ciclo >= 75% → "completado"
   - Ciclo actual = primer ciclo no completado

2. **Generación de Candidatas Temporales**
   - Todas las materias NO cursadas del ciclo actual
   - Todas las materias NO cursadas de ciclos anteriores (rezagadas)

3. **Filtrado por Requisitos**
   - Valida que todos los prerequisitos estén aprobados
   - Genera alertas de tipo "BLOQUEO" para materias sin requisitos

4. **Regla de Ligaduras** (Regla del Profesor)
   - Si dos materias ligadas (una es prerequisito directo) están ambas en candidatas
   - Elimina la materia dependiente (del ciclo posterior)
   - Genera alertas de tipo "LIGADURA"
   - Ejemplo: Si Cálculo Diferencial → Cálculo Integral, y ambas son candidatas, se elimina Integral

**Ejemplo de ligaduras detectadas:**
```
ID0102 (Cálculo Diferencial) → ID0104 (Cálculo Integral)
ID0201 (Cálculo Vectorial) → ID0301 (Ecuaciones Diferenciales)
ID0205 (Diseño de Patrones) → ID0305 (Técnicas Algorítmicas)
... y más
```

### 3. **Servicio de Integración** (services/seriacion_service.py)

**ProcessadorSeriacionExacerbado** clase que:
- Integra el sistema experto con datos de BD PostgreSQL
- Calcula progreso por ciclo
- Detecta ciclo actual automáticamente
- Genera planes semestrales
- Produce resúmenes ejecutivos

**Métodos principales:**
```python
- analizar_estudiante_completo(estudiante_id) → análisis detallado
- generar_plan_semestral(estudiante_id, semestres_futuro) → plan futuro
- _calcular_progreso_por_ciclo() → progreso académico
- _detectar_ciclo_actual() → ubicación actual
```

### 4. **Suite Completa de Tests** (tests/test_sistema_experto.py)

**5 Tests validated:**

✅ **TEST 1:** Ejecución básica del sistema
- Verifica: ciclo detectado, materias recomendadas, alertas

✅ **TEST 2:** Validación de requisitos
- Verifica: bloqueo de materias sin prerequisites

✅ **TEST 3:** Regla de ligaduras
- Verifica: eliminación correcta de materias ligadas

✅ **TEST 4:** Integración con procesador
- Verifica: cálculo de progreso y detección de ciclo

✅ **TEST 5:** Generación de plan semestral
- Verifica: plan proyectado respetando carga académica

**Resultado:** ✅ **TODOS LOS TESTS PASARON**

---

## 🚀 Uso del Sistema

### Ejemplo Básico:

```python
from agents.sistema_experto_seriacion import ejecutar_sistema_experto

# Datos del estudiante
datos_est = {
    "id": "EST001",
    "nombre": "Juan Pérez",
    "promedio": 8.5,
    "total_creditos": 54
}

# Historial académico (materias aprobadas)
historial = [
    {"clave_materia": "ID0001", "calificacion": 9.0, "creditos_obtenidos": 6},
    {"clave_materia": "ID0101", "calificacion": 8.5, "creditos_obtenidos": 8},
    # ... resto de materias ...
]

# Ejecutar sistema experto
resultado = ejecutar_sistema_experto(datos_est, historial)

# Resultado:
# {
#     "ciclo_actual": 2,
#     "ciclo_recomendado": 2,
#     "materias_recomendadas": [...],
#     "alertas": [...],
#     "total_materias_recomendadas": 7,
#     "diagrama_ligaduras": {...}
# }
```

### Con Integración BD:

```python
from services.seriacion_service import ProcessadorSeriacionExacerbado

procesador = ProcessadorSeriacionExacerbado(
    db_service=db_service,
    mapa_curricular=mapa
)

# Análisis completo
resultado = procesador.analizar_estudiante_completo("EST001")

# Plan semestral
plan = procesador.generar_plan_semestral("EST001", semestres_futuro=2)
```

---

## 📊 Ejemplos de Salida

### Estudiante completó Ciclo 1:
```
[CICLO 1] 100.0% (55/55 creditos)
[CICLO 2] 0.0% (0/51 creditos)
[INFO] Ciclo actual: 2
[CANDIDATAS] 7 materias
[VALIDAS] 7 materias (despues requisitos)
[RECOMENDACIONES] 7 materias

Materias Recomendadas:
1. ID0201 - Cálculo Vectorial (8 créditos)
2. ID0202 - Probabilidad y Estadística (8 créditos)
3. ID0203 - Álgebra Lineal (8 créditos)
... y más
```

### Con alertas de bloqueo:
```
Alertas:
- [BLOQUEO] ID0102 requiere ID0001
- [BLOQUEO] ID0104 requiere ID0102
```

---

## 🔗 Estructura de Archivos

```
proyecto terminal/
├── agents/
│   └── sistema_experto_seriacion.py      # Motor experto nativo
├── services/
│   └── seriacion_service.py              # Integración con BD
├── tests/
│   └── test_sistema_experto.py           # Suite de tests
├── data/
│   ├── mapa_curricular_2021ID_real.json
│   ├── mapa_curricular_2021ID_real_completo.json
│   └── equivalencias_legacy_2021ID.json
└── requirements.txt                      # Dependencias actualizadas

---

## 🧩 Nota de Extracción PDF

- El extractor de PDF siempre toma la `clave` y el `nombre` directamente del kardex/historial.
- El JSON curricular no altera claves extraídas; solo aporta metadatos (ciclo, categoría, requisitos).
- Por esta razón, migrar al mapa real mejora la seriación sin afectar la extracción base del parser.
```

---

## 📦 Dependencias

**Sistema experto NO necesita bibliotecas externas complejas:**
- Solo Python 3.13+ estándar
- Código 100% nativo
- Compatible con cualquier plataforma

**Dependencias del proyecto:**
- pandas, numpy (análisis de datos)
- streamlit (dashboard)
- sqlalchemy (modelos BD)
- networkx (grafos de seriación - opcional)

---

## ✅ Lo que está listo

- ✅ Mapa curricular completo y estructurado
- ✅ Sistema experto con reglas de seriación
- ✅ Detección automática de ciclo actual
- ✅ Generación de candidatas temporales
- ✅ Validación de requisitos
- ✅ Regla de ligaduras implementada
- ✅ Servicio de integración con BD
- ✅ Tests completos y validados
- ✅ Documentación

---

## 🚀 Próximos Pasos

1. **Integración con BD PostgreSQL**
   - Conectar `ProcessadorSeriacionExacerbado` con datos reales
   - Guardar recomendaciones en tabla `recomendaciones`

2. **API REST**
   - Crear endpoints para consultar recomendaciones
   - `/api/seriacion/{estudiante_id}`
   - `/api/plan/{estudiante_id}`

3. **Dashboard Streamlit**
   - Visualizar materias recomendadas
   - Mostrar progreso por ciclo
   - Alertas de bloqueo/ligadura
   - Plan semestral interactivo

4. **Agente Conversacional**
   - Integrar con Gemini
   - Responder consultas en lenguaje natural
   - "¿Qué materias puedo cursar el próximo semestre?"

---

## 📝 Notas Importantes

### Regla del Profesor Implementada Correctamente
La regla de ligaduras es fundamental:
- **Sin ligaduras:** Solo se validan requisitos directos
- **Con ligaduras:** Se evita que ambas materias encadenadas sean candidatas

Ejemplo:
```
Sin ligadura (2 requisitos):
  Cálculo Integral + Probabilidad → Minería de Datos
  Ambas pueden ser candidatas si cumplen requisitos

Con ligadura (1 requisito directo):
  Cálculo Diferencial → Cálculo Integral
  Si ambas son candidatas, Integral se elimina
```

---

## 👨‍💻 Autor/Desarrollador

Sistema Experto de Seriación Curricular
Plan 2021 - IDeIO (Ingeniería en Datos e Inteligencia Organizacional)
Universidad del Caribe

**Mapa curricular basado en documentación oficial del programa.**
