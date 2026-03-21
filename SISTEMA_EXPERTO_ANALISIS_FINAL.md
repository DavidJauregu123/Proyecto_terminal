# SISTEMA EXPERTO DE SERIACIÓN - ANÁLISIS DEFINITIVO

## OBJETIVO
Determinar qué materias puede cursar un estudiante basándose en:
- Su historial académico (aprobadas, reprobadas, en curso)
- El plan de estudios
- Reglas de seriación y prerequisitos
- **RESTRICCIÓN CLAVE:** Todos los prerequisitos deben estar APROBADOS (no en curso)

---

## FASE 1: DETERMINACIÓN DEL CICLO ACTUAL

### Lógica Precisada

El ciclo actual es el **primer ciclo donde el estudiante NO ha aprobado el 75% de sus materias**.

```
ciclo_actual = 1

PARA cada ciclo en [1, 2, 3, 4]:
    materias_del_ciclo = todas las materias que pertenecen a este ciclo
    aprobadas_en_ciclo = COUNT(mat en materias_del_ciclo WHERE estatus = "APROBADA")
    total_materias_ciclo = COUNT(materias_del_ciclo)
    
    porcentaje_aprobacion = aprobadas_en_ciclo / total_materias_ciclo
    
    SI porcentaje_aprobacion >= 0.75:
        ciclo_actual = ciclo + 1
    SINO:
        // Este es el ciclo actual → detenerse
        ciclo_actual = ciclo
        BREAK

ciclo_actual = MIN(ciclo_actual, 4)  // Máximo ciclo 4
```

### Casos Límite

| Caso | Ejemplo | Resultado |
|------|---------|-----------|
| Estudiante nuevo | 0% de ciclo 1 aprobado | ciclo_actual = 1 |
| 75% exacto | 9 de 12 materias ciclo 1 | ciclo_actual = 2 |
| 74% | 8 de 12 materias ciclo 1 | ciclo_actual = 1 |
| Todos ciclos ≥75% | Avanzadísimo | ciclo_actual = 4 |
| Cicl 1=75%, ciclo 2=50% | Mezclado | ciclo_actual = 2 |

---

## FASE 2: CONSTRUCCIÓN DE CANDIDATAS INICIALES

### Definición

Las candidatas iniciales son todas las materias que:
1. Pertenecen al ciclo actual O ciclos anteriores
2. NO han sido aprobadas
3. NO están en curso / recursando

### Pseudocódigo

```
candidatas_iniciales = CONJUNTO VACÍO

PARA cada ciclo en [1 ... ciclo_actual]:
    PARA cada materia en mapa_curricular WHERE materia.ciclo = ciclo:
        SI materia.clave NOT EN aprobadas AND materia.clave NOT EN en_curso:
            candidatas_iniciales.ADD(materia)

RETORNAR candidatas_iniciales
```

### Ejemplo

```
Plan: Ciclo 1 {A, B, C}, Ciclo 2 {D, E, F}, Ciclo 3 {G, H, I}
Estudiante: aprobadas={A, B}, en_curso={D}, ciclo_actual=2

Candidatas iniciales = {C, E, F}
Explicación:
  - C: ciclo 1, no aprobada, no en curso → INCLUYE
  - D: ciclo 2, pero en curso → EXCLUYE
  - E: ciclo 2, no aprobada, no en curso → INCLUYE
  - F: ciclo 2, no aprobada, no en curso → INCLUYE
  - G, H, I: ciclo 3 > ciclo_actual → NO SE CONSIDERAN
```

---

## FASE 3: APLICACIÓN DE REGLAS DE DEPURACIÓN

### REGLA A: Validación Estricta de Prerequisitos

**Principio:** Una materia candidata SOLO es elegible si TODOS sus prerequisitos ya están APROBADOS.

#### Pseudocódigo

```
candidatas_depuradas_A = CONJUNTO VACÍO

PARA cada materia_candidata en candidatas_iniciales:
    prerequisitos = obtener_prerequisitos(materia_candidata)
    
    SI prerequisitos es VACÍO:
        // No tiene prerequisitos
        candidatas_depuradas_A.ADD(materia_candidata)
    SINO:
        // Verificar que TODOS los prerequisitos están APROBADOS
        todos_cumplidos = TRUE
        
        PARA cada prereq en prerequisitos:
            SI prereq NOT EN aprobadas:
                todos_cumplidos = FALSE
                BREAK
        
        SI todos_cumplidos:
            candidatas_depuradas_A.ADD(materia_candidata)
        // Si no, se elimina (NO se agrega)
```

#### Interpretación Crítica

```
Importante: 
- Si un prerequisito está EN_CURSO, NO cuenta como cumplido
- Si un prerequisito NO está aprobado NI en curso, NO cuenta como cumplido
- Solo APROBADA = candidata elegible
```

#### Ejemplo

```
Mapa:
  Ciclo 1: Cálculo Diferencial (sin prereq)
  Ciclo 1: Matrices (sin prereq)
  Ciclo 1: Cálculo Integral (prereq: Cál. Diferencial)
  Ciclo 2: Ecuaciones Diferenciales (prereq: Cál. Integral)
  Ciclo 2: Álgebra Lineal (prereq: Matrices)

Historial:
  Aprobadas: {Cálculo Diferencial}
  En curso: {Matrices}
  Candidatas iniciales: {Cálculo Integral, Ecuaciones Diferenciales, Álgebra Lineal}

Aplicar REGLA A:
  - Cálculo Integral: prereq = Cál. Diferencial (APROBADO) → MANTIENE ✓
  - Ecuaciones Diferenciales: prereq = Cál. Integral (NO APROBADO) → ELIMINA ✗
  - Álgebra Lineal: prereq = Matrices (EN CURSO, no cuenta) → ELIMINA ✗

Candidatas después Regla A: {Cálculo Integral}
```

---

### REGLA B: Eliminación por Cadena de Seriación

**Problema que resuelve:** 
Si en el conjunto de candidatas hay varias materias que pertenecen a una misma cadena de seriación, 
se debe eleiminar la de nivel más alto y mantener la más cercana al punto actual del estudiante.

**Definición de Cadena:**
Una cadena de seriación es una secuencia de materias donde cada una es prerequisito directo de la siguiente:

```
Ejemplo 1 (lineal):
  Cálculo Diferencial → Cálculo Integral → Ecuaciones Diferenciales

Ejemplo 2 (árbol):
                    Cálculo Vectorial
                    /              \
       Cálculo Integral      Álgebra Lineal
       /
   Cálculo Diferencial
```

#### Algoritmo de Detección

```
PARA cada materia_candidata en candidatas_depuradas_A:
    cadena = construir_cadena_recursiva(materia_candidata, candidatas_depuradas_A)
    
    SI length(cadena) > 1:
        // Hay una cadena: eliminar todos excepto el primero
        base = cadena[0]  // El que no tiene prereq en la cadena
        
        PARA cada mat en cadena[1 ... end]:
            ELIMINAR mat de candidatas_depuradas_A
```

#### Función Auxiliar: Construir Cadena

```
FUNCIÓN construir_cadena_recursiva(materia, candidatas):
    cadena = [materia]
    
    PARA cada mat_candidata en candidatas:
        SI mat_candidata IN prerequisitos(materia):
            // mat_candidata es prerequisito de materia
            cadena_previa = construir_cadena_recursiva(mat_candidata, candidatas)
            cadena = cadena_previa + cadena
    
    RETORNAR cadena
```

#### Ejemplo

```
Candidatas después Regla A: 
  {Cálculo Diferencial, Cálculo Integral, Ecuaciones Diferenciales}

Prerequisitos:
  - Cálculo Integral requiere Cálculo Diferencial
  - Ecuaciones Diferenciales requiere Cálculo Integral

Construir cadena para Ecuaciones Diferenciales:
  - Cadena completa: [Cálculo Diferencial, Cálculo Integral, Ecuaciones Diferenciales]

Aplicar Regla B:
  - Mantener: Cálculo Diferencial (base de la cadena)
  - Eliminar: Cálculo Integral, Ecuaciones Diferenciales

Candidatas después Regla B: {Cálculo Diferencial}
```

---

## FASE 4: RESULTADO FINAL

```
candidatas_finales = candidatas_depuradas_A (después de Regla B)

OUTPUT: {
    ciclo_actual: INT,
    materias_candidatas: LIST[STRING (claves de materia)],
    cantidad_candidatas: INT,
    detalles_por_materia: {
        clave: {
            nombre: STRING,
            ciclo: INT,
            categoria: STRING,
            creditos: INT,
            razon_eliminacion: STRING OR NULL
        }
    }
}
```

---

## FLUJO COMPLETO EN PSEUDOCÓDIGO

```
FUNCIÓN sistema_experto(
    historial_completo: LIST[{clave, estatus, ciclo}],
    mapa_curricular: LIST[{clave, nombre, ciclo, categoria, creditos, prerequisitos[]}]
) → DICT:
    
    // Paso 1: Extraer información del historial
    aprobadas = {mat.clave FOR mat IN historial_completo IF mat.estatus = "APROBADA"}
    en_curso = {mat.clave FOR mat IN historial_completo IF mat.estatus IN ["EN_CURSO", "RECURSANDO"]}
    
    // Paso 2: Determinar ciclo actual
    ciclo_actual = determinar_ciclo_actual(historial_completo, mapa_curricular)
    
    // Paso 3: Generar candidatas iniciales
    candidatas = generar_candidatas_iniciales(ciclo_actual, mapa_curricular, aprobadas, en_curso)
    
    // Paso 4: Aplicar REGLA A - Validar prerequisitos
    candidatas = validar_prerequisitos(candidatas, aprobadas, mapa_curricular)
    
    // Paso 5: Aplicar REGLA B - Eliminar cadenas
    candidatas = eliminar_cadenas_seriacion(candidatas, mapa_curricular)
    
    // Paso 6: Enriquecer resultado
    resultado = {
        ciclo_actual: ciclo_actual,
        materias_candidatas: candidatas,
        cantidad_candidatas: LENGTH(candidatas),
        detalles: enriquecer_detalles(candidatas, mapa_curricular)
    }
    
    RETORNAR resultado
```

---

## PSEUDO-REGLAS IF-THEN (Para Experta o Similar)

### Regla 1: Candidata Base
```
IF ciclo <= ciclo_actual 
   AND materia.ciclo = ciclo
   AND materia NOT IN {aprobadas}
   AND materia NOT IN {en_curso}
THEN candidata_potencial(materia)
```

### Regla 2: Prerequisitos Válidos
```
IF candidata_potencial(materia)
   AND FORALL prereq IN prerequisites(materia):
       prereq IN {aprobadas}
THEN candidata_válida(materia)
```

### Regla 3: No Duplicar en Cadena
```
IF candidata_válida(materia_A)
   AND candidata_válida(materia_B)
   AND materia_B IN prerequisites(materia_A)
THEN REMOVE candidata_válida(materia_A)
```

---

## CASOS LÍMITE CUBIERTOS

| Caso | Manejo |
|------|--------|
| Prerequisito en curso | Rechazar (Regla A) |
| Prerequisito no aprobado | Rechazar (Regla A) |
| Zwei candidatas en cadena | Mantener solo base (Regla B) |
| Múltiples cadenas | Aplicar Regla B a cada una |
| Ciclo actual incompleto | Incluir materias solo de ese ciclo e inferiores |
| Ciclos posteriores | NO SE INCLUYEN |
| Estudiante sin aprobadas | Ciclo actual = 1, solo sin prerequisitos |
| Estudiante avanzadísimo | Ciclo actual capped en 4 |

---

## CASOS ESPECIALES A CONSIDERAR

### ¿Qué si una materia tiene múltiples caminos de prerequisitos?

```
Ejemplo:
  Cálculo Vectorial requiere: {Cálculo Integral O Álgebra Lineal}
  (es decir, necesita AL MENOS uno de los dos)

Regla A (modificada para OR):
  SI existe_al_menos_uno(prerequisitos) ∈ aprobadas:
      ENTONCES candidata_válida(materia)
```

**Pregunta para ti:** ¿Tu mapa curricular tiene prerequisitos con lógica OR, o solo AND?
Si respuesta = AND, la lógica arriba es suficiente.

---

## VALIDACIÓN: EJEMPLO COMPLETO

```
ENTRADA:
========
Mapa Curricular (Plan 2021ID):
  Ciclo 1: A (sin prereq, 3 cred), B (sin prereq, 4 cred), C (prereq: A, 3 cred)
  Ciclo 2: D (prereq: B, 4 cred), E (prereq: C, 3 cred), F (sin prereq, 3 cred)
  Ciclo 3: G (prereq: D, 4 cred), H (prereq: E, 3 cred)

Historial Estudiante:
  Aprobadas: {A, B}
  En curso: {C}
  Otros: ninguno

EJECUCIÓN:
==========
1) Ciclo actual = 1 (no ha aprobado 75% de ciclo 1: aprobó 2 de 3 = 66%)

2) Candidatas iniciales:
      Ciclo 1 no aprobadas ni en curso = {} 
      (A=aprobada, B=aprobada, C=en curso)
   RESULTADO: candidatas = {}

SIN EMBARGO, revisando lógica de ciclo actual:
  Si 2 aprobadas de 3 = 66% < 75%, entonces ciclo_actual = 1
  Las candidatas deben incluir lo que falta del ciclo actual: {C}

Pero C está EN CURSO, así que NO se incluye como candidata.

CONCLUSIÓN: No hay candidatas disponibles ahora.
(El estudiante debe terminar C para poder avanzar.)

---

ESCENARIO ALTERNATIVO:
Historial Estudiante (modificado):
  Aprobadas: {A, B, C}  // C ahora aprobada
  En curso: {}

1) Ciclo actual:
      Ciclo 1: 3 aprobadas de 3 = 100% >= 75% → continuar
      Ciclo 2: 0 aprobadas de 3 = 0% < 75% → STOP
   ciclo_actual = 2

2) Candidatas iniciales:
      Ciclo 1: {} (todas aprobadas)
      Ciclo 2: {D, E, F}
   candidatas_iniciales = {D, E, F}

3) Regla A (prerequisitos):
      D: prereq = B (APROBADO) → MANTIENE
      E: prereq = C (APROBADO) → MANTIENE
      F: sin prereq → MANTIENE
   candidatas_después_A = {D, E, F}

4) Regla B (cadenas):
      Cadena 1: [B, D, G] pero D ∈ candidatas, G ∉ candidatas → solo [D]
      Cadena 2: [C, E, H] pero E ∈ candidatas, H ∉ candidatas → solo [E]
      Cadena 3: [F] sin dependientes en candidatas
   candidatas_después_B = {D, E, F}

RESULTADO FINAL:
  ciclo_actual = 2
  materias_candidatas = {D, E, F}
  detalles:
    - D: Nombre, Ciclo 2, 4 créditos
    - E: Nombre, Ciclo 2, 3 créditos
    - F: Nombre, Ciclo 2, 3 créditos
```

---

## IMPLEMENTACIÓN RECOMENDADA

### Estructura de Función Principal

```python
def ejecutar_sistema_experto(
    historial_academico: List[Dict],
    mapa_curricular: List[Dict],
    plan_estudios: str = "2021ID"
) -> Dict:
    """
    Genera el conjunto de materias candidatas que puede cursar el estudiante.
    
    Args:
        historial_academico: Lista de {clave, estatus, ciclo, ...}
        mapa_curricular: Lista de {clave, nombre, ciclo, prerequisitos[], ...}
        plan_estudios: Identificador del plan
    
    Returns:
        {
            ciclo_actual: int,
            materias_candidatas: [str],  # claves
            cantidad_candidatas: int,
            detalles: Dict[str, Dict]
        }
    """
    
    # Fase 1
    aprobadas = extraer_aprobadas(historial_academico)
    en_curso = extraer_en_curso(historial_academico)
    
    # Fase 2
    ciclo_actual = detectar_ciclo_actual(historial_academico, mapa_curricular)
    
    # Fase 3
    candidatas = generar_candidatas_iniciales(ciclo_actual, mapa_curricular, aprobadas, en_curso)
    
    # Fase 4 - Regla A
    candidatas = aplicar_regla_a_prerequisitos(candidatas, aprobadas, mapa_curricular)
    
    # Fase 5 - Regla B
    candidatas = aplicar_regla_b_cadenas(candidatas, mapa_curricular)
    
    # Fase 6
    return {
        "ciclo_actual": ciclo_actual,
        "materias_candidatas": candidatas,
        "cantidad_candidatas": len(candidatas),
        "detalles": enriquecer_materias(candidatas, mapa_curricular)
    }
```

---

## RESUMEN DE RESTRICCIONES CONFIRMADAS

✅ **Prerequisitos:** SOLO cuenta como cumplido si el requisito está APROBADO (no en curso)  
✅ **Alcance:** SOLO ciclos actuales e inferiores (sin ciclos posteriores)  
✅ **Salida:** Conjunto de materias candidatas viables (sin optimizar carga)  
✅ **Sin límites:** No hay máximo de candidatas ni políticas especiales adicionales  

