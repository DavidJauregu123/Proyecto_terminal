"""
SISTEMA EXPERTO DE SERIACIÓN CURRICULAR v3
Genera el conjunto de materias candidatas que puede cursar un estudiante.

FLUJO:
  1. Determinar ciclo actual (primer ciclo con <75% aprobación)
  2. Generar candidatas iniciales (materias de ciclos ≤ actual, no aprobadas, no en curso)
  3. Regla A: Validar prerequisitos (todos deben estar APROBADOS)
  4. Regla B: Eliminar cadenas seriación (mantener solo base de cada cadena)
  
OUTPUT: Conjunto de materias candidatas viables
"""

import json
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional


# =============================================================================
# CARGAR Y PARSEAR DATOS
# =============================================================================

def cargar_mapa_curricular(plan: str = "2021ID") -> List[Dict]:
    """Carga el mapa curricular y lo convierte a lista."""
    ruta = Path(__file__).parent.parent / "data" / f"mapa_curricular_{plan}_real_completo.json"
    
    if not ruta.exists():
        return []
    
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            datos = json.load(f)
            
            # Si es dict (mapeado por clave), convertir a lista
            if isinstance(datos, dict):
                resultado = []
                for clave, info in datos.items():
                    if isinstance(info, dict):
                        # NORMALIZAR: Poner clave en UPPERCASE
                        clave_normalizada = str(clave).strip().upper()
                        info["clave"] = clave_normalizada
                        resultado.append(info)
                return resultado
            
            return datos if isinstance(datos, list) else []
    except Exception as e:
        print(f"Error cargando mapa curricular: {e}")
        return []


# =============================================================================
# FASE 1: DETERMINACIÓN DEL CICLO ACTUAL
# =============================================================================

def detectar_ciclo_actual(
    historial: List[Dict],
    mapa: List[Dict]
) -> int:
    """
    Determina el ciclo actual del estudiante (en semestres 1-8).

    Algoritmo:
      - Recorre semestres del 1 al 8.
      - Si el estudiante no tiene ninguna materia en contacto (aprobada o en curso)
        en ese semestre, detiene la búsqueda (no ha iniciado ese semestre).
      - Si tiene contacto: ese semestre es al menos el actual.
        * Si aprobó >=75% del semestre → avanza al siguiente.
        * Si aprobó <75% → ese es el semestre actual.

    Returns:
        int: Ciclo actual (semestre 1-8)
    """
    aprobadas = {
        str(mat.get("clave", "")).strip().upper()
        for mat in historial
        if mat.get("estatus", "").upper() == "APROBADA"
    }
    en_curso = {
        str(mat.get("clave", "")).strip().upper()
        for mat in historial
        if mat.get("estatus", "").upper() in ["EN_CURSO", "RECURSANDO"]
    }
    en_contacto = aprobadas | en_curso

    # Separar EL por ciclo del mapa (no por corte numérico global):
    # - early: EL cuyo ciclo en el plan es 1-4 (1 recomendada por sem, sin carry)
    # - late:  EL cuyo ciclo en el plan es 5-8 (acumulativo con carry-over)
    # Esto evita que EL tomadas en sems 1-4 inflen el crédito de sems 5-8.
    el_claves_early = {
        str(m.get("clave", "")).strip().upper()
        for m in mapa
        if m.get("categoria") == "ELECCION_LIBRE" and m.get("ciclo", 0) <= 4
    }
    el_claves_late = {
        str(m.get("clave", "")).strip().upper()
        for m in mapa
        if m.get("categoria") == "ELECCION_LIBRE" and m.get("ciclo", 0) >= 5
    }
    el_total_early = len(el_claves_early & en_contacto)
    el_total_late  = len(el_claves_late  & en_contacto)

    # Contar Preespecialidad totales tomadas (aprobadas o en curso) para el enfoque acumulativo
    preesp_claves_plan = {
        str(m.get("clave", "")).strip().upper()
        for m in mapa
        if m.get("categoria") == "PREESPECIALIDAD"
    }
    preesp_total = len(preesp_claves_plan & (aprobadas | en_curso))

    ciclo_actual = 1

    for ciclo in range(1, 9):
        materias_ciclo = [m for m in mapa if m.get("ciclo") == ciclo]
        if not materias_ciclo:
            continue

        claves_ciclo = {str(m.get("clave", "")).strip().upper() for m in materias_ciclo}

        # Si no hay ninguna materia de este ciclo en contacto, el estudiante
        # aún no ha iniciado este ciclo → el actual es el anterior.
        if not (claves_ciclo & en_contacto):
            break

        # Tiene contacto: este ciclo es candidato a actual
        ciclo_actual = ciclo

        # El 75% se calcula SOLO sobre BÁSICAS: las EL y PREESPECIALIDAD son
        # optativas distribuidas libremente, no bloquean el avance de semestre.
        # Las Prácticas Profesionales (clave PID*) tampoco cuentan: tienen su
        # propia lógica de alerta independiente.
        basicas_ciclo = {
            str(m.get("clave", "")).strip().upper()
            for m in materias_ciclo
            if m.get("categoria") == "BASICA"
            and not str(m.get("clave", "")).strip().upper().startswith("PID")
        }
        if not basicas_ciclo:
            # Semestre sin básicas (no debería ocurrir) → avanzar sin restricción
            continue

        cursadas_basicas = len(basicas_ciclo & (aprobadas | en_curso))
        total_basicas = len(basicas_ciclo)

        # --- Componente de Elección Libre (solo sems 1-4) ---
        # En sems 1-4: 1 EL por semestre entra al umbral.
        # En sems 5-8: solo se usan las BÁSICAS (el usuario pidió no tomar
        #   en cuenta EL ni PREESP para el análisis de semestre actual
        #   en los últimos 2 ciclos anuales).
        if ciclo <= 4:
            el_credit = min(el_total_early, ciclo) - min(el_total_early, ciclo - 1)
            el_recomendadas = 1
        else:
            el_credit = 0
            el_recomendadas = 0

        total_ciclo = total_basicas + el_recomendadas
        cursadas_total = cursadas_basicas + el_credit
        porcentaje = cursadas_total / total_ciclo

        if porcentaje < 0.75:
            # No superó el 75% → este es el ciclo actual
            break
        # Superó 75% → avanzar al siguiente ciclo

    return ciclo_actual


# =============================================================================
# FASE 2: CONSTRUCCIÓN DE CANDIDATAS INICIALES
# =============================================================================

def generar_candidatas_iniciales(
    ciclo_actual: int,
    mapa: List[Dict],
    aprobadas: Set[str],
    en_curso: Set[str]
) -> Set[str]:
    """
    Genera el conjunto de candidatas iniciales: todas las materias que
    pertenecen al ciclo actual o ciclos anteriores, que NO están aprobadas
    ni en curso.
    
    Algoritmo:
      candidatas = {}
      PARA cada ciclo en [1 ... ciclo_actual]:
          PARA cada materia en mapa WHERE materia.ciclo = ciclo:
              SI materia NOT EN aprobadas AND materia NOT EN en_curso:
                  candidatas.ADD(materia.clave)
    
    Returns:
        Set[str]: Claves de materias candidatas iniciales
    """
    candidatas = set()
    
    for ciclo in range(1, ciclo_actual + 1):
        # Materias de este ciclo
        materias_ciclo = [m for m in mapa if m.get("ciclo") == ciclo]
        
        for materia in materias_ciclo:
            clave = str(materia.get("clave", "")).strip().upper()  # NORMALIZAR
            
            # Incluir si: NO aprobada Y NO en curso
            if clave and clave not in aprobadas and clave not in en_curso:
                candidatas.add(clave)
    
    return candidatas


# =============================================================================
# FASE 3: REGLA A - VALIDACIÓN DE PREREQUISITOS
# =============================================================================

def obtener_prerequisitos(
    clave: str,
    mapa: List[Dict]
) -> Set[str]:
    """
    Obtiene los prerequisitos de una materia.
    
    Returns:
        Set[str]: Claves de los prerequisitos (vacío si no hay)
    """
    # NORMALIZAR clave a UPPERCASE
    clave = str(clave).strip().upper()
    
    materia = next((m for m in mapa if str(m.get("clave", "")).upper() == clave), None)
    if not materia:
        return set()
    
    # El campo de prerequisitos en el JSON se llama "requisitos"
    prerequisitos = materia.get("requisitos") or []
    
    if isinstance(prerequisitos, str):
        # Si es string, probablemente una sola clave
        return {str(prerequisitos).strip().upper()}
    elif isinstance(prerequisitos, list):
        # Si es lista, procesar cada elemento
        resultado = set()
        for req in prerequisitos:
            if isinstance(req, str):
                resultado.add(str(req).strip().upper())
            elif isinstance(req, dict):
                # Podría ser {clave: "...", tipo: "..."}
                if "clave" in req:
                    resultado.add(str(req["clave"]).strip().upper())
        return resultado
    
    return set()


def aplicar_regla_a_prerequisitos(
    candidatas: Set[str],
    aprobadas: Set[str],
    mapa: List[Dict]
) -> Set[str]:
    """
    REGLA A: Elimina candidatas cuyos prerequisitos NO estén APROBADOS.
    
    Principio: Una materia candidata SOLO es elegible si TODOS sus
    prerequisitos ya están APROBADOS.
    
    Algoritmo:
      candidatas_validas = {}
      PARA cada materia_candidata en candidatas:
          prerequisitos = obtener_prerequisitos(materia_candidata)
          
          SI prerequisitos es VACÍO:
              candidatas_validas.ADD(materia_candidata)
          SINO:
              todos_cumplidos = TRUE
              PARA cada prereq en prerequisitos:
                  SI prereq NOT EN aprobadas:
                      todos_cumplidos = FALSE
                      BREAK
              
              SI todos_cumplidos:
                  candidatas_validas.ADD(materia_candidata)
    
    Returns:
        Set[str]: Candidatas que pasan la validación de prerequisitos
    """
    candidatas_validas = set()
    
    for clave in candidatas:
        clave = str(clave).strip().upper()  # NORMALIZAR
        requisitos = obtener_prerequisitos(clave, mapa)
        
        if not requisitos:
            # Sin prerequisitos → válida
            candidatas_validas.add(clave)
        else:
            # Verificar que TODOS los prerequisitos están APROBADOS
            todos_cumplidos = all(req in aprobadas for req in requisitos)
            
            if todos_cumplidos:
                candidatas_validas.add(clave)
            # Si no, se elimina silenciosamente
    
    return candidatas_validas


# =============================================================================
# FASE 4: REGLA B - ELIMINACIÓN POR CADENA DE SERIACIÓN
# =============================================================================

def detectar_cadenas_seriacion(
    candidatas: Set[str],
    mapa: List[Dict]
) -> List[List[str]]:
    """
    Detecta cadenas de seriación dentro del conjunto de candidatas.
    
    Una cadena es una secuencia de materias donde cada una es prerrequisito
    de la siguiente.
    
    Returns:
        List[List[str]]: Lista de cadenas (cada cadena es una lista ordenada
                         desde la base hasta la más avanzada)
    """
    if not candidatas:
        return []
    
    cadenas = []
    visitadas = set()
    
    # NORMALIZAR todas las candidatas a UPPERCASE
    candidatas = {str(c).strip().upper() for c in candidatas}
    
    for clave in candidatas:
        if clave in visitadas:
            continue
        
        # Construir cadena para esta materia
        cadena = _construir_cadena_recursiva(clave, candidatas, mapa, set())
        
        if cadena:
            # Ordenar: de base a avanzada
            cadena_ordenada = _ordenar_cadena(cadena, mapa)
            cadenas.append(cadena_ordenada)
            visitadas.update(cadena)
    
    return cadenas


def _construir_cadena_recursiva(
    clave: str,
    candidatas: Set[str],
    mapa: List[Dict],
    visitados: Set[str]
) -> List[str]:
    """
    Construye recursivamente una cadena de seriación a partir de una materia.
    
    Busca prerequisitos de la materia que también estén en candidatas.
    """
    clave = str(clave).strip().upper()  # NORMALIZAR
    
    if clave in visitados:
        return []
    
    visitados.add(clave)
    cadena = [clave]
    
    # Buscar prerequisitos (normalizados)
    requisitos = obtener_prerequisitos(clave, mapa)
    
    for req in requisitos:
        req = str(req).strip().upper()  # NORMALIZAR
        if req in candidatas and req not in visitados:
            cadena_previa = _construir_cadena_recursiva(req, candidatas, mapa, visitados)
            cadena = cadena_previa + cadena
    
    return cadena


def _ordenar_cadena(
    cadena: List[str],
    mapa: List[Dict]
) -> List[str]:
    """
    Ordena una cadena de base (sin prerequisitos) a avanzada.
    Uses topological sort.
    """
    if len(cadena) <= 1:
        return cadena
    
    # NORMALIZAR todas las claves
    cadena = [str(c).strip().upper() for c in cadena]
    
    # Crear grafo de dependencias
    grafo = {}
    for clave in cadena:
        requisitos = obtener_prerequisitos(clave, mapa) & set(cadena)
        grafo[clave] = requisitos
    
    # Topological sort (Kahn's algorithm)
    in_degree = {clave: 0 for clave in cadena}
    for clave in cadena:
        for req in grafo[clave]:
            in_degree[clave] += 1
    
    cola = [clave for clave in cadena if in_degree[clave] == 0]
    ordenada = []
    
    while cola:
        # Tomar el que no tiene dependencias
        nodo = cola.pop(0)
        ordenada.append(nodo)
        
        # Buscar quién depende de este nodo
        for clave in cadena:
            if nodo in grafo[clave]:
                in_degree[clave] -= 1
                if in_degree[clave] == 0:
                    cola.append(clave)
    
    # Si no se pudo ordenar completamente, retornar original
    return ordenada if len(ordenada) == len(cadena) else cadena


def aplicar_regla_b_cadenas(
    candidatas: Set[str],
    mapa: List[Dict]
) -> Set[str]:
    """
    REGLA B: Elimina materias duplicadas en cadenas de seriación.
    
    Principio: Si en candidatas hay múltiples materias de la misma cadena,
    mantener solo la más cercana al punto actual (la base) y eliminar las
    demás (las más avanzadas).
    
    Algoritmo:
      cadenas = detectar_cadenas_seriacion(candidatas)
      
      PARA cada cadena en cadenas:
          candidatas_en_cadena = {mat IN candidatas PARA mat EN cadena}
          
          SI length(candidatas_en_cadena) > 1:
              base = cadena[0]  // La más base
              
              PARA cada mat en candidatas_en_cadena - {base}:
                  ELIMINAR mat de candidatas
    
    Returns:
        Set[str]: Candidatas sin duplicados en cadenas
    """
    candidatas_depuradas = candidatas.copy()
    
    cadenas = detectar_cadenas_seriacion(candidatas, mapa)
    
    for cadena in cadenas:
        # Candidatas actuales que están en esta cadena (NORMALIZAR)
        candidatas_en_cadena = [str(c).strip().upper() for c in cadena if str(c).strip().upper() in candidatas]
        
        if len(candidatas_en_cadena) > 1:
            # Mantener solo la base (primera en la cadena)
            base = candidatas_en_cadena[0]
            
            # Eliminar las demás
            for mat in candidatas_en_cadena[1:]:
                candidatas_depuradas.discard(mat)
    
    return candidatas_depuradas


# =============================================================================
# FASE 5: REGLA C - CUOTA DE ELECCIÓN LIBRE POR CICLO ANUAL
# =============================================================================

# Claves de prácticas preespecialidad y su especialidad correspondiente
PRACTICAS_PREESP_ESPECIALIDAD = {
    "PID0403": "BUSINESS_INTELLIGENCE",  # Inteligencia Organizacional de Negocios
    "PID0404": "TICS",                   # Innovación en TIC
}

# Materias de Elección Libre recomendadas por semestre, SOLO a partir del
# ciclo anual 3 (semestres 5-8). En sems 1-4 no se incluyen en el umbral.
EL_RECOMENDADAS_POR_CICLO = {5: 1, 6: 2, 7: 2, 8: 3}

# Acumulado deseado de EL al final de cada semestre, contando DESDE cero
# en el semestre 5 (ciclo anual 3). Sem 4 = 0 sirve como base del delta.
# Fórmula de crédito: min(el_total, acum_curr) - min(el_total, acum_prev)
#   → si el_total >= acum_curr  : crédito = recomendadas del semestre (máximo)
#   → si el_total < acum_curr   : crédito = lo que el alumno aportó de nuevo
EL_ACUMULADAS_CICLO = {4: 0, 5: 1, 6: 3, 7: 5, 8: 8}

# Materias de Preespecialidad recomendadas por semestre (mapa ideal: 0,0,0,0,1,1,1,2)
PREESP_RECOMENDADAS_POR_CICLO = {1: 0, 2: 0, 3: 0, 4: 0, 5: 1, 6: 1, 7: 1, 8: 2}

# Total acumulado de Preespecialidad esperadas al final de cada semestre
PREESP_ACUMULADAS_CICLO = {1: 0, 2: 0, 3: 0, 4: 0, 5: 1, 6: 2, 7: 3, 8: 5}

# Cuotas requeridas de Elección Libre por ciclo anual
EL_CUOTAS = {
    1: 2,    # Ciclo anual 1 (semestres 1-2): 2 EL requeridas
    2: 2,    # Ciclo anual 2 (semestres 3-4): 2 EL requeridas
    "34": 8, # Ciclos anuales 3+4 combinados (semestres 5-8): 8 EL requeridas
}


def _grupo_anual(ciclo_anual: int):
    """Devuelve la clave del grupo de cuota para un ciclo_anual dado."""
    if ciclo_anual == 1:
        return 1
    elif ciclo_anual == 2:
        return 2
    elif ciclo_anual in (3, 4):
        return "34"
    return None


def aplicar_regla_c_cuota_el(
    candidatas: Set[str],
    aprobadas: Set[str],
    mapa: List[Dict]
) -> Tuple[Set[str], int]:
    """
    REGLA C: Elimina candidatas de ELECCION_LIBRE de ciclos anuales donde
    la cuota ya está cubierta.

    Cuotas (definidas en EL_CUOTAS):
      - Ciclo anual 1 (sems 1-2): 2 EL requeridas
      - Ciclo anual 2 (sems 3-4): 2 EL requeridas
      - Ciclos anuales 3+4 (sems 5-8): 8 EL requeridas

    Returns:
        Tuple[Set[str], int]: (candidatas_filtradas, numero_eliminadas)
    """
    # Construir índice mapa por clave
    mapa_idx = {str(m.get("clave", "")).strip().upper(): m for m in mapa}

    # Contar EL aprobadas por grupo anual
    el_aprobadas_count = {1: 0, 2: 0, "34": 0}
    for m in mapa:
        clave = str(m.get("clave", "")).strip().upper()
        if clave not in aprobadas:
            continue
        if "ELECCI" not in m.get("categoria", "").upper():
            continue
        grupo = _grupo_anual(m.get("ciclo_anual", 0))
        if grupo is not None:
            el_aprobadas_count[grupo] += 1

    candidatas_filtradas = set()
    for clave in candidatas:
        clave = str(clave).strip().upper()
        mat = mapa_idx.get(clave)
        if not mat:
            candidatas_filtradas.add(clave)
            continue

        if "ELECCI" not in mat.get("categoria", "").upper():
            # No es EL → se mantiene siempre
            candidatas_filtradas.add(clave)
            continue

        # Es EL → verificar si la cuota del grupo ya está cubierta
        grupo = _grupo_anual(mat.get("ciclo_anual", 0))
        if grupo is None:
            candidatas_filtradas.add(clave)
            continue

        if el_aprobadas_count[grupo] < EL_CUOTAS[grupo]:
            candidatas_filtradas.add(clave)
        # else: cuota cubierta → se elimina

    eliminadas = len(candidatas) - len(candidatas_filtradas)
    return candidatas_filtradas, eliminadas


# =============================================================================
# FASE 6: REGLA D - FILTRO DE PREESPECIALIDAD POR ESPECIALIDAD DETECTADA
# =============================================================================

def detectar_especialidad(aprobadas: Set[str], plan: str = "2021ID") -> Optional[str]:
    """
    Detecta la especialidad del estudiante contando cuántas materias de
    PREESPECIALIDAD tiene aprobadas en cada track.

    Reglas:
    - Si el alumno tiene materias aprobadas en UNA sola especialidad → esa especialidad.
    - Si tiene materias en AMBAS especialidades → None (ambiguo, se muestran las dos).
    - Si no tiene ninguna materia de preespecialidad → None (se muestran las dos).
    """
    ruta = Path(__file__).parent.parent / "data" / f"mapeo_especialidades_{plan}.json"
    if not ruta.exists():
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            mapeo = json.load(f)
    except Exception:
        return None

    conteos = {}
    for especialidad, claves in mapeo.items():
        claves_upper = {str(c).strip().upper() for c in claves}
        conteos[especialidad] = len(claves_upper & aprobadas)

    if not conteos or max(conteos.values()) == 0:
        # Ninguna preespecialidad tocada → ambiguo
        return None

    especialidades_con_avance = [esp for esp, cnt in conteos.items() if cnt > 0]
    if len(especialidades_con_avance) == 1:
        # Solo una especialidad tiene avance → esa es la detectada
        return especialidades_con_avance[0]

    # Avance en más de una → ambiguo (se mostrarán ambas)
    return None


def _especialidad_completa(aprobadas: Set[str], plan: str = "2021ID") -> Optional[str]:
    """
    Devuelve el nombre de la especialidad cuyas materias de PREESPECIALIDAD
    están TODAS aprobadas, o None si ninguna está completa.
    """
    ruta = Path(__file__).parent.parent / "data" / f"mapeo_especialidades_{plan}.json"
    if not ruta.exists():
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            mapeo = json.load(f)
    except Exception:
        return None

    for especialidad, claves in mapeo.items():
        claves_upper = {str(c).strip().upper() for c in claves}
        if claves_upper and claves_upper.issubset(aprobadas):
            return especialidad
    return None


def aplicar_regla_d_preespecialidad(
    candidatas: Set[str],
    aprobadas: Set[str],
    mapa: List[Dict],
    plan: str = "2021ID"
) -> Tuple[Set[str], int, Optional[str]]:
    """
    REGLA D (nueva lógica de preespecialidad):

    Casos:
    A) Alumno sin ninguna preespecialidad aprobada → mantener candidatas de AMBAS.
    B) Alumno con avance en UNA sola especialidad (no terminada) → eliminar
       candidatas de la otra especialidad.
    C) Alumno con avance en AMBAS especialidades → mantener candidatas de ambas
       hasta que una se complete. Una vez completa una, las materias pendientes
       de la otra que estén en candidatas se tratan como ELECCION_LIBRE (se
       mantienen también, porque el mapa ya las tiene en ciclos 3/4).
    D) Una especialidad ya está completa → solo recomendar la que falta (o nada
       si las dos están completas).

    Returns:
        Tuple[Set[str], int, Optional[str]]:
            (candidatas_filtradas, numero_eliminadas, especialidad_detectada)
    """
    ruta = Path(__file__).parent.parent / "data" / f"mapeo_especialidades_{plan}.json"
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            mapeo = json.load(f)
    except Exception:
        return candidatas, 0, None

    # Conteos de maetrias preespecialidad aprobadas por especialidad
    conteos = {}
    claves_por_esp = {}
    for esp, claves in mapeo.items():
        claves_upper = {str(c).strip().upper() for c in claves}
        claves_por_esp[esp] = claves_upper
        conteos[esp] = len(claves_upper & aprobadas)

    especialidades = list(mapeo.keys())
    especialidad_detectada = None

    # ¿Cuál especialidad (si alguna) está completa?
    completa = _especialidad_completa(aprobadas, plan)

    if completa is not None:
        # Una especialidad terminada: solo recomendar materias de la otra
        # (la otra puede ser una EL si la termina, pero por ahora se muestran)
        especialidad_detectada = completa
        otras_claves = set()
        for esp in especialidades:
            if esp != completa:
                otras_claves.update(claves_por_esp.get(esp, set()))
        # No eliminamos nada de candidatas aquí — las de la otra esp siguen siendo
        # candidatas. Solo eliminamos las de la especialidad ya completa que aún
        # podrían aparecer (no deberían, pero por si acaso).
        mapa_idx = {str(m.get("clave", "")).strip().upper(): m for m in mapa}
        candidatas_filtradas = set()
        for clave in candidatas:
            clave = str(clave).strip().upper()
            mat = mapa_idx.get(clave)
            if not mat:
                candidatas_filtradas.add(clave)
                continue
            if "PREESP" in mat.get("categoria", "").upper() and clave in claves_por_esp.get(completa, set()):
                continue  # ya completa, no recomendar sus pendientes
            candidatas_filtradas.add(clave)
        eliminadas = len(candidatas) - len(candidatas_filtradas)
        return candidatas_filtradas, eliminadas, especialidad_detectada

    # Ninguna completa
    especialidades_con_avance = [esp for esp, cnt in conteos.items() if cnt > 0]

    if len(especialidades_con_avance) == 0:
        # Caso A: sin avance en ninguna → mostrar ambas
        return candidatas, 0, None

    if len(especialidades_con_avance) == 1:
        # Caso B: solo una especialidad tocada → eliminar materias de la otra
        esp_detectada = especialidades_con_avance[0]
        especialidad_detectada = esp_detectada
        claves_otras = set()
        for esp in especialidades:
            if esp != esp_detectada:
                claves_otras.update(claves_por_esp.get(esp, set()))
        mapa_idx = {str(m.get("clave", "")).strip().upper(): m for m in mapa}
        candidatas_filtradas = set()
        for clave in candidatas:
            clave = str(clave).strip().upper()
            mat = mapa_idx.get(clave)
            if not mat:
                candidatas_filtradas.add(clave)
                continue
            if "PREESP" in mat.get("categoria", "").upper() and clave in claves_otras:
                continue
            candidatas_filtradas.add(clave)
        eliminadas = len(candidatas) - len(candidatas_filtradas)
        return candidatas_filtradas, eliminadas, especialidad_detectada

    # Caso C: avance en AMBAS → mantener candidatas de las dos
    return candidatas, 0, None


def aplicar_regla_e_practicas_preespecialidad(
    candidatas: Set[str],
    aprobadas: Set[str],
    en_curso: Set[str],
    especialidad_detectada: Optional[str],
    plan: str = "2021ID"
) -> Tuple[Set[str], int]:
    """
    REGLA E: Filtra las prácticas de preespecialidad.

    Condiciones para que una práctica preespecialidad sea candidata:
      1. La especialidad del estudiante coincide con la de la práctica.
      2. El estudiante tiene ≥3 materias de esa preespecialidad aprobadas o en curso.
      3. La práctica "contraria" no está ya aprobada ni en curso
         (solo se puede cursar una).
    """
    cursadas = aprobadas | en_curso

    ruta = Path(__file__).parent.parent / "data" / f"mapeo_especialidades_{plan}.json"
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            mapeo = json.load(f)
    except Exception:
        mapeo = {}

    eliminadas = 0
    resultado = set()

    for clave in candidatas:
        clave_norm = str(clave).strip().upper()
        if clave_norm not in PRACTICAS_PREESP_ESPECIALIDAD:
            resultado.add(clave_norm)
            continue

        especialidad_requerida = PRACTICAS_PREESP_ESPECIALIDAD[clave_norm]

        # 1. Sin especialidad detectada o no coincide → eliminar
        if especialidad_detectada != especialidad_requerida:
            eliminadas += 1
            continue

        # 2. Verificar ≥3 materias de preespecialidad de su especialidad cursadas
        materias_esp = {str(c).strip().upper() for c in mapeo.get(especialidad_requerida, [])}
        if len(materias_esp & cursadas) < 3:
            eliminadas += 1
            continue

        # 3. Si la práctica de la otra especialidad ya está en trayectoria → eliminar
        otras = {k for k in PRACTICAS_PREESP_ESPECIALIDAD if k != clave_norm}
        if otras & cursadas:
            eliminadas += 1
            continue

        resultado.add(clave_norm)

    return resultado, eliminadas


# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

def ejecutar_sistema_experto(
    historial_academico: List[Dict],
    mapa_curricular: Optional[List[Dict]] = None,
    plan_estudios: str = "2021ID"
) -> Dict:
    """
    Ejecuta el sistema experto de seriación para generar materias candidatas.
    
    Args:
        historial_academico: Lista de materias cursadas
                            [{clave, nombre, ciclo, estatus, calificacion, creditos}, ...]
        mapa_curricular: Mapa curricular (si no se pasa, se carga automáticamente)
        plan_estudios: ID del plan (default: 2021ID)
    
    Returns:
        Dict:
        {
            "ciclo_actual": int,
            "candidatas_count": int,
            "candidatas_claves": [str],
            "candidatas_detalles": [
                {
                    "clave": str,
                    "nombre": str,
                    "ciclo": int,
                    "creditos": int,
                    "categoria": str,
                    "prerequisitos": [str]
                },
                ...
            ],
            "especialidad_detectada": str | None,
            "debug": {
                "candidatas_iniciales_count": int,
                "eliminadas_regla_a": int,
                "eliminadas_regla_b": int,
                "eliminadas_regla_c": int,
                "eliminadas_regla_d": int
            }
        }
    """
    
    # Cargar mapa si no se pasó
    if mapa_curricular is None:
        mapa_curricular = cargar_mapa_curricular(plan_estudios)
    
    if not mapa_curricular:
        return {
            "ciclo_actual": 0,
            "candidatas_count": 0,
            "candidatas_claves": [],
            "candidatas_detalles": [],
            "error": "No se pudo cargar el mapa curricular"
        }
    
    # =========================================================================
    # PASO 1: Extraer información del historial (NORMALIZAR a UPPERCASE)
    # =========================================================================
    aprobadas = {
        str(mat.get("clave", "")).strip().upper() 
        for mat in historial_academico 
        if mat.get("estatus", "").upper() == "APROBADA"
    }
    
    en_curso = {
        str(mat.get("clave", "")).strip().upper() 
        for mat in historial_academico 
        if mat.get("estatus", "").upper() in ["EN_CURSO", "RECURSANDO"]
    }
    
    # =========================================================================
    # PASO 2: Determinar ciclo actual
    # =========================================================================
    ciclo_actual = detectar_ciclo_actual(historial_academico, mapa_curricular)
    
    # =========================================================================
    # PASO 3: Generar candidatas iniciales
    # =========================================================================
    candidatas = generar_candidatas_iniciales(
        ciclo_actual, mapa_curricular, aprobadas, en_curso
    )
    count_iniciales = len(candidatas)
    
    # =========================================================================
    # PASO 4: Aplicar REGLA A - Validar prerequisitos
    # =========================================================================
    candidatas_antes_b = len(candidatas)
    candidatas = aplicar_regla_a_prerequisitos(candidatas, aprobadas, mapa_curricular)
    count_eliminadas_a = candidatas_antes_b - len(candidatas)
    
    # =========================================================================
    # PASO 5: Aplicar REGLA B - Eliminar cadenas
    # =========================================================================
    candidatas_antes_b = len(candidatas)
    candidatas = aplicar_regla_b_cadenas(candidatas, mapa_curricular)
    count_eliminadas_b = candidatas_antes_b - len(candidatas)

    # =========================================================================
    # PASO 6: Aplicar REGLA C - Cuota de Elección Libre
    # =========================================================================
    candidatas, count_eliminadas_c = aplicar_regla_c_cuota_el(
        candidatas, aprobadas, mapa_curricular
    )

    # =========================================================================
    # PASO 7: Aplicar REGLA D - Filtro de Preespecialidad
    # =========================================================================
    candidatas, count_eliminadas_d, especialidad_detectada = aplicar_regla_d_preespecialidad(
        candidatas, aprobadas, mapa_curricular, plan_estudios
    )

    # =========================================================================
    # PASO 8: Aplicar REGLA E - Filtro de Prácticas Preespecialidad
    # =========================================================================
    candidatas, count_eliminadas_e = aplicar_regla_e_practicas_preespecialidad(
        candidatas, aprobadas, en_curso, especialidad_detectada, plan_estudios
    )

    # =========================================================================
    # PASO 9: Enriquecer resultado
    # =========================================================================
    detalles = []
    for clave in sorted(candidatas):
        clave = str(clave).strip().upper()  # NORMALIZAR
        materia_info = next(
            (m for m in mapa_curricular if str(m.get("clave", "")).strip().upper() == clave),
            None
        )
        
        if materia_info:
            requisitos = obtener_prerequisitos(clave, mapa_curricular)
            detalles.append({
                "clave": clave,
                "nombre": materia_info.get("nombre", "Desconocido"),
                "ciclo": materia_info.get("ciclo", 0),
                "creditos": materia_info.get("creditos", 0),
                "categoria": materia_info.get("categoria", ""),
                "prerequisitos": sorted(list(requisitos))
            })
    
    return {
        "ciclo_actual": ciclo_actual,
        "candidatas_count": len(candidatas),
        "candidatas_claves": sorted(list(candidatas)),
        "candidatas_detalles": detalles,
        "especialidad_detectada": especialidad_detectada,
        "debug": {
            "candidatas_iniciales_count": count_iniciales,
            "eliminadas_regla_a": count_eliminadas_a,
            "eliminadas_regla_b": count_eliminadas_b,
            "eliminadas_regla_c": count_eliminadas_c,
            "eliminadas_regla_d": count_eliminadas_d,
            "eliminadas_regla_e": count_eliminadas_e
        }
    }
