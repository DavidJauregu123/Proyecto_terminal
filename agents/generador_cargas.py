"""
Generador de Cargas Académicas con NSGA-III
Optimiza la selección de materias usando un algoritmo genético multi-objetivo.

OBJETIVOS (3):
  1. Maximizar cobertura de prioridad (nivel 1 > 2 > 3 > 4 > 5)
  2. Minimizar dispersión horaria (huecos entre clases y días dispersos)
  3. Minimizar distancia al número deseado de materias

RESTRICCIONES:
  - Sin choques de horario
  - Dentro del rango de créditos permitido
  - Máximo de materias según situación (condicionado = 3)
  - Respetar disponibilidad horaria del estudiante
"""

import random
import warnings
from typing import Dict, List, Optional, Tuple
from itertools import combinations

from services.oferta_service import verificar_choque_horario, verificar_disponibilidad

warnings.filterwarnings("ignore", category=RuntimeWarning)


# =============================================================================
# FUNCIONES DE EVALUACIÓN (OBJETIVOS)
# =============================================================================

def _peso_prioridad(prioridad: int) -> float:
    """Peso exponencial: nivel 1 = 81, nivel 2 = 27, nivel 3 = 9, nivel 4 = 3, nivel 5 = 1."""
    return 3 ** (5 - prioridad)


def objetivo_prioridad(secciones_carga: List[Dict]) -> float:
    """
    Objetivo 1: Maximizar cobertura de prioridad.
    Suma de pesos exponenciales por cada materia incluida.
    Se normaliza dividiendo entre el máximo teórico.
    """
    if not secciones_carga:
        return 0.0
    score = sum(_peso_prioridad(s["prioridad"]) for s in secciones_carga)
    max_score = len(secciones_carga) * 81  # Máximo si todas fueran nivel 1
    return score / max_score if max_score > 0 else 0.0


def objetivo_compacidad(secciones_carga: List[Dict]) -> float:
    """
    Objetivo 2: Minimizar dispersión horaria (0 = compacto, 1 = disperso).
    Penaliza huecos entre clases y días con pocas horas.
    """
    if not secciones_carga:
        return 1.0

    dias_horas = {}  # {"Lunes": [7,8,9,13,14], ...}
    for seccion in secciones_carga:
        for bloque in seccion["horario"]:
            dia = bloque["dia"]
            if dia not in dias_horas:
                dias_horas[dia] = []
            dias_horas[dia].extend(range(bloque["inicio"], bloque["fin"]))

    if not dias_horas:
        return 1.0

    # Penalización por huecos dentro de cada día
    total_huecos = 0
    total_horas = 0
    for dia, horas in dias_horas.items():
        horas_unicas = sorted(set(horas))
        if len(horas_unicas) < 2:
            continue
        rango = horas_unicas[-1] - horas_unicas[0]
        huecos = rango - len(horas_unicas)
        total_huecos += huecos
        total_horas += len(horas_unicas)

    # Penalización por muchos días usados
    dias_usados = len(dias_horas)
    penalizacion_dias = dias_usados / 6.0  # 6 días posibles

    if total_horas == 0:
        return 1.0

    penalizacion_huecos = total_huecos / max(total_horas, 1)

    # Combinación ponderada
    return min(1.0, 0.6 * penalizacion_huecos + 0.4 * penalizacion_dias)


def objetivo_cantidad(secciones_carga: List[Dict], materias_deseadas: int) -> float:
    """
    Objetivo 3: Minimizar distancia al número deseado de materias (0 = exacto).
    """
    if materias_deseadas <= 0:
        return 0.0
    # Contar materias únicas (no secciones)
    materias = set(s["clave"] for s in secciones_carga)
    diferencia = abs(len(materias) - materias_deseadas)
    return min(1.0, diferencia / materias_deseadas)


# =============================================================================
# VALIDACIÓN DE CARGAS
# =============================================================================

def es_carga_valida(
    secciones: List[Dict],
    disponibilidad: Dict[str, List[int]],
    max_materias: int,
    max_creditos: int = 54,
    min_creditos: int = 0,
) -> bool:
    """Verifica que una carga sea válida."""
    if not secciones:
        return False

    # Verificar materias únicas (no duplicar misma materia)
    claves = [s["clave"] for s in secciones]
    if len(claves) != len(set(claves)):
        return False

    # Verificar límite de materias
    if len(claves) > max_materias:
        return False

    # Verificar créditos
    total_creditos = sum(s["creditos"] for s in secciones)
    if total_creditos > max_creditos or total_creditos < min_creditos:
        return False

    # Verificar disponibilidad para cada sección
    if disponibilidad:
        for seccion in secciones:
            if not verificar_disponibilidad(seccion["horario"], disponibilidad):
                return False

    # Verificar choques entre todas las parejas de secciones
    for i in range(len(secciones)):
        for j in range(i + 1, len(secciones)):
            if verificar_choque_horario(secciones[i]["horario"], secciones[j]["horario"]):
                return False

    return True


# =============================================================================
# NSGA-III
# =============================================================================

def _generar_individuo(
    secciones_por_materia: Dict[str, List[Dict]],
    materias_ordenadas: List[str],
    disponibilidad: Dict[str, List[int]],
    max_materias: int,
    max_creditos: int,
) -> Optional[List[Dict]]:
    """Genera un individuo (carga) válido aleatoriamente."""
    carga = []
    claves_usadas = set()
    creditos_total = 0
    intentos_orden = list(materias_ordenadas)
    random.shuffle(intentos_orden)

    for clave in intentos_orden:
        if len(claves_usadas) >= max_materias:
            break
        if clave in claves_usadas:
            continue

        opciones = list(secciones_por_materia.get(clave, []))
        random.shuffle(opciones)

        for seccion in opciones:
            nuevos_creditos = creditos_total + seccion["creditos"]
            if nuevos_creditos > max_creditos:
                continue

            # Verificar disponibilidad
            if disponibilidad and not verificar_disponibilidad(seccion["horario"], disponibilidad):
                continue

            # Verificar choques con carga actual
            tiene_choque = False
            for existente in carga:
                if verificar_choque_horario(seccion["horario"], existente["horario"]):
                    tiene_choque = True
                    break

            if not tiene_choque:
                carga.append(seccion)
                claves_usadas.add(clave)
                creditos_total = nuevos_creditos
                break

    return carga if carga else None


def _dominates(obj_a: Tuple[float, ...], obj_b: Tuple[float, ...]) -> bool:
    """Verifica si a domina a b (todos objetivos iguales o mejores, al menos uno estrictamente mejor)."""
    al_menos_uno_mejor = False
    for a, b in zip(obj_a, obj_b):
        if a > b:  # Mayor es peor (minimizamos todo excepto prioridad que invertimos)
            return False
        if a < b:
            al_menos_uno_mejor = True
    return al_menos_uno_mejor


def _non_dominated_sort(population: List[Tuple[float, ...]]) -> List[List[int]]:
    """Ordena la población en frentes de no-dominancia."""
    n = len(population)
    domination_count = [0] * n
    dominated_by = [[] for _ in range(n)]
    frentes = [[]]

    for i in range(n):
        for j in range(i + 1, n):
            if _dominates(population[i], population[j]):
                dominated_by[i].append(j)
                domination_count[j] += 1
            elif _dominates(population[j], population[i]):
                dominated_by[j].append(i)
                domination_count[i] += 1

        if domination_count[i] == 0:
            frentes[0].append(i)

    k = 0
    while frentes[k]:
        siguiente = []
        for i in frentes[k]:
            for j in dominated_by[i]:
                domination_count[j] -= 1
                if domination_count[j] == 0:
                    siguiente.append(j)
        k += 1
        frentes.append(siguiente)

    return [f for f in frentes if f]


def _cruce_uniforme(padre1: List[Dict], padre2: List[Dict], prob: float = 0.5) -> List[Dict]:
    """Cruce uniforme: toma materias de ambos padres sin duplicar."""
    claves_p1 = {s["clave"]: s for s in padre1}
    claves_p2 = {s["clave"]: s for s in padre2}
    todas = set(claves_p1.keys()) | set(claves_p2.keys())

    hijo = []
    for clave in todas:
        if random.random() < prob:
            if clave in claves_p1:
                hijo.append(claves_p1[clave])
        else:
            if clave in claves_p2:
                hijo.append(claves_p2[clave])
    return hijo


def _mutacion(
    individuo: List[Dict],
    secciones_por_materia: Dict[str, List[Dict]],
    prob: float = 0.15,
) -> List[Dict]:
    """Mutación: cambia sección de una materia o agrega/quita una materia."""
    resultado = list(individuo)

    if random.random() < prob and resultado:
        # Cambiar sección de una materia aleatoria
        idx = random.randint(0, len(resultado) - 1)
        clave = resultado[idx]["clave"]
        opciones = secciones_por_materia.get(clave, [])
        if len(opciones) > 1:
            nueva = random.choice(opciones)
            resultado[idx] = nueva

    if random.random() < prob * 0.5:
        # Quitar una materia aleatoria
        if len(resultado) > 1:
            idx = random.randint(0, len(resultado) - 1)
            resultado.pop(idx)

    return resultado


def generar_cargas_nsga3(
    secciones_disponibles: List[Dict],
    disponibilidad: Dict[str, List[int]],
    materias_deseadas: int = 5,
    max_materias: int = 8,
    max_creditos: int = 54,
    min_creditos: int = 0,
    poblacion_size: int = 100,
    generaciones: int = 50,
    n_resultados: int = 3,
) -> List[Dict]:
    """
    Genera cargas académicas optimizadas usando NSGA-III.

    Args:
        secciones_disponibles: Secciones filtradas por oferta y candidatas
        disponibilidad: Horas disponibles por día
        materias_deseadas: Número aproximado de materias que quiere el estudiante
        max_materias: Máximo de materias permitido (3 si condicionado)
        max_creditos: Máximo de créditos por semestre
        min_creditos: Mínimo de créditos por semestre
        poblacion_size: Tamaño de la población del GA
        generaciones: Número de generaciones
        n_resultados: Cuántas cargas recomendar

    Returns:
        Lista de cargas recomendadas, cada una con:
        {
            "secciones": [...],
            "total_materias": int,
            "total_creditos": int,
            "score_prioridad": float,
            "score_compacidad": float,
            "score_cantidad": float,
            "etiqueta": str  ("Recomendada", "Alternativa 1", etc.)
        }
    """
    if not secciones_disponibles:
        return []

    # Agrupar secciones por materia
    secciones_por_materia: Dict[str, List[Dict]] = {}
    for s in secciones_disponibles:
        secciones_por_materia.setdefault(s["clave"], []).append(s)

    materias_ordenadas = sorted(
        secciones_por_materia.keys(),
        key=lambda c: min(s["prioridad"] for s in secciones_por_materia[c])
    )

    # Ajustar materias deseadas al máximo permitido
    materias_deseadas = min(materias_deseadas, max_materias)

    # --- Generar población inicial ---
    poblacion = []
    intentos = 0
    max_intentos = poblacion_size * 20

    while len(poblacion) < poblacion_size and intentos < max_intentos:
        individuo = _generar_individuo(
            secciones_por_materia, materias_ordenadas,
            disponibilidad, max_materias, max_creditos
        )
        if individuo:
            poblacion.append(individuo)
        intentos += 1

    if not poblacion:
        # Fallback: generar cargas greedy sin NSGA-III
        return _generar_cargas_greedy(
            secciones_por_materia, materias_ordenadas,
            disponibilidad, materias_deseadas, max_materias,
            max_creditos, n_resultados
        )

    # --- Evolución NSGA-III ---
    for gen in range(generaciones):
        # Evaluar objetivos (minimizar todos: invertimos prioridad)
        objetivos = []
        for ind in poblacion:
            obj = (
                1.0 - objetivo_prioridad(ind),       # Minimizar (invertido)
                objetivo_compacidad(ind),              # Minimizar
                objetivo_cantidad(ind, materias_deseadas),  # Minimizar
            )
            objetivos.append(obj)

        # Selección por frentes de no-dominancia
        frentes = _non_dominated_sort(objetivos)

        # Construir nueva población con los mejores frentes
        nueva_poblacion = []
        for frente in frentes:
            if len(nueva_poblacion) + len(frente) <= poblacion_size:
                nueva_poblacion.extend(frente)
            else:
                # Llenar con los que quepan (por crowding distance simplificado)
                restantes = poblacion_size - len(nueva_poblacion)
                nueva_poblacion.extend(frente[:restantes])
                break

        # Reconstruir población con índices
        padres = [poblacion[i] for i in nueva_poblacion]

        # Generar hijos por cruce y mutación
        hijos = []
        while len(hijos) < poblacion_size // 2:
            if len(padres) < 2:
                break
            p1, p2 = random.sample(padres, 2)
            hijo = _cruce_uniforme(p1, p2)
            hijo = _mutacion(hijo, secciones_por_materia)

            # Validar hijo
            if es_carga_valida(hijo, disponibilidad, max_materias, max_creditos, min_creditos):
                hijos.append(hijo)

        poblacion = padres + hijos
        # Limitar tamaño
        poblacion = poblacion[:poblacion_size * 2]

    # --- Seleccionar mejores resultados ---
    # Evaluar toda la población final
    evaluados = []
    vistos = set()
    for ind in poblacion:
        claves_key = tuple(sorted(s["clave"] for s in ind))
        if claves_key in vistos:
            continue
        vistos.add(claves_key)

        if not es_carga_valida(ind, disponibilidad, max_materias, max_creditos, min_creditos):
            continue

        score_pri = objetivo_prioridad(ind)
        score_comp = objetivo_compacidad(ind)
        score_cant = objetivo_cantidad(ind, materias_deseadas)

        # Score combinado ponderado (para ranking final)
        score_total = 0.5 * score_pri + 0.3 * (1 - score_comp) + 0.2 * (1 - score_cant)

        evaluados.append({
            "secciones": sorted(ind, key=lambda s: (s["prioridad"], s["ciclo"])),
            "total_materias": len(set(s["clave"] for s in ind)),
            "total_creditos": sum(s["creditos"] for s in ind),
            "score_prioridad": round(score_pri, 3),
            "score_compacidad": round(1 - score_comp, 3),
            "score_cantidad": round(1 - score_cant, 3),
            "score_total": round(score_total, 3),
        })

    # Ordenar por score total descendente
    evaluados.sort(key=lambda e: e["score_total"], reverse=True)

    # Tomar los top N con cargas diferentes
    resultados = []
    for ev in evaluados:
        if len(resultados) >= n_resultados:
            break
        resultados.append(ev)

    # Etiquetar
    etiquetas = ["Recomendada", "Alternativa 1", "Alternativa 2",
                 "Alternativa 3", "Alternativa 4"]
    for i, r in enumerate(resultados):
        r["etiqueta"] = etiquetas[i] if i < len(etiquetas) else f"Alternativa {i}"

    return resultados


def _generar_cargas_greedy(
    secciones_por_materia: Dict[str, List[Dict]],
    materias_ordenadas: List[str],
    disponibilidad: Dict[str, List[int]],
    materias_deseadas: int,
    max_materias: int,
    max_creditos: int,
    n_resultados: int,
) -> List[Dict]:
    """
    Fallback greedy cuando NSGA-III no puede generar población.
    Selecciona materias en orden de prioridad, eligiendo la mejor sección.
    """
    resultados = []

    for intento in range(n_resultados * 5):
        carga = []
        claves_usadas = set()
        creditos_total = 0
        orden = list(materias_ordenadas)
        if intento > 0:
            random.shuffle(orden)

        for clave in orden:
            if len(claves_usadas) >= min(materias_deseadas + intento % 2, max_materias):
                break
            if clave in claves_usadas:
                continue

            opciones = list(secciones_por_materia.get(clave, []))
            if intento > 0:
                random.shuffle(opciones)

            for seccion in opciones:
                nuevos_creditos = creditos_total + seccion["creditos"]
                if nuevos_creditos > max_creditos:
                    continue

                if disponibilidad and not verificar_disponibilidad(seccion["horario"], disponibilidad):
                    continue

                tiene_choque = any(
                    verificar_choque_horario(seccion["horario"], e["horario"])
                    for e in carga
                )
                if not tiene_choque:
                    carga.append(seccion)
                    claves_usadas.add(clave)
                    creditos_total = nuevos_creditos
                    break

        if carga:
            claves_key = tuple(sorted(s["clave"] for s in carga))
            ya_existe = any(
                tuple(sorted(s["clave"] for s in r["secciones"])) == claves_key
                for r in resultados
            )
            if not ya_existe:
                score_pri = objetivo_prioridad(carga)
                score_comp = objetivo_compacidad(carga)
                score_cant = objetivo_cantidad(carga, materias_deseadas)

                resultados.append({
                    "secciones": sorted(carga, key=lambda s: (s["prioridad"], s["ciclo"])),
                    "total_materias": len(claves_usadas),
                    "total_creditos": creditos_total,
                    "score_prioridad": round(score_pri, 3),
                    "score_compacidad": round(1 - score_comp, 3),
                    "score_cantidad": round(1 - score_cant, 3),
                    "score_total": round(0.5 * score_pri + 0.3 * (1 - score_comp) + 0.2 * (1 - score_cant), 3),
                })

        if len(resultados) >= n_resultados:
            break

    resultados.sort(key=lambda e: e["score_total"], reverse=True)
    etiquetas = ["Recomendada", "Alternativa 1", "Alternativa 2"]
    for i, r in enumerate(resultados):
        r["etiqueta"] = etiquetas[i] if i < len(etiquetas) else f"Alternativa {i}"

    return resultados
