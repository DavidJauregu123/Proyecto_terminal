"""
Agente Asesor Curricular — LangChain + LangGraph + Gemini.
12 tools inteligentes con análisis pre-computado para asesor curricular.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import pandas as pd

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agents.knowledge_base import SYSTEM_PROMPT
from config import settings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MAPA_PATH = _PROJECT_ROOT / "data" / "mapa_curricular_2021ID_real_completo.json"
_mapa_cache: Optional[dict] = None


def _cargar_mapa() -> dict:
    global _mapa_cache
    if _mapa_cache is None:
        with open(_MAPA_PATH, "r", encoding="utf-8") as f:
            _mapa_cache = json.load(f)
    return _mapa_cache


def _norm(s: str) -> str:
    """Normaliza: minúsculas + sin acentos."""
    return unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()


def _buscar_en_mapa(consulta: str) -> list:
    """Busca materias en el mapa por clave exacta, nombre parcial o palabras sueltas. Sin acentos."""
    mapa = _cargar_mapa()
    q = consulta.strip()
    q_up = q.upper()

    if q_up in mapa:
        return [(q_up, mapa[q_up])]

    q_n = _norm(q)
    palabras = [p for p in q_n.split() if len(p) > 2]
    matches = []
    for k, info in mapa.items():
        nombre_n = _norm(info.get("nombre", ""))
        k_low = k.lower()
        if q_n in nombre_n or q_n in k_low:
            matches.append((k, info))
        elif palabras and all(p in nombre_n or p in k_low for p in palabras):
            matches.append((k, info))
    return matches


def _contar_dependientes(clave: str, mapa: dict) -> list:
    """Retorna lista de claves que requieren esta materia como prerrequisito."""
    return [k for k, v in mapa.items() if clave in v.get("requisitos", [])]


def _cadena_impacto(clave: str, mapa: dict, profundidad: int = 3) -> list:
    """Calcula el impacto en cascada: si repruebas esta materia, qué se bloquea en cadena."""
    bloqueadas = set()
    nivel_actual = {clave}
    for _ in range(profundidad):
        siguiente = set()
        for c in nivel_actual:
            for dep in _contar_dependientes(c, mapa):
                if dep not in bloqueadas:
                    bloqueadas.add(dep)
                    siguiente.add(dep)
        nivel_actual = siguiente
        if not nivel_actual:
            break
    return sorted(bloqueadas)


_session_ref: Dict[str, Any] = {}


def set_session_state(d: Dict[str, Any]):
    global _session_ref
    _session_ref = d


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL 1: Resumen del estudiante con evaluación de regularidad
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS DE ANALISIS — funciones compartidas entre tools
# ═══════════════════════════════════════════════════════════════════════════

def _analizar_tendencia_promedio(df) -> dict:
    """Analiza la tendencia del promedio en los ultimos periodos.
    Retorna: {tendencia, ultimos_promedios, diff}"""
    if df is None or df.empty or "calificacion" not in df.columns:
        return {"tendencia": "sin datos", "ultimos_promedios": [], "diff": 0.0}

    try:
        df2 = df.copy()
        df2["calificacion"] = pd.to_numeric(df2["calificacion"], errors="coerce")
        # Solo calificadas con numero
        df2 = df2[df2["calificacion"].notna() & (df2["calificacion"] > 0)]
        df2 = df2[df2["estatus"].str.upper().isin(["APROBADA", "REPROBADA"])]
        if df2.empty:
            return {"tendencia": "sin datos", "ultimos_promedios": [], "diff": 0.0}

        # Promedio por periodo
        promedios = df2.groupby("periodo")["calificacion"].mean().sort_index()
        if len(promedios) < 2:
            return {"tendencia": "insuficiente", "ultimos_promedios": list(promedios.items()), "diff": 0.0}

        ultimos = promedios.tail(3)
        lista = [(str(p), round(float(v), 2)) for p, v in ultimos.items()]

        # Diferencia entre el ultimo y el anterior
        vals = ultimos.values
        diff = float(vals[-1] - vals[0]) if len(vals) >= 2 else 0.0

        if diff >= 0.3:
            tendencia = "subiendo"
        elif diff <= -0.3:
            tendencia = "bajando"
        else:
            tendencia = "estable"

        return {"tendencia": tendencia, "ultimos_promedios": lista, "diff": round(diff, 2)}
    except Exception:
        return {"tendencia": "sin datos", "ultimos_promedios": [], "diff": 0.0}


def _proyectar_egreso(df, cred_acum: int, cred_total: int) -> dict:
    """Proyecta cuantos periodos le faltan al alumno para egresar con su ritmo actual.
    Retorna: {periodos_restantes, creditos_por_periodo, fecha_estimada}"""
    if df is None or df.empty or cred_acum >= cred_total:
        return {"periodos_restantes": 0, "creditos_por_periodo": 0, "ok": False}

    try:
        aprobadas = df[df["estatus"].str.upper() == "APROBADA"]
        if aprobadas.empty or "periodo" not in aprobadas.columns:
            return {"periodos_restantes": 0, "creditos_por_periodo": 0, "ok": False}

        periodos_activos = aprobadas["periodo"].nunique()
        if periodos_activos == 0:
            return {"periodos_restantes": 0, "creditos_por_periodo": 0, "ok": False}

        cred_por_periodo = cred_acum / periodos_activos
        cred_falt = cred_total - cred_acum
        periodos_restantes = cred_falt / cred_por_periodo if cred_por_periodo > 0 else 0

        return {
            "periodos_restantes": round(periodos_restantes, 1),
            "creditos_por_periodo": round(cred_por_periodo, 1),
            "ok": True,
        }
    except Exception:
        return {"periodos_restantes": 0, "creditos_por_periodo": 0, "ok": False}


def _carga_promedio(df) -> dict:
    """Calcula la carga promedio de materias por periodo del estudiante.
    Retorna: {promedio, max, min, total_periodos}"""
    if df is None or df.empty or "periodo" not in df.columns:
        return {"promedio": 0, "max": 0, "min": 0, "total_periodos": 0}

    try:
        # Solo periodos con materias APROBADA o REPROBADA (no EN_CURSO ni SIN_REGISTRAR)
        df2 = df[df["estatus"].str.upper().isin(["APROBADA", "REPROBADA"])]
        if df2.empty:
            return {"promedio": 0, "max": 0, "min": 0, "total_periodos": 0}

        por_periodo = df2.groupby("periodo").size()
        return {
            "promedio": round(float(por_periodo.mean()), 1),
            "max": int(por_periodo.max()),
            "min": int(por_periodo.min()),
            "total_periodos": int(len(por_periodo)),
        }
    except Exception:
        return {"promedio": 0, "max": 0, "min": 0, "total_periodos": 0}


def _tasa_aprobacion_por_categoria(df, mapa: dict) -> dict:
    """Calcula la tasa de aprobacion por categoria del plan.
    Retorna: {categoria: {aprobadas, reprobadas, tasa}}"""
    if df is None or df.empty:
        return {}

    try:
        resultado = {}
        df2 = df[df["estatus"].str.upper().isin(["APROBADA", "REPROBADA"])].copy()
        if df2.empty:
            return {}

        df2["categoria"] = df2["clave"].str.upper().map(
            lambda c: mapa.get(c, {}).get("categoria", "DESCONOCIDA")
        )

        for cat, grupo in df2.groupby("categoria"):
            apr = int((grupo["estatus"].str.upper() == "APROBADA").sum())
            rep = int((grupo["estatus"].str.upper() == "REPROBADA").sum())
            total = apr + rep
            tasa = round((apr / total * 100), 1) if total > 0 else 0
            resultado[cat] = {"aprobadas": apr, "reprobadas": rep, "tasa": tasa}

        return resultado
    except Exception:
        return {}


def _mejor_peor_periodo(df) -> dict:
    """Identifica el mejor y peor periodo del estudiante.
    Retorna: {mejor: {periodo, promedio}, peor: {periodo, promedio}}"""
    if df is None or df.empty:
        return {}

    try:
        df2 = df.copy()
        df2["calificacion"] = pd.to_numeric(df2["calificacion"], errors="coerce")
        df2 = df2[df2["calificacion"].notna() & (df2["calificacion"] > 0)]
        df2 = df2[df2["estatus"].str.upper().isin(["APROBADA", "REPROBADA"])]
        if df2.empty or "periodo" not in df2.columns:
            return {}

        por_periodo = df2.groupby("periodo")["calificacion"].mean()
        if por_periodo.empty:
            return {}

        mejor_p = por_periodo.idxmax()
        peor_p = por_periodo.idxmin()

        return {
            "mejor": {"periodo": str(mejor_p), "promedio": round(float(por_periodo[mejor_p]), 2)},
            "peor": {"periodo": str(peor_p), "promedio": round(float(por_periodo[peor_p]), 2)},
        }
    except Exception:
        return {}


def _distribucion_calificaciones(df) -> dict:
    """Cuenta cuantas materias aprobadas tiene con cada calificacion (10, 9, 8, 7)."""
    if df is None or df.empty:
        return {}

    try:
        aprobadas = df[df["estatus"].str.upper() == "APROBADA"].copy()
        aprobadas["calificacion"] = pd.to_numeric(aprobadas["calificacion"], errors="coerce")
        aprobadas = aprobadas[aprobadas["calificacion"].notna()]
        if aprobadas.empty:
            return {}

        dist = {}
        for calif in [10, 9, 8, 7]:
            dist[calif] = int((aprobadas["calificacion"] == calif).sum())
        return dist
    except Exception:
        return {}


@tool
def resumen_estudiante() -> str:
    """Retorna datos del estudiante + evaluación de regularidad + alertas + requisitos de egreso. Úsalo para cualquier pregunta sobre cómo va el alumno."""
    datos = _session_ref.get("datos_estudiante")
    if not datos:
        return (
            "No tengo acceso a datos del estudiante. "
            "Verifica que el Historial Academico y el Kardex esten subidos en el panel lateral "
            "y que el procesamiento haya terminado (debe aparecer un mensaje de exito). "
            "Si ya los subiste, intenta recargar la pagina o volver a subir los PDF."
        )

    cred_total = _session_ref.get("creditos_totales", 404)
    cred_acum = _session_ref.get("creditos_acumulados", datos.total_creditos)
    cred_falt = max(0, cred_total - cred_acum)
    pct = round((cred_acum / cred_total) * 100, 1) if cred_total > 0 else 0

    resultado = _session_ref.get("resultado_experto")
    sem = resultado.get("semestre_cursado", 0) if resultado else 0
    esp = resultado.get("especialidad_detectada", "No detectada") if resultado else "No detectada"

    # Inglés
    nivel_ing = _session_ref.get("nivel_ingles_texto", "No disponible")
    ing_ok = _session_ref.get("ingles_completo", False)

    # Situación
    sit = str(getattr(datos, "situacion", "")).upper()
    es_condicional = "CONDICIONAL" in sit

    # Análisis del historial
    # Se reportan DOS metricas de reprobacion porque miden cosas distintas:
    # 1) Indice actual (del dashboard): usa historial_calculo (canonico: ultimo estado por materia).
    #    Formula: materias con ultimo estado REPROBADA / materias cursadas. Esto es lo oficial.
    # 2) Total historico de reprobaciones: usa historial_df (raw: todos los intentos).
    #    Cuenta cada intento reprobado aunque despues el alumno haya aprobado la materia.
    df_raw = _session_ref.get("historial_df")
    _hc = _session_ref.get("historial_calculo")
    df = _hc if (_hc is not None and hasattr(_hc, "empty") and not _hc.empty) else df_raw
    aprobadas = 0
    reprobadas_detalle = []
    en_curso_count = 0
    _mat_reprobadas_count = 0
    _mat_cursadas_count = 0
    _indice_reprobacion = 0.0
    _intentos_reprobados_total = 0
    _materias_con_reprobacion_distintas = 0
    if df is not None and not df.empty:
        aprobadas = len(df[df["estatus"].str.upper() == "APROBADA"])
        # EN_CURSO/RECURSANDO (sólo en el raw, historial_calculo ya los excluye)
        if df_raw is not None and not df_raw.empty:
            en_curso = df_raw[df_raw["estatus"].str.upper().isin(["EN_CURSO", "RECURSANDO"])]
            en_curso_count = len(en_curso)

        # Indice OFICIAL (canonico): materias pendientes de aprobar ahora
        _mat_reprobadas_count = int((df["estatus"].str.upper() == "REPROBADA").sum())
        _mat_cursadas_count = int(df["estatus"].str.upper().isin(["APROBADA", "REPROBADA"]).sum())
        _indice_reprobacion = (_mat_reprobadas_count / _mat_cursadas_count * 100) if _mat_cursadas_count > 0 else 0.0

        # Metrica HISTORICA: todos los intentos reprobados (aunque despues hayan sido aprobados)
        if df_raw is not None and not df_raw.empty:
            _intentos_reprobados_total = int((df_raw["estatus"].str.upper() == "REPROBADA").sum())
            rep_raw = df_raw[df_raw["estatus"].str.upper() == "REPROBADA"]
            if not rep_raw.empty:
                _materias_con_reprobacion_distintas = int(rep_raw["clave"].nunique())

        # Materias que AHORA siguen reprobadas (no aprobadas despues)
        rep = df[df["estatus"].str.upper() == "REPROBADA"]
        if not rep.empty:
            # Contar cuantos intentos totales tuvo cada clave (en el raw)
            for clave in rep["clave"].unique():
                nombre_rows = df[df["clave"] == clave]["nombre"]
                nombre = nombre_rows.iloc[0] if len(nombre_rows) > 0 else clave
                # Total de intentos reprobados en la historia
                if df_raw is not None and not df_raw.empty:
                    veces = int(((df_raw["clave"] == clave) & (df_raw["estatus"].str.upper() == "REPROBADA")).sum())
                else:
                    veces = 1
                if veces >= 3:
                    reprobadas_detalle.append(f"  BAJA DEFINITIVA: {clave} ({nombre}) — {veces} reprobaciones")
                elif veces == 2:
                    reprobadas_detalle.append(f"  TERCERA OPORTUNIDAD: {clave} ({nombre}) — próximo intento es el último")
                else:
                    reprobadas_detalle.append(f"  {clave} ({nombre}) — 1 reprobación previa")

    mapa = _cargar_mapa()
    mat_pend = len(mapa) - aprobadas

    # Evaluación de regularidad
    avance_esperado = round((sem / 8) * 100) if sem > 0 else 0
    diferencia = pct - avance_esperado
    if diferencia >= -5:
        regularidad = "AL CORRIENTE"
    elif diferencia >= -15:
        regularidad = "LIGERAMENTE ATRASADO"
    else:
        regularidad = "SIGNIFICATIVAMENTE ATRASADO"

    # Riesgo — combinar checks propios + alertas del procesador
    riesgos = []
    if es_condicional:
        riesgos.append("Alumno CONDICIONAL (carga fija: exactamente 3 materias)")
    if any("TERCERA" in r for r in reprobadas_detalle):
        riesgos.append("Tiene materias en TERCERA OPORTUNIDAD")
    if any("BAJA" in r for r in reprobadas_detalle):
        riesgos.append("Tiene materias con BAJA DEFINITIVA")
    if not ing_ok and sem >= 6:
        riesgos.append("Inglés incompleto y ya va en semestre avanzado")
    # Alertas del procesador (MATERIAS_REPROBADAS, ATRASO_PRÁCTICAS, PREREQUISITO_SALTADO, etc.)
    alertas_proc = _session_ref.get("alertas_academicas") or []
    for alerta in alertas_proc:
        tipo = alerta.get("tipo", "")
        desc = alerta.get("descripcion", "")
        sev = alerta.get("severidad", "")
        # Evitar duplicar lo que ya chequeamos arriba
        if tipo in ("TERCERA_OPORTUNIDAD", "BAJA_AUTOMÁTICA"):
            continue
        prefijo = "🔴" if sev == "CRITICA" else "🟠"
        riesgos.append(f"{prefijo} {tipo}: {desc}")

    # ── Analisis enriquecido ──
    df_analisis = df_raw if df_raw is not None else df
    tendencia = _analizar_tendencia_promedio(df_analisis)
    proyeccion = _proyectar_egreso(df_analisis, cred_acum, cred_total)
    carga = _carga_promedio(df_analisis)
    tasas_cat = _tasa_aprobacion_por_categoria(df_analisis, mapa)

    out = (
        f"DATOS: {datos.matricula} | {datos.nombre} | {datos.situacion}\n"
        f"Plan: {datos.plan_estudios} | Promedio: {datos.promedio_general}\n"
        f"Créditos: {cred_acum}/{cred_total} ({pct}%) | Faltan: {cred_falt}\n"
        f"Semestre: {sem}/8 | Restantes: {max(0,8-sem)} | En curso: {en_curso_count} materias\n"
        f"Materias: {aprobadas} aprobadas, {mat_pend} pendientes\n"
        f"Índice de reprobación actual (oficial): {_indice_reprobacion:.1f}% — {_mat_reprobadas_count} materias pendientes de aprobar / {_mat_cursadas_count} cursadas\n"
    )

    # Metrica historica solo si difiere del indice actual
    if _intentos_reprobados_total > _mat_reprobadas_count:
        out += (
            f"Historial de intentos reprobados: {_intentos_reprobados_total} intentos en {_materias_con_reprobacion_distintas} materias distintas "
            f"(incluye materias que ya aprobó en intentos posteriores)\n"
        )

    out += (
        f"Especialidad: {esp}\n"
        f"\nREGULARIDAD: {regularidad} (avance real {pct}% vs esperado ~{avance_esperado}%)\n"
        f"RIESGOS: {'; '.join(riesgos) if riesgos else 'Ninguno identificado'}\n"
        f"\nINGLÉS: {nivel_ing} | Completo: {'Sí' if ing_ok else 'No — PENDIENTE'}\n"
    )

    # Tendencia del promedio
    if tendencia["ultimos_promedios"]:
        ultimos_str = " -> ".join(f"{p}:{v}" for p, v in tendencia["ultimos_promedios"])
        flecha = {"subiendo": "^", "bajando": "v", "estable": "~"}.get(tendencia["tendencia"], "")
        diff = tendencia["diff"]
        diff_str = f"(+{diff})" if diff > 0 else f"({diff})"
        out += f"\nTENDENCIA PROMEDIO: {tendencia['tendencia'].upper()} {flecha} {diff_str}\n"
        out += f"  Últimos periodos: {ultimos_str}\n"

    # Carga promedio
    if carga["total_periodos"] > 0:
        out += f"\nCARGA ACADÉMICA HISTÓRICA:\n"
        out += f"  Promedio: {carga['promedio']} materias/periodo | Max: {carga['max']} | Min: {carga['min']}\n"
        out += f"  Periodos cursados: {carga['total_periodos']}\n"

    # Proyeccion de egreso
    if proyeccion["ok"]:
        out += f"\nPROYECCIÓN DE EGRESO (con ritmo actual):\n"
        out += f"  Créditos por periodo: {proyeccion['creditos_por_periodo']}\n"
        out += f"  Periodos restantes estimados: {proyeccion['periodos_restantes']}\n"

    # Tasa de aprobacion por categoria
    if tasas_cat:
        out += f"\nTASA DE APROBACIÓN POR CATEGORÍA:\n"
        orden_cat = ["BASICA", "PRE_ESPECIALIDAD", "ELECCION_LIBRE", "CO_CURRICULAR"]
        for cat in orden_cat:
            if cat in tasas_cat:
                d = tasas_cat[cat]
                out += f"  {cat}: {d['tasa']}% ({d['aprobadas']} aprobadas / {d['aprobadas']+d['reprobadas']} cursadas)\n"
        for cat, d in tasas_cat.items():
            if cat not in orden_cat:
                out += f"  {cat}: {d['tasa']}% ({d['aprobadas']} aprobadas / {d['aprobadas']+d['reprobadas']} cursadas)\n"

    if reprobadas_detalle:
        out += "\nREPROBADAS:\n" + "\n".join(reprobadas_detalle)
    else:
        out += "\nREPROBADAS: Ninguna"

    return out


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL 2: Diagnóstico académico — riesgo, cuellos de botella, prioridades
# ═══════════════════════════════════════════════════════════════════════════

@tool
def diagnostico_academico() -> str:
    """Análisis profundo: materias críticas por seriación, cuellos de botella, riesgo de atraso, y materias que el alumno debería priorizar. Para preguntas como '¿está en riesgo?', '¿qué debería priorizar?', '¿cuáles son las más importantes?'."""
    datos = _session_ref.get("datos_estudiante")
    if not datos:
        return (
            "No tengo acceso a datos del estudiante. "
            "Verifica que los PDF (Historial y Kardex) esten subidos y procesados en el panel lateral."
        )

    mapa = _cargar_mapa()
    df = _session_ref.get("historial_df")
    resultado = _session_ref.get("resultado_experto")

    if df is None or df.empty:
        return "Sin historial cargado."

    aprobadas_set = set(df[df["estatus"].str.upper() == "APROBADA"]["clave"].str.upper())
    en_curso_set = set(df[df["estatus"].str.upper().isin(["EN_CURSO", "RECURSANDO"])]["clave"].str.upper())

    sem_actual = resultado.get("semestre_cursado", 0) if resultado else 0

    # 1. Materias atrasadas (de ciclos anteriores no aprobadas ni en curso)
    atrasadas = []
    for clave, info in mapa.items():
        ciclo = info.get("ciclo", 99)
        if ciclo < sem_actual and clave not in aprobadas_set and clave not in en_curso_set:
            cat = info.get("categoria", "")
            if cat == "BASICA":  # Solo básicas obligatorias
                deps = _cadena_impacto(clave, mapa)
                atrasadas.append((clave, info.get("nombre", ""), ciclo, len(deps), deps))

    # Ordenar por impacto (más dependientes primero)
    atrasadas.sort(key=lambda x: -x[3])

    # 2. Cuellos de botella: materias pendientes que más bloquean
    cuellos = []
    for clave, info in mapa.items():
        if clave in aprobadas_set:
            continue
        deps = _contar_dependientes(clave, mapa)
        deps_pendientes = [d for d in deps if d not in aprobadas_set]
        if len(deps_pendientes) >= 2:
            cuellos.append((clave, info.get("nombre", ""), len(deps_pendientes),
                            ", ".join(deps_pendientes[:5])))
    cuellos.sort(key=lambda x: -x[2])

    # 3. Materias en curso que son críticas
    criticas_en_curso = []
    for clave in en_curso_set:
        impacto = _cadena_impacto(clave, mapa)
        impacto_pendiente = [i for i in impacto if i not in aprobadas_set]
        if impacto_pendiente:
            nombre = mapa.get(clave, {}).get("nombre", clave)
            criticas_en_curso.append((clave, nombre, len(impacto_pendiente), impacto_pendiente[:4]))

    criticas_en_curso.sort(key=lambda x: -x[2])

    out = "DIAGNÓSTICO ACADÉMICO\n"
    out += "=" * 40 + "\n"

    # Atrasadas
    if atrasadas:
        out += f"\nMATERIAS ATRASADAS (básicas de ciclos anteriores al {sem_actual}, no cursadas):\n"
        for clave, nombre, ciclo, n_deps, deps in atrasadas[:8]:
            out += f"  ⚠ {clave} {nombre} (ciclo {ciclo}) — bloquea {n_deps} materias"
            if deps:
                out += f": {', '.join(deps[:3])}"
            out += "\n"
    else:
        out += "\nMATERIAS ATRASADAS: Ninguna — el alumno va al corriente con las básicas.\n"

    # Cuellos de botella
    if cuellos:
        out += f"\nCUELLOS DE BOTELLA (materias pendientes que más bloquean):\n"
        for clave, nombre, n_deps, deps_str in cuellos[:5]:
            out += f"  🔴 {clave} {nombre} — bloquea {n_deps} pendientes: {deps_str}\n"

    # Críticas en curso
    if criticas_en_curso:
        out += f"\nMATERIAS EN CURSO CRÍTICAS (si las reprueba, se bloquean más):\n"
        for clave, nombre, n_imp, imps in criticas_en_curso[:5]:
            out += f"  ⚡ {clave} {nombre} — reprobar bloquea {n_imp}: {', '.join(imps)}\n"

    return out


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL 3: Buscar materia con análisis de impacto
# ═══════════════════════════════════════════════════════════════════════════

@tool
def buscar_materia(consulta: str) -> str:
    """Busca materia por nombre o clave. Retorna: info, prerrequisitos cumplidos/faltantes, dependientes, impacto en cadena si reprueba, historial del estudiante, periodo ideal recomendado, y contexto segun categoria (pre-especialidad o eleccion libre). Para preguntas como 'que pasa si reprueba X?', 'que materias dependen de X?', 'cuando deberia llevar Y?'."""
    mapa = _cargar_mapa()
    matches = _buscar_en_mapa(consulta)

    if not matches:
        return f"'{consulta}' no encontrada en el plan IDeIO 2021."

    resultados = []
    df = _session_ref.get("historial_df")
    aprobadas_set = set()
    if df is not None and not df.empty:
        aprobadas_set = set(df[df["estatus"].str.upper() == "APROBADA"]["clave"].str.upper())

    resultado_exp = _session_ref.get("resultado_experto") or {}
    sem_actual = resultado_exp.get("semestre_cursado", 0)
    esp_activa = (
        _session_ref.get("especialidad_forzada")
        or resultado_exp.get("especialidad_detectada")
        or ""
    )

    for clave, info in matches[:3]:
        ciclo_materia = info.get("ciclo", 0)
        categoria = info.get("categoria", "")
        reqs_lista = info.get("requisitos", [])
        reqs = ", ".join(reqs_lista) or "Ninguno"

        # Prerrequisitos cumplidos vs faltantes
        reqs_cumplidos = [r for r in reqs_lista if r.upper() in aprobadas_set]
        reqs_faltantes = [r for r in reqs_lista if r.upper() not in aprobadas_set]

        # Dependientes directos
        deps_directos = _contar_dependientes(clave, mapa)
        deps_str = ", ".join(f"{d} ({mapa[d].get('nombre','')})" for d in deps_directos) if deps_directos else "Ninguna"

        # Impacto en cascada
        cascada = _cadena_impacto(clave, mapa)
        cascada_pendiente = [c for c in cascada if c not in aprobadas_set]

        # Periodo ideal
        if ciclo_materia and sem_actual:
            if ciclo_materia == sem_actual:
                periodo_ideal = f"Ciclo {ciclo_materia} — es de su semestre actual, conviene cargarla ya"
            elif ciclo_materia < sem_actual:
                atraso = sem_actual - ciclo_materia
                periodo_ideal = f"Ciclo {ciclo_materia} — ATRASADA por {atraso} semestre(s), priorizar"
            else:
                adelanto = ciclo_materia - sem_actual
                periodo_ideal = f"Ciclo {ciclo_materia} — falta {adelanto} semestre(s) para el momento ideal"
        else:
            periodo_ideal = f"Ciclo {ciclo_materia}" if ciclo_materia else "No definido"

        linea = (
            f"{clave} — {info.get('nombre')} | Ciclo {ciclo_materia} | "
            f"{info.get('creditos')}cr | {categoria}\n"
            f"  Prerrequisitos: {reqs}\n"
        )

        # Estado de prerrequisitos
        if reqs_lista:
            if not reqs_faltantes:
                linea += f"  ✓ Prerrequisitos CUMPLIDOS: el alumno puede cursarla\n"
            else:
                faltantes_str = ", ".join(
                    f"{r} ({mapa.get(r.upper(), {}).get('nombre','')})"
                    for r in reqs_faltantes
                )
                linea += f"  ✗ Prerrequisitos FALTANTES: {faltantes_str}\n"

        linea += (
            f"  Dependientes directos: {deps_str}\n"
            f"  IMPACTO SI REPRUEBA: {len(cascada_pendiente)} materias bloqueadas en cascada"
        )
        if cascada_pendiente:
            linea += f": {', '.join(cascada_pendiente[:8])}"
            if len(cascada_pendiente) > 8:
                linea += f" (+{len(cascada_pendiente)-8} más)"
        linea += f"\n  Periodo ideal: {periodo_ideal}\n"

        # Contexto segun categoria
        if categoria == "PRE_ESPECIALIDAD":
            # ¿A que linea pertenece?
            clave_u = clave.upper()
            if clave_u.startswith("IT") or clave_u.startswith("IA"):
                linea_preesp = "Innovación en TIC"
            elif clave_u.startswith("NI") or clave_u.startswith("IL"):
                linea_preesp = "Inteligencia Organizacional y de Negocios"
            else:
                linea_preesp = "pre-especialidad"
            alineada = esp_activa and linea_preesp.lower() in esp_activa.lower()
            if esp_activa:
                if alineada:
                    linea += f"  PRE-ESPECIALIDAD — pertenece a la línea {linea_preesp} (alineada con la especialidad del alumno)\n"
                else:
                    linea += f"  PRE-ESPECIALIDAD — pertenece a la línea {linea_preesp} (distinta a '{esp_activa}': puede contar como elección libre)\n"
            else:
                linea += f"  PRE-ESPECIALIDAD — línea {linea_preesp}\n"

        elif categoria == "ELECCION_LIBRE":
            # Contar cuantas EL tiene aprobadas
            el_info = _session_ref.get("eleccion_libre_info")
            if el_info and isinstance(el_info, dict):
                try:
                    total_req = sum(el_info.get(f"ciclo_{c}", {}).get("requeridas", 0) for c in [1, 2, "3_y_4"])
                    total_apr = sum(el_info.get(f"ciclo_{c}", {}).get("aprobadas_count", 0) for c in [1, 2, "3_y_4"])
                    linea += f"  ELECCIÓN LIBRE — progreso global: {total_apr}/{total_req} aprobadas\n"
                except Exception:
                    pass

        elif categoria == "CO_CURRICULAR":
            clave_u = clave.upper()
            if clave_u.startswith("AD"):
                tipo_co = "Actividad Deportiva"
            elif clave_u.startswith("TA") or clave_u.startswith("AC"):
                tipo_co = "Actividad Cultural"
            elif clave_u.startswith("LI"):
                tipo_co = "Idioma — Inglés"
            else:
                tipo_co = "Co-curricular"
            linea += f"  CO-CURRICULAR — {tipo_co}\n"

        # Historial del estudiante
        if df is not None and not df.empty:
            hist = df[df["clave"].str.upper() == clave]
            if not hist.empty:
                intentos = []
                for _, row in hist.iterrows():
                    intentos.append(
                        f"{row.get('estatus')} cal:{row.get('calificacion','')} P:{row.get('periodo','')}"
                    )
                n_reprobadas = sum(1 for i in intentos if "REPROBADA" in i)
                linea += f"  Historial del alumno: {' | '.join(intentos)}"
                if n_reprobadas >= 2:
                    linea += f"\n  ⚠ ALERTA: {n_reprobadas} reprobaciones — próximo intento es ÚLTIMA OPORTUNIDAD"
                elif n_reprobadas == 1:
                    linea += f"\n  Nota: 1 reprobación previa — le quedan 2 intentos"
            else:
                linea += "  Historial del alumno: No cursada aún"

        resultados.append(linea.rstrip())

    return "\n\n".join(resultados)


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL 4: Historial con filtro
# ═══════════════════════════════════════════════════════════════════════════

@tool
def consultar_historial(filtro: str = "") -> str:
    """Lista materias del historial con analisis. Filtros: APROBADA, REPROBADA, EN_CURSO, RECURSANDO, o vacío para resumen general. Incluye mejor/peor periodo, distribucion de calificaciones y desglose por categoria."""
    df = _session_ref.get("historial_df")
    if df is None or df.empty:
        return "Sin historial cargado."

    mapa = _cargar_mapa()

    # Si no hay filtro, mostrar resumen analitico general (no todas las materias)
    if not filtro or not filtro.strip():
        out_lines = [f"HISTORIAL ACADÉMICO — Resumen analítico\n"]

        # Conteos por estatus
        por_estatus = df["estatus"].str.upper().value_counts().to_dict()
        out_lines.append("POR ESTATUS:")
        for est in ["APROBADA", "REPROBADA", "EN_CURSO", "RECURSANDO", "SIN_REGISTRAR"]:
            if est in por_estatus:
                out_lines.append(f"  {est}: {por_estatus[est]}")
        out_lines.append("")

        # Desglose por categoria
        desglose = _tasa_aprobacion_por_categoria(df, mapa)
        if desglose:
            out_lines.append("POR CATEGORÍA (cursadas):")
            for cat, d in desglose.items():
                total = d["aprobadas"] + d["reprobadas"]
                out_lines.append(f"  {cat}: {d['aprobadas']} aprobadas de {total} ({d['tasa']}%)")
            out_lines.append("")

        # Mejor / peor periodo
        mp = _mejor_peor_periodo(df)
        if mp:
            out_lines.append("PERIODOS DESTACADOS:")
            out_lines.append(f"  Mejor: {mp['mejor']['periodo']} (promedio {mp['mejor']['promedio']})")
            out_lines.append(f"  Peor: {mp['peor']['periodo']} (promedio {mp['peor']['promedio']})")
            out_lines.append("")

        # Distribucion de calificaciones
        dist = _distribucion_calificaciones(df)
        if dist:
            out_lines.append("DISTRIBUCIÓN DE CALIFICACIONES (aprobadas):")
            total_calif = sum(dist.values())
            for calif in [10, 9, 8, 7]:
                n = dist.get(calif, 0)
                pct = round(n / total_calif * 100, 1) if total_calif > 0 else 0
                out_lines.append(f"  {calif}: {n} materias ({pct}%)")
            out_lines.append("")

        # Materias recursando (cursadas mas de 1 vez)
        try:
            conteo_claves = df.groupby("clave").size()
            multiples = conteo_claves[conteo_claves >= 2]
            if not multiples.empty:
                out_lines.append(f"MATERIAS CURSADAS 2+ VECES ({len(multiples)}):")
                for clave, veces in multiples.items():
                    nombre = df[df["clave"] == clave]["nombre"].iloc[0] if len(df[df["clave"] == clave]) > 0 else clave
                    out_lines.append(f"  {clave} {nombre}: {veces} veces")
                out_lines.append("")
        except Exception:
            pass

        out_lines.append('Para ver el listado completo filtrado, usa filtro="APROBADA", "REPROBADA", "EN_CURSO" o "RECURSANDO".')
        return "\n".join(out_lines)

    # Con filtro: mostrar listado completo + analisis
    f_upper = filtro.upper().strip()
    if f_upper == "REPROBADA":
        # Usar historial_calculo (último estado por materia) para no contar materias
        # que el alumno reprobó pero luego aprobó
        _hc = _session_ref.get("historial_calculo")
        df_canon = _hc if (_hc is not None and hasattr(_hc, "empty") and not _hc.empty) else df
        df_f = df_canon[df_canon["estatus"].str.upper() == "REPROBADA"]
    elif f_upper == "RECURSANDO":
        df_f = df[df["estatus"].str.upper().isin(["EN_CURSO", "RECURSANDO"])]
    else:
        df_f = df[df["estatus"].str.upper() == f_upper]

    if df_f.empty:
        return f"Sin materias con estatus '{filtro}'."

    lineas = []
    for _, row in df_f.iterrows():
        cat = mapa.get(str(row.get("clave", "")).upper(), {}).get("categoria", "?")
        lineas.append(
            f"- {row.get('clave','?')} {row.get('nombre','?')} | C{row.get('ciclo','?')} | "
            f"{cat} | cal:{row.get('calificacion','')} | P:{row.get('periodo','')}"
        )

    # Análisis adicional según filtro
    extra = ""
    if f_upper == "REPROBADA":
        # Contar intentos históricos desde el raw df para detectar riesgo real
        terceras = []
        for clave in df_f["clave"].unique():
            veces = int(((df["clave"] == clave) & (df["estatus"].str.upper() == "REPROBADA")).sum())
            if veces >= 2:
                nombre = df_f[df_f["clave"] == clave]["nombre"].iloc[0] if len(df_f[df_f["clave"] == clave]) > 0 else clave
                terceras.append((clave, nombre, veces))
        if terceras:
            extra = "\n\nEN RIESGO (2+ reprobaciones):\n"
            for clave, nombre, veces in terceras:
                extra += f"  ⚠ {clave} {nombre}: {veces} reprobaciones\n"
        # Categoria mas afectada
        cats = df_f["clave"].str.upper().map(lambda c: mapa.get(c, {}).get("categoria", "?"))
        conteo_cat = cats.value_counts()
        if not conteo_cat.empty:
            extra += f"\nCategoría más afectada: {conteo_cat.index[0]} ({conteo_cat.iloc[0]} reprobaciones)"

    elif f_upper == "APROBADA":
        # Creditos aprobados
        if "creditos" in df_f.columns:
            total_cred = df_f["creditos"].fillna(0).sum()
            extra = f"\n\nCréditos aprobados: {int(total_cred)}"

    out = f"Total: {len(df_f)} materias con estatus '{filtro.upper()}'\n\n" + "\n".join(lineas)
    return out + extra


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL 5: Candidatas del sistema experto
# ═══════════════════════════════════════════════════════════════════════════

@tool
def consultar_candidatas() -> str:
    """Materias recomendadas para el siguiente semestre con prioridad y razón. Para preguntas como '¿qué debería cargar?', '¿qué le toca el próximo semestre?'."""
    resultado = _session_ref.get("resultado_experto")
    if not resultado:
        return "Sistema experto no ejecutado. Cargar documentos primero."

    candidatas = resultado.get("candidatas_detalles", [])
    sem_c = resultado.get("semestre_cursado", "?")
    sem_o = resultado.get("semestre_objetivo", "?")

    lineas = [f"Semestre cursado: {sem_c} | Objetivo: {sem_o} | Candidatas: {len(candidatas)}\n"]

    # Agrupar por prioridad
    por_prioridad = {}
    for c in candidatas:
        p = c.get("prioridad", 5)
        por_prioridad.setdefault(p, []).append(c)

    for p in sorted(por_prioridad.keys()):
        etiqueta = {1: "URGENTE", 2: "IMPORTANTE", 3: "RECOMENDADA", 4: "OPCIONAL", 5: "BAJA"}.get(p, "?")
        lineas.append(f"Prioridad {p} ({etiqueta}):")
        for c in por_prioridad[p]:
            lineas.append(f"  - {c.get('clave')} {c.get('nombre')} C{c.get('ciclo')} {c.get('creditos')}cr | {c.get('razon','')}")

    return "\n".join(lineas)


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL: Priorizar materias (orden estrategico para el asesor)
# ═══════════════════════════════════════════════════════════════════════════

@tool
def priorizar_materias() -> str:
    """Devuelve el ORDEN ESTRATEGICO de materias que el estudiante debe priorizar, agrupadas por nivel de urgencia con justificacion. Responde preguntas como 'que debe priorizar?', 'que materias debe cargar primero?', 'por donde empezar?', 'que es lo mas urgente?'. Incluye creditos por grupo y recomendacion accionable."""
    resultado = _session_ref.get("resultado_experto")
    if not resultado:
        return "Sistema experto no ejecutado. Cargar documentos primero."

    candidatas = resultado.get("candidatas_detalles", [])
    if not candidatas:
        return "Sin materias candidatas. El estudiante puede haber completado el plan."

    sem_c = resultado.get("semestre_cursado", "?")
    sem_o = resultado.get("semestre_objetivo", "?")

    # Agrupar por nivel de prioridad (el sistema experto ya los categoriza)
    por_nivel = {}
    for c in candidatas:
        p = c.get("prioridad", 5)
        nivel = c.get("nivel", "Otro")
        key = (p, nivel)
        por_nivel.setdefault(key, []).append(c)

    # Etiquetas accionables por prioridad
    _urgencia = {
        1: ("CRITICO", "Resolver YA. Sin esto se bloquean materias que ya curso."),
        2: ("URGENTE", "Recursar antes de que llegue a tercera oportunidad."),
        3: ("ALTA", "Cerrar ciclos atrasados para no seguir acumulando rezago."),
        4: ("NORMAL", "Progresion natural del plan."),
        5: ("OPCIONAL", "Tomar si hay espacio despues de lo anterior."),
        6: ("BAJA", "No bloquea egreso inmediato, pero debe completarse."),
    }

    out = [
        f"ORDEN DE PRIORIZACION ESTRATEGICA (semestre cursado {sem_c} -> objetivo {sem_o})",
        "=" * 72,
    ]

    # Recomendacion global
    datos = _session_ref.get("datos_estudiante")
    if datos and "CONDICIONAL" in str(datos.situacion).upper():
        out.append("Limite de carga del alumno: exactamente 3 materias por semestre (condicionado, ni mas ni menos)")
    else:
        out.append("Limite de carga del alumno: maximo 9 materias por semestre")
    out.append("")

    # Recorrer en orden de prioridad
    orden_prioridad = sorted(por_nivel.keys(), key=lambda k: k[0])

    for (prioridad, nivel) in orden_prioridad:
        mats = por_nivel[(prioridad, nivel)]
        urgencia, tip = _urgencia.get(prioridad, ("?", ""))
        total_cr = sum(m.get("creditos", 0) for m in mats)

        out.append(f"[{urgencia}] Prioridad {prioridad} — {nivel}  ({len(mats)} materia(s), {total_cr} creditos)")
        out.append(f"  Accion: {tip}")
        for m in mats:
            razon = m.get("razon", "")
            razon_short = razon[:70] + "..." if len(razon) > 70 else razon
            out.append(
                f"    - {m.get('clave')} {m.get('nombre')} (C{m.get('ciclo')}, {m.get('creditos')}cr)"
                + (f" | {razon_short}" if razon_short else "")
            )
        out.append("")

    # Recomendacion sintetica al final
    out.append("RECOMENDACION:")

    criticas = por_nivel.get((1, "Prerequisito faltante retroactivo"), [])
    urgentes = por_nivel.get((2, "Materias reprobadas"), [])
    atrasadas = []
    for k, v in por_nivel.items():
        if k[0] == 3:
            atrasadas.extend(v)
    ciclo_actual = []
    for k, v in por_nivel.items():
        if k[0] == 4:
            ciclo_actual.extend(v)

    if criticas:
        out.append(f"  1. Cargar las {len(criticas)} materia(s) con PREREQUISITO RETROACTIVO (sin esto quedan materias 'fantasma' aprobadas sin su requisito).")
    if urgentes:
        out.append(f"  {'2' if criticas else '1'}. Recursar las {len(urgentes)} REPROBADAS pendientes (antes de que lleguen a tercera oportunidad).")
    if atrasadas:
        idx = 1 + (1 if criticas else 0) + (1 if urgentes else 0)
        out.append(f"  {idx}. Cerrar {len(atrasadas)} materia(s) ATRASADAS de ciclos anteriores (empezando por la mas antigua).")
    if ciclo_actual and max_materias > len(criticas) + len(urgentes) + len(atrasadas):
        restante = max_materias - len(criticas) - len(urgentes) - len(atrasadas)
        out.append(f"  Completar carga con hasta {restante} materia(s) del CICLO ACTUAL (progresion natural).")

    out.append("")
    out.append(f"NOTA: No exceder {max_materias} materias por semestre. Priorizar los grupos superiores antes que electivas.")

    return "\n".join(out)


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL 6: Comparar carga real vs recomendada
# ═══════════════════════════════════════════════════════════════════════════

@tool
def comparar_carga() -> str:
    """Compara materias EN_CURSO vs recomendadas. Para '¿está cargando bien?', '¿lleva materias que no debería?', '¿le falta cargar algo importante?'."""
    df = _session_ref.get("historial_df")
    resultado = _session_ref.get("resultado_experto")
    if df is None or df.empty:
        return "Sin historial."
    if not resultado:
        return "Sistema experto no ejecutado."

    mapa = _cargar_mapa()
    en_curso_df = df[df["estatus"].str.upper().isin(["EN_CURSO", "RECURSANDO"])]
    en_curso = set(en_curso_df["clave"].str.upper())
    candidatas_det = resultado.get("candidatas_detalles", [])
    candidatas = {c["clave"].upper() for c in candidatas_det}
    candidatas_p1 = {c["clave"].upper() for c in candidatas_det if c.get("prioridad") in (1, 2)}

    coinciden = en_curso & candidatas
    solo_curso = en_curso - candidatas
    solo_rec = candidatas - en_curso
    urgentes_no_cursando = candidatas_p1 - en_curso

    # ¿Está cargando materias de semestres adelantados?
    sem_actual = resultado.get("semestre_objetivo", 99)
    adelantadas = []
    for clave in en_curso:
        info = mapa.get(clave, {})
        if info.get("ciclo", 0) > sem_actual:
            adelantadas.append(f"{clave} ({info.get('nombre','')}, ciclo {info.get('ciclo')})")

    lineas = [
        f"En curso: {len(en_curso)} | Recomendadas: {len(candidatas)} | Coinciden: {len(coinciden)}",
    ]
    if coinciden:
        lineas.append(f"✅ Bien elegidas: {', '.join(sorted(coinciden))}")
    if solo_curso:
        lineas.append(f"⚠ Cursando pero NO recomendadas: {', '.join(sorted(solo_curso))}")
    if urgentes_no_cursando:
        lineas.append(f"🔴 URGENTES que NO está cursando (P1/P2): {', '.join(sorted(urgentes_no_cursando))}")
    if adelantadas:
        lineas.append(f"⚠ Materias ADELANTADAS (ciclo mayor al objetivo): {', '.join(adelantadas)}")
    if not solo_curso and not urgentes_no_cursando and not adelantadas:
        lineas.append("✅ La carga actual es consistente con las recomendaciones.")

    return "\n".join(lineas)


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL 7: Cargas generadas
# ═══════════════════════════════════════════════════════════════════════════

@tool
def consultar_cargas() -> str:
    """Horarios/cargas generados por el optimizador. Para '¿qué horarios hay?', '¿dónde veo las opciones de carga?'."""
    cargas = _session_ref.get("cargas_generadas")
    if not cargas:
        return "Sin cargas generadas. El asesor debe ir a '📅 Generador de Cargas' para generarlas."

    lineas = [f"{len(cargas)} opciones:"]
    for i, carga in enumerate(cargas, 1):
        materias = carga.get("materias", [])
        total_cred = sum(m.get("creditos", 0) for m in materias)
        nombres = ", ".join(f"{m.get('clave','?')} ({m.get('nombre','')})" for m in materias)
        lineas.append(f"  Opción {i}: {len(materias)} materias, {total_cred}cr\n    {nombres}")
    return "\n".join(lineas)


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL 8: Elección Libre — progreso por ciclo
# ═══════════════════════════════════════════════════════════════════════════

@tool
def consultar_eleccion_libre() -> str:
    """Progreso del alumno en materias de Elección Libre por ciclo. Para preguntas como '¿cuántas elecciones libres le faltan?', '¿cuántas EL lleva en ciclo X?', '¿cómo va con las EL?'."""
    el_info = _session_ref.get("eleccion_libre_info")
    if not el_info:
        return "Datos de elección libre no disponibles. Cargar documentos primero."

    ciclos = el_info.get("ciclos", {})
    pre_tit = el_info.get("pre_titulacion", "No detectada")
    pre_count = el_info.get("pre_count", {})

    lineas = [f"Pre-especialidad de titulación: {pre_tit}\n"]
    labels = {1: "Ciclo 1", 2: "Ciclo 2", "3_y_4": "Ciclos 3 y 4"}
    requeridos = {1: 2, 2: 2, "3_y_4": 8}

    total_aprobadas = 0
    total_requeridas = 0

    for key, label in labels.items():
        d = ciclos.get(key, {})
        aprobadas = d.get("aprobadas", 0)
        en_curso = d.get("en_curso", 0)
        requeridas = requeridos.get(key, 0)
        faltan = max(0, requeridas - aprobadas)
        total_aprobadas += aprobadas
        total_requeridas += requeridas
        claves = d.get("claves", [])
        nombres = d.get("nombres", [])
        mat_str = ", ".join(f"{c} ({n})" for c, n in zip(claves, nombres)) if claves else "Ninguna"
        lineas.append(
            f"{label}: {aprobadas}/{requeridas} aprobadas | {en_curso} en curso | faltan {faltan}\n"
            f"  Materias: {mat_str}"
        )

    lineas.append(f"\nTOTAL EL: {total_aprobadas}/{total_requeridas} aprobadas | faltan {max(0, total_requeridas - total_aprobadas)}")

    # Progreso preesp de la no usada (pueden contar como EL)
    pre_no_usada = [k for k in pre_count.keys() if k != pre_tit]
    for p in pre_no_usada:
        cnt = pre_count.get(p, 0)
        if cnt > 0:
            lineas.append(f"  Nota: tiene {cnt} materia(s) de {p} (pre-esp no usada) que pueden contar como EL en ciclos 3-4.")

    return "\n".join(lineas)


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL 9: Pre-especialidades — progreso por línea
# ═══════════════════════════════════════════════════════════════════════════

@tool
def consultar_preespecialidades() -> str:
    """Progreso del alumno en cada pre-especialidad (TICS, Business Intelligence). Para '¿cómo va en pre-especialidad?', '¿cuántas materias de TICS tiene?', '¿cuál es su especialidad?'."""
    mapa = _cargar_mapa()
    df = _session_ref.get("historial_df")

    # Construir lookup estatus + nombre más reciente por clave
    estatus_clave: dict = {}
    if df is not None and not df.empty:
        for _, row in df.iterrows():
            clave = str(row.get("clave", "")).upper()
            est = str(row.get("estatus", "")).upper()
            per = str(row.get("periodo", ""))
            nom = str(row.get("nombre", ""))
            prev = estatus_clave.get(clave)
            if prev is None or per >= prev["periodo"]:
                estatus_clave[clave] = {"estatus": est, "periodo": per, "nombre": nom}

    # Determinar especialidad activa (forzada > detectada)
    resultado = _session_ref.get("resultado_experto")
    esp_forzada = str(_session_ref.get("especialidad_forzada") or "")
    esp_detectada_raw = (resultado.get("especialidad_detectada", "") or "") if resultado else ""
    esp_activa = (esp_forzada or esp_detectada_raw).upper().strip()

    _ESP_A_TRACK = {
        "BUSINESS_INTELLIGENCE": "Inteligencia Organizacional y de Negocios",
        "ION": "Inteligencia Organizacional y de Negocios",
        "TICS": "Innovación en TIC",
        "ITIC": "Innovación en TIC",
    }
    track_principal = _ESP_A_TRACK.get(esp_activa)
    esp_label = esp_activa.replace("_", " ").title() if esp_activa else "No detectada"

    # Construir mapa completo de tracks desde el JSON (siempre ambas líneas)
    preesp_mapa: dict[str, list] = {}
    for c, info in mapa.items():
        cat = info.get("categoria", "").upper()
        if "PREESP" not in cat and "PRE_ESP" not in cat and "PRE-ESP" not in cat:
            continue
        nombre_m = info.get("nombre", "")
        if "inteligencia" in nombre_m.lower() and ("negocios" in nombre_m.lower() or "organizacional" in nombre_m.lower()):
            track = "Inteligencia Organizacional y de Negocios"
        elif "innovaci" in nombre_m.lower() and "tic" in nombre_m.lower():
            track = "Innovación en TIC"
        elif c in ["ID3420", "ID3421", "ID3422", "ID3423", "ID3424"]:
            track = "Inteligencia Organizacional y de Negocios"
        elif c in ["ID3416", "ID3417", "ID3418", "ID3419", "ID3469"]:
            track = "Innovación en TIC"
        else:
            continue
        preesp_mapa.setdefault(track, []).append(c)

    if not preesp_mapa:
        return "No se encontraron materias de pre-especialidad en el mapa curricular."

    # Track principal primero
    tracks_ordenados = sorted(preesp_mapa.keys(), key=lambda t: (0 if t == track_principal else 1))

    partes = []
    if track_principal:
        partes.append(f"**Especialidad activa: {esp_label}**")
    else:
        partes.append("**Especialidad activa:** No detectada (el sistema no ha identificado una línea principal)")
    partes.append("")

    for track in tracks_ordenados:
        todas_claves = preesp_mapa[track]

        aprobadas_lista = []
        reprobadas_lista = []
        faltan_lista = []

        for c in todas_claves:
            info_hist = estatus_clave.get(c, {})
            est = info_hist.get("estatus", "")
            nombre_mat = info_hist.get("nombre") or mapa.get(c, {}).get("nombre", c)
            entrada = f"{c} — {nombre_mat}"
            if est == "APROBADA":
                aprobadas_lista.append(entrada)
            elif est == "REPROBADA":
                reprobadas_lista.append(entrada)
            else:
                faltan_lista.append(entrada)

        aprobadas_n = len(aprobadas_lista)
        faltan_n = max(0, 5 - aprobadas_n)

        if aprobadas_n >= 5:
            estado_emoji, estado = "✅", "COMPLETADA"
        elif aprobadas_n >= 3:
            estado_emoji, estado = "🟡", "EN PROGRESO"
        elif aprobadas_n >= 1:
            estado_emoji, estado = "🟠", "INICIADA"
        else:
            estado_emoji, estado = "⚪", "PENDIENTE"

        barra = "█" * aprobadas_n + "░" * (5 - aprobadas_n)

        es_principal = (track == track_principal)
        if es_principal:
            partes.append(f"### ⭐ {track} — TU LÍNEA PRINCIPAL")
        else:
            partes.append(f"### {track}")
            partes.append("*(Línea alternativa: si apruebas sus materias cuentan como Elección Libre)*")

        partes.append(f"{estado_emoji} **{aprobadas_n}/5 aprobadas** `{barra}` — {estado}  |  Faltan: {faltan_n}")
        partes.append("")

        if aprobadas_lista:
            partes.append("**Aprobadas:**")
            for item in aprobadas_lista:
                partes.append(f"- ✅ {item}")
        else:
            partes.append("**Aprobadas:** ninguna todavía")

        if reprobadas_lista:
            partes.append("")
            partes.append("**Reprobadas (pendientes de recursar):**")
            for item in reprobadas_lista:
                partes.append(f"- ❌ {item}")

        if faltan_lista:
            partes.append("")
            partes.append("**Pendientes (no cursadas):**")
            for item in faltan_lista:
                partes.append(f"- ○ {item}")

        partes.append("")
        partes.append("---")
        partes.append("")

    return "\n".join(partes)


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL 10: Consultar historial por periodo
# ═══════════════════════════════════════════════════════════════════════════

@tool
def consultar_por_periodo(periodo: str) -> str:
    """Lista las materias cursadas en un periodo académico específico (ej. '2023-1', '2024-2'). Para '¿qué cargó en 2023-1?', '¿qué llevó el semestre pasado?'."""
    df = _session_ref.get("historial_df")
    if df is None or df.empty:
        return "Sin historial cargado."

    # Búsqueda flexible: coincidencia parcial del periodo
    mask = df["periodo"].astype(str).str.contains(periodo.strip(), case=False, na=False)
    df_p = df[mask]

    if df_p.empty:
        periodos_disponibles = sorted(df["periodo"].dropna().astype(str).unique().tolist())
        return f"Periodo '{periodo}' no encontrado. Periodos disponibles: {', '.join(periodos_disponibles)}"

    lineas = [f"Periodo '{periodo}': {len(df_p)} materias\n"]
    cred_total = 0
    for _, row in df_p.iterrows():
        cal = row.get("calificacion", "")
        cred = row.get("creditos", 0)
        try:
            cred_total += int(float(cred)) if str(cred) not in ("", "nan") else 0
        except Exception:
            pass
        cal_str = f" | Cal: {cal}" if str(cal) not in ("", "nan", "None") else ""
        lineas.append(
            f"  - {row.get('clave','?')} {row.get('nombre','?')} | {row.get('estatus','?')}{cal_str} | {cred}cr"
        )
    lineas.append(f"\nTotal créditos del periodo: {cred_total}")
    return "\n".join(lineas)


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL 11: Co-curriculares (deportiva, cultural, idiomas)
# ═══════════════════════════════════════════════════════════════════════════

@tool
def consultar_cocurriculares() -> str:
    """Materias co-curriculares del alumno: actividades deportivas, culturales e idiomas. Para '¿qué deportivas tiene?', '¿tiene actividad cultural?', '¿cuáles son sus co-curriculares?'."""
    df = _session_ref.get("historial_df")
    if df is None or df.empty:
        return "Sin historial cargado."

    # Lógica idéntica a processor.calcular_requisitos:
    # AD#### = deportiva | TA#### / AC#### = cultural
    # SIN_REGISTRAR también cuenta como cumplido (equivalencias/convalidaciones)
    ESTATUS_VALIDOS = {"APROBADA", "SIN_REGISTRAR"}

    tiene_deportiva = False
    tiene_cultural = False
    deportivas = []
    culturales = []
    otros_cocurr = []

    for _, row in df.iterrows():
        clave = str(row.get("clave", "")).upper().strip()
        estatus = str(row.get("estatus", "")).upper().strip()
        cal = row.get("calificacion", "")
        per = row.get("periodo", "")
        nombre = str(row.get("nombre", ""))
        cal_str = f" | Cal: {cal}" if str(cal) not in ("", "nan", "None") else ""
        entry = f"  {clave} {nombre}{cal_str} | {estatus} | P:{per}"

        if clave.startswith("AD"):
            deportivas.append(entry)
            if estatus in ESTATUS_VALIDOS:
                tiene_deportiva = True
        elif clave.startswith("TA") or clave.startswith("AC"):
            culturales.append(entry)
            if estatus in ESTATUS_VALIDOS:
                tiene_cultural = True
        elif clave.startswith("LI"):  # inglés
            otros_cocurr.append(entry)

    # Inglés: usar el flag ya calculado por el parser (más preciso que revisar claves)
    ingles_ok = _session_ref.get("ingles_completo", False)
    nivel_ing = _session_ref.get("nivel_ingles_texto", "No disponible")

    lineas = ["CO-CURRICULARES Y REQUISITOS DE EGRESO\n"]

    lineas.append(f"Actividad Deportiva: {'✅ CUMPLIDA' if tiene_deportiva else '❌ PENDIENTE'}")
    if deportivas:
        lineas += deportivas
    else:
        lineas.append("  (ningún registro con prefijo AD)")

    lineas.append(f"\nActividad Cultural: {'✅ CUMPLIDA' if tiene_cultural else '❌ PENDIENTE'}")
    if culturales:
        lineas += culturales
    else:
        lineas.append("  (ningún registro con prefijo TA o AC)")

    lineas.append(f"\nInglés: {'✅ COMPLETO' if ingles_ok else '❌ PENDIENTE'} — {nivel_ing}")
    if otros_cocurr:
        lineas += otros_cocurr

    return "\n".join(lineas)


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL 12: Créditos por categoría
# ═══════════════════════════════════════════════════════════════════════════

@tool
def consultar_creditos_categoria() -> str:
    """Desglose de créditos acumulados por categoría: BASICA, ELECCION_LIBRE, PRE_ESPECIALIDAD, CO_CURRICULAR. Para '¿cuántos créditos de básicas lleva?', '¿créditos por categoría?', '¿qué le falta para egresar?'."""
    df = _session_ref.get("historial_df")
    if df is None or df.empty:
        return "Sin historial cargado."

    mapa = _cargar_mapa()
    aprobadas = df[df["estatus"].str.upper() == "APROBADA"]

    creditos_cat: dict = {}
    requeridos_cat: dict = {}

    for k, v in mapa.items():
        cat = v.get("categoria", "OTRA")
        requeridos_cat[cat] = requeridos_cat.get(cat, 0) + v.get("creditos", 0)

    for _, row in aprobadas.iterrows():
        clave = str(row.get("clave", "")).upper()
        info = mapa.get(clave, {})
        cat = info.get("categoria", "OTRA")
        cred = info.get("creditos", 0) or row.get("creditos", 0)
        try:
            cred = int(float(cred))
        except Exception:
            cred = 0
        creditos_cat[cat] = creditos_cat.get(cat, 0) + cred

    cred_total = _session_ref.get("creditos_totales", 404)
    cred_acum = sum(creditos_cat.values())

    _NOMBRE_CAT = {
        "BASICA": "Materias Básicas",
        "ELECCION_LIBRE": "Elección Libre",
        "PRE_ESPECIALIDAD": "Pre-especialidad",
        "CO_CURRICULAR": "Co-curriculares (Inglés)",
        "OTRA": "Otras materias",
    }

    def _barra(acum, req, ancho=12):
        if not isinstance(req, int) or req == 0:
            return "░" * ancho
        llenos = round(acum / req * ancho)
        llenos = max(0, min(llenos, ancho))
        return "█" * llenos + "░" * (ancho - llenos)

    partes = []
    partes.append("### Progreso hacia la graduación")

    barra_global = _barra(cred_acum, cred_total, ancho=20)
    try:
        pct_global = round(cred_acum / cred_total * 100, 1)
    except Exception:
        pct_global = "?"
    partes.append(f"**{cred_acum} / {cred_total} créditos acumulados**")
    partes.append(f"`{barra_global}` {pct_global}%")
    faltan_global = cred_total - cred_acum
    if faltan_global > 0:
        partes.append(f"Faltan **{faltan_global} créditos** para completar la carrera.")
    else:
        partes.append("¡Ya cubriste todos los créditos requeridos!")
    partes.append("")
    partes.append("---")
    partes.append("")
    partes.append("**Desglose por categoría:**")
    partes.append("")

    orden_cat = ["BASICA", "PRE_ESPECIALIDAD", "ELECCION_LIBRE", "CO_CURRICULAR", "OTRA"]
    todas_cats = sorted(set(list(creditos_cat.keys()) + list(requeridos_cat.keys())))
    cats_ordenadas = [c for c in orden_cat if c in todas_cats] + [c for c in todas_cats if c not in orden_cat]

    for cat in cats_ordenadas:
        acum = creditos_cat.get(cat, 0)
        req = requeridos_cat.get(cat, "?")
        # Omitir categorías irrelevantes: sin requerimiento definido o sin créditos
        if not isinstance(req, int) or req == 0:
            continue
        nombre = _NOMBRE_CAT.get(cat, cat)
        barra = _barra(acum, req)
        pct = round(acum / req * 100, 1)
        faltan = req - acum
        if acum >= req:
            emoji = "✅"
            estado = "Completada"
        elif acum > 0:
            emoji = "🟡"
            estado = "En progreso"
        else:
            emoji = "⚪"
            estado = "Pendiente"
        partes.append(f"**{nombre}** {emoji} {estado}")
        partes.append(f"`{barra}` {acum}/{req} cr ({pct}%) — faltan {faltan}")
        partes.append("")

    return "\n".join(partes)


# ═══════════════════════════════════════════════════════════════════════════
#  TOOL: Buscar por calificación numérica
# ═══════════════════════════════════════════════════════════════════════════

@tool
def buscar_por_calificacion(calificacion: str) -> str:
    """Busca materias del historial donde la calificación coincide con un valor. Útil para '¿hubo alguna materia donde sacó 7?', '¿qué materias tiene con 8?', '¿tiene algún 6?'."""
    df = _session_ref.get("historial_df")
    if df is None or df.empty:
        return "Sin historial cargado."

    cal_buscar = calificacion.strip()
    # Normalizar: comparar como float si es número
    try:
        cal_float = float(cal_buscar)
        def _coincide(val):
            try:
                return float(val) == cal_float
            except Exception:
                return str(val).strip() == cal_buscar
    except ValueError:
        def _coincide(val):
            return str(val).strip().upper() == cal_buscar.upper()

    coincidentes = df[df["calificacion"].apply(lambda v: _coincide(v) if str(v) not in ("", "nan", "None") else False)]

    if coincidentes.empty:
        return f"No hay materias con calificación {cal_buscar} en el historial."

    lineas = [f"**Materias con calificación {cal_buscar}** ({len(coincidentes)} encontradas):\n"]
    for _, row in coincidentes.iterrows():
        lineas.append(
            f"- {row.get('clave','?')} — {row.get('nombre','?')} | "
            f"{row.get('estatus','?')} | Ciclo {row.get('ciclo','?')} | Periodo: {row.get('periodo','')}"
        )
    return "\n".join(lineas)


# ═══════════════════════════════════════════════════════════════════════════
#  Agente
# ═══════════════════════════════════════════════════════════════════════════

ALL_TOOLS = [
    resumen_estudiante,
    diagnostico_academico,
    buscar_materia,
    consultar_historial,
    consultar_candidatas,
    priorizar_materias,
    comparar_carga,
    consultar_cargas,
    consultar_eleccion_libre,
    consultar_preespecialidades,
    consultar_por_periodo,
    consultar_cocurriculares,
    consultar_creditos_categoria,
    buscar_por_calificacion,
]


def crear_agente(api_key: str = "", modelo: str = ""):
    key = api_key or settings.CEREBRAS_API_KEY
    if not key:
        return None

    llm = ChatOpenAI(
        model=modelo or "gpt-oss-120b",
        openai_api_key=key,
        openai_api_base="https://api.cerebras.ai/v1",
        temperature=0.1,
        max_tokens=1024,
    )

    return create_react_agent(model=llm, tools=ALL_TOOLS, prompt=SYSTEM_PROMPT)


def _trim_history(messages: List, max_chars: int = 12000) -> List:
    if not messages:
        return messages
    total = sum(len(getattr(m, "content", "")) for m in messages)
    if total <= max_chars:
        return messages
    trimmed = []
    chars = 0
    for msg in reversed(messages):
        c = len(getattr(msg, "content", ""))
        if chars + c > max_chars:
            break
        trimmed.insert(0, msg)
        chars += c
    return trimmed


def _limpiar_latex(texto: str) -> str:
    """Convierte notacion LaTeX a texto plano para que Streamlit lo renderice bien."""
    import re

    # \frac{a}{b} -> "a / b"
    texto = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"\1 / \2", texto)
    # \text{X} -> "X"
    texto = re.sub(r"\\text\{([^{}]+)\}", r"\1", texto)
    # \approx -> "aprox"
    texto = texto.replace(r"\approx", "aprox").replace(r"\;", " ").replace(r"\ ", " ").replace(r"\,", " ")
    # \sim -> "~"
    texto = texto.replace(r"\sim", "~")
    # \times -> "x"
    texto = texto.replace(r"\times", "x")
    # \cdot -> "·"
    texto = texto.replace(r"\cdot", "·")
    # Bloques [...math...]  o  \[...\]  -> quitar los delimitadores
    texto = re.sub(r"\\\[(.*?)\\\]", r"\1", texto, flags=re.DOTALL)
    texto = re.sub(r"\$\$(.*?)\$\$", r"\1", texto, flags=re.DOTALL)
    texto = re.sub(r"\$([^$\n]+?)\$", r"\1", texto)
    # Lineas que solo son "[" o "]" (delimitadores de bloque math) -> borrarlas
    texto = re.sub(r"^\s*\[\s*$", "", texto, flags=re.MULTILINE)
    texto = re.sub(r"^\s*\]\s*$", "", texto, flags=re.MULTILINE)
    # Residuos de backslash + letra al inicio de palabra (comandos no mapeados) -> quitarles el backslash
    texto = re.sub(r"\\([a-zA-Z]+)", r"\1", texto)
    # Multiples saltos de linea consecutivos -> maximo 2
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto


def _extraer_texto(content) -> str:
    """Extrae solo el texto de un content de AIMessage.

    Gemini 2.5 puede retornar content como:
    - str: texto plano
    - list[dict]: bloques con 'type','text','extras' (la firma digital va en extras)
    """
    if isinstance(content, str):
        texto = content
    elif isinstance(content, list):
        partes = []
        for bloque in content:
            if isinstance(bloque, dict) and bloque.get("type") == "text":
                partes.append(bloque.get("text", ""))
            elif isinstance(bloque, str):
                partes.append(bloque)
        texto = "".join(partes)
    else:
        texto = str(content)

    # Limpiar newlines literales escapados y normalizar saltos de linea para markdown
    texto = texto.replace("\\n", "\n")
    # Limpiar notacion LaTeX (red de seguridad)
    texto = _limpiar_latex(texto)
    # Markdown necesita doble newline o dos espacios + newline para salto visual
    lineas = texto.split("\n")
    return "  \n".join(lineas)


# ═══════════════════════════════════════════════════════════════════════════
#  RESPUESTAS LOCALES — sin LLM, sin costo, sin latencia
#  Si no matchea, cae al LLM que tambien tiene las reglas en el prompt.
# ═══════════════════════════════════════════════════════════════════════════

# Sinonimos: el usuario puede decir cualquiera y matchea igual
_SINONIMOS = {
    "reprobar": ["reprobar", "reprueba", "repruebe", "reprobara", "tronar", "trone", "tronara",
                  "tronado", "trono", "ha tronado", "ha tronar", "tronó",
                  "perder", "pierde", "pierda", "perdiera",
                  "no pasar", "no pase", "no aprobar", "no aprueba", "no apruebe",
                  "jalar", "jale", "jalara"],
    "materia": ["materia", "clase", "asignatura", "curso"],
    "materias": ["materias", "clases", "asignaturas", "cursos"],
    "cargar": ["cargar", "inscribir", "meter", "llevar", "tomar", "registrar", "agarrar"],
    "condicional": ["condicional", "condicionado"],
    "maximo": ["maximo", "max", "limite", "tope", "permitido"],
    "veces": ["veces", "oportunidades", "intentos", "chances"],
    "egreso": ["egreso", "egresar", "graduar", "titular", "titulacion", "graduacion", "terminar"],
    "requisitos": ["requisitos", "requisito", "necesito", "necesita", "piden", "pide", "exige", "falta"],
    "especialidad": ["especialidad", "especialidades", "preespecialidad", "pre-especialidad",
                       "especializacion", "linea", "concentracion"],
    "ingles": ["ingles", "english", "idioma", "topicos"],
    "horario": ["horario", "horarios", "schedule", "carga horaria"],
    "donde": ["donde", "en que parte", "encuentro", "como veo", "en que pestana",
               "en que seccion", "como accedo", "como llego", "en donde"],
    "seriacion": ["seriacion", "prerequisito", "prerrequisito", "requisito previo",
                    "cadena", "bloqueo", "bloquea"],
    "deportiva": ["deportiva", "deporte", "deportivo", "actividad fisica"],
    "cultural": ["cultural", "cultura", "actividad artistica"],
    "promedio": ["promedio", "calificacion general", "nota", "average"],
    "credito": ["credito", "creditos"],
    "semestre": ["semestre", "semestres", "ciclo", "ciclos", "periodo"],
    "calificacion": ["calificacion", "calificaciones", "nota", "notas", "como le fue", "que saco", "cuanto saco"],
    "eleccion_libre": ["eleccion libre", "el ciclo", "materias libres", "elecciones libres", "libre"],
    "preespecialidad": ["preespecialidad", "pre especialidad", "pre-especialidad", "especialidad cursada", "linea de especialidad"],
    "cocurricular": ["cocurricular", "co-curricular", "actividad adicional", "actividades adicionales"],
}

_REGLAS_LOCALES = [
    # (palabras_clave, respuesta)
    (["materias", "condicional"],
     "Un alumno CONDICIONAL debe cargar EXACTAMENTE 3 materias por semestre (ni mas ni menos). Un alumno irregular o regular puede cargar hasta 9 materias."),
    (["materias", "maximo", "regular"],
     "Un alumno regular o irregular puede cargar hasta 9 materias por semestre."),
    (["materias", "cargar", "maximo"],
     "Un alumno regular o irregular puede cargar hasta 9 materias por semestre. Un alumno CONDICIONAL debe cargar exactamente 3 materias (ni mas ni menos)."),
    (["veces", "reprobar"],
     "Cada materia se puede cursar hasta 3 veces. Con 2 reprobaciones entra en TERCERA OPORTUNIDAD (ultimo intento). Con 3 reprobaciones es BAJA DEFINITIVA de esa materia."),
    (["oportunidades", "materia"],
     "Cada materia se puede cursar hasta 3 veces (3 oportunidades). 1 reprobacion: quedan 2 intentos. 2 reprobaciones: TERCERA OPORTUNIDAD. 3 reprobaciones: BAJA DEFINITIVA."),
    (["tercera oportunidad"],
     "La tercera oportunidad ocurre cuando un alumno ha reprobado una materia 2 veces. Es su ultimo intento: si reprueba, se le da baja definitiva de esa materia. Multiples materias en tercera oportunidad pueden llevar a baja del programa."),
    (["baja definitiva"],
     "La baja definitiva de una materia ocurre tras 3 reprobaciones. El alumno ya no puede cursarla. Si es una materia obligatoria, esto puede impedir la titulacion."),
    (["requisitos", "egreso"],
     "Requisitos de egreso del plan IDeIO 2021: 1) Aprobar las 86 materias (~404 creditos). 2) Ingles completo hasta Topicos 2 (LI0110). 3) Actividad deportiva completada. 4) Actividad cultural completada. 5) Servicio social y practicas profesionales."),
    (["requisitos", "titular"],
     "Requisitos de egreso del plan IDeIO 2021: 1) Aprobar las 86 materias (~404 creditos). 2) Ingles completo hasta Topicos 2 (LI0110). 3) Actividad deportiva completada. 4) Actividad cultural completada. 5) Servicio social y practicas profesionales."),
    (["requisitos", "egresar"],
     "Requisitos de egreso del plan IDeIO 2021: 1) Aprobar las 86 materias (~404 creditos). 2) Ingles completo hasta Topicos 2 (LI0110). 3) Actividad deportiva completada. 4) Actividad cultural completada. 5) Servicio social y practicas profesionales."),
    (["requisitos", "ingles"],
     "El requisito de ingles consiste en aprobar 6 niveles: LI1101, LI1102, LI0103, LI0104, LI0109, LI0110 (Topicos 2). Debe completarse antes del egreso. Si un alumno va en semestre 6+ sin completarlo, es alerta."),
    (["especialidades"],
     "El plan IDeIO 2021 tiene 3 pre-especialidades: 1) TICS (Tecnologias de Informacion y Comunicacion). 2) Business Intelligence (Inteligencia de Negocios). 3) Ciencia de Datos."),
    (["especialidad", "principal", "dos especialidad"],
     "Si un alumno cargo materias de dos especialidades, la principal se determina por la que tenga MAS materias de pre-especialidad aprobadas. En caso de empate, el asesor puede forzar la seleccion desde el panel lateral del sistema."),
    (["especialidad", "otra", "eleccion libre"],
     "Un alumno puede tomar materias de otra especialidad como eleccion libre si hay cupo disponible."),
    (["prioridad", "p1", "p2", "significan"],
     "Las prioridades del sistema experto son: P1=URGENTE (materia atrasada critica), P2=IMPORTANTE (materia del semestre actual), P3=RECOMENDADA, P4=OPCIONAL, P5=BAJA prioridad. Se recomienda siempre priorizar P1 y P2."),
    (["seriacion"],
     "La seriacion son los prerrequisitos entre materias. Si un alumno no aprueba una materia, se le BLOQUEAN todas las que la requieren como prerrequisito. Las materias con mas dependientes son cuellos de botella y deben priorizarse."),
    (["semestres", "plan", "cuantos"],
     "El plan IDeIO 2021 tiene 8 semestres (4 ciclos anuales), con 86 materias y aproximadamente 404 creditos totales."),
    (["actividad deportiva"],
     "El requisito de actividad deportiva exige completar al menos 1 actividad deportiva durante la carrera. Se puede verificar en Historia Academica > Eleccion Libre y Adicionales."),
    (["actividad cultural"],
     "El requisito de actividad cultural exige completar al menos 1 actividad cultural durante la carrera. Se puede verificar en Historia Academica > Eleccion Libre y Adicionales."),
    (["donde", "promedio"],
     "El promedio general se encuentra en la pestana Historia Academica > Resumen General."),
    (["donde", "credito"],
     "Los creditos acumulados y faltantes se encuentran en Historia Academica > Resumen General."),
    (["donde", "ingles"],
     "El progreso de ingles se encuentra en Historia Academica > Eleccion Libre y Adicionales."),
    (["donde", "candidata"],
     "Las materias candidatas recomendadas estan en la pestana Sistema Experto."),
    (["donde", "horario"],
     "Los horarios generados estan en la pestana Generador de Cargas."),
    (["donde", "oferta"],
     "La oferta academica real y su cruce con candidatas esta en la pestana Oferta y Candidatas."),
    (["donde", "mapa"],
     "El mapa curricular completo esta en la pestana Mapa Curricular."),
    (["donde", "especialidad"],
     "La informacion de pre-especialidad esta en Historia Academica > Pre-Especialidades."),
    (["donde", "deportiva"],
     "La actividad deportiva se encuentra en Historia Academica > Eleccion Libre y Adicionales."),
    (["donde", "cultural"],
     "La actividad cultural se encuentra en Historia Academica > Eleccion Libre y Adicionales."),
]


def _expandir_sinonimos(texto: str) -> str:
    """Reemplaza sinonimos en el texto por su forma canonica para mejorar matching."""
    resultado = texto
    for canonical, variantes in _SINONIMOS.items():
        for variante in variantes:
            v_norm = _norm(variante)
            if v_norm != _norm(canonical) and v_norm in resultado:
                resultado = resultado.replace(v_norm, _norm(canonical))
    return resultado


def _detectar_simulacion(pregunta: str) -> Optional[str]:
    """Detecta preguntas tipo 'que pasa si reprueba X' y ejecuta simulacion local.
    Retorna resultado de simulacion o None si no es una pregunta de simulacion."""
    q = _norm(pregunta)
    q_expanded = _expandir_sinonimos(q)

    # Patrones que indican simulacion
    _sim_signals = [
        "que pasa si reprobar",
        "que pasa si no aprobar",
        "si reprobar",
        "si no aprobar",
        "no aprobar",
        "que se bloquea",
        "impacto de reprobar",
        "consecuencia de reprobar",
        "consecuencias de reprobar",
        "que bloquea reprobar",
        "se bloquea si reprobar",
    ]

    es_simulacion = any(s in q_expanded for s in _sim_signals)
    if not es_simulacion:
        return None

    # Extraer nombres de materias: quitar las palabras de la pregunta y quedarse con el resto
    _stopwords = {
        "que", "pasa", "si", "el", "la", "los", "las", "un", "una", "no", "se",
        "le", "al", "del", "en", "con", "por", "para", "como", "cual", "es",
        "son", "tiene", "puede", "podria", "seria", "fuera", "materia", "materias",
        "reprueba", "reprobar", "reprobara", "tronar", "tronara", "jala", "jalara",
        "aprueba", "aprobar", "aprobara", "pierde", "perder", "perdiera",
        "bloquea", "bloquean", "bloquearia", "impacto", "consecuencia", "consecuencias",
        "pase", "pasara", "estudiante", "alumno",
    }

    # Trabajar con el texto original (con acentos) para buscar materias
    palabras = pregunta.strip().split()
    # Reconstruir las partes que no son stopwords
    fragmentos = []
    frag_actual = []
    for p in palabras:
        p_clean = _norm(p).strip("?,.")
        if p_clean in _stopwords or len(p_clean) <= 2:
            if frag_actual:
                fragmentos.append(" ".join(frag_actual))
                frag_actual = []
        else:
            frag_actual.append(p.strip("?,."))
    if frag_actual:
        fragmentos.append(" ".join(frag_actual))

    # Intentar buscar cada fragmento como materia
    materias_encontradas = []
    for frag in fragmentos:
        matches = _buscar_en_mapa(frag)
        if matches:
            materias_encontradas.append(frag)

    if not materias_encontradas:
        # Si no encontro materias especificas, tal vez es una pregunta generica
        return None

    return simular_reprobacion(materias_encontradas)


def _consulta_datos_local(pregunta: str) -> Optional[str]:
    """Responde preguntas simples sobre datos del estudiante sin usar LLM."""
    q = _norm(pregunta)
    q_exp = _expandir_sinonimos(q)
    df = _session_ref.get("historial_df")
    datos = _session_ref.get("datos_estudiante")

    if df is None or (hasattr(df, 'empty') and df.empty):
        return None  # Sin datos, dejar pasar al LLM que dara el mensaje adecuado

    # "que debe priorizar?" / "que materias priorizar?" / "por donde empezar?" / "que es lo urgente?"
    # Keywords flexibles que pueden aparecer en cualquier parte
    _sig_prioridad = [
        "priorizar", "prioridad", "priorizara", "priorizaria", "priorice",
        "empezar",  # "por donde empezar", "por cual empezar", "debe empezar"
        "urgente", "urgencia", "critico", "importante",  # "mas urgente", "que es critico"
        "orden de importancia", "estrategia de carga", "orden estrategico",
    ]
    _sig_contexto = ["materia", "cargar", "carga", "curso", "clase", "semestre", "alumno", "estudiante", "debe"]

    _es_pregunta_prioridad = (
        any(s in q_exp for s in _sig_prioridad)
        and any(s in q_exp for s in _sig_contexto)
    )

    # Casos extra que no necesitan contexto
    if not _es_pregunta_prioridad:
        if any(s in q_exp for s in [
            "que priorizar", "que priorizaria",
            "cargar primero", "tomar primero", "llevar primero",
            "orden estrategico", "orden de prioridad", "orden de carga",
            "mas critico", "mas importante", "mas urgente",
            "que hacer primero",
        ]):
            _es_pregunta_prioridad = True

    if _es_pregunta_prioridad:
        resultado = _session_ref.get("resultado_experto")
        if resultado and resultado.get("candidatas_detalles"):
            # Delegar a la tool priorizar_materias (invocacion directa)
            return priorizar_materias.invoke({})

    # "índice de reprobación" / "tasa de reprobación" / "cuántas tronó" — calcular localmente
    # con historial_calculo para coincidir exactamente con el valor del dashboard.
    _es_pregunta_indice = (
        ("indice" in q or "tasa" in q) and ("reprobar" in q_exp or "reprobacion" in q)
    ) or (
        # "cuantas tronó" / "cuántas ha tronado" + pregunta por índice/porcentaje/cantidad
        "tronar" in q_exp and any(s in q for s in ["indice", "tasa", "porcentaje", "porcent", "cuantas", "cuántas", "%"])
    )
    if _es_pregunta_indice:
        # Indice oficial (canonico): usa historial_calculo
        _hc = _session_ref.get("historial_calculo")
        df_calc = _hc if (_hc is not None and hasattr(_hc, "empty") and not _hc.empty) else df
        _n_rep = int((df_calc["estatus"].str.upper() == "REPROBADA").sum())
        _n_curs = int(df_calc["estatus"].str.upper().isin(["APROBADA", "REPROBADA"]).sum())
        _idx = round((_n_rep / _n_curs * 100), 1) if _n_curs > 0 else 0.0

        # Metrica historica (raw): todos los intentos reprobados
        _n_intentos_rep = int((df["estatus"].str.upper() == "REPROBADA").sum())
        _n_materias_con_rep = int(df[df["estatus"].str.upper() == "REPROBADA"]["clave"].nunique())

        resp = (
            f"**Índice de reprobación actual (oficial): {_idx}%**\n\n"
            f"- Se calcula sobre el estado ACTUAL de cada materia (último intento registrado)\n"
            f"- Materias que siguen pendientes de aprobar: {_n_rep}\n"
            f"- Materias cursadas (aprobadas + reprobadas): {_n_curs}\n"
            f"- Fórmula: {_n_rep}/{_n_curs} × 100 = {_idx}%\n"
        )

        # Si hay diferencia con el historico, mostrarla
        if _n_intentos_rep > _n_rep:
            intentos_recuperados = _n_intentos_rep - _n_rep
            resp += (
                f"\n**Historial de reprobaciones (todos los intentos):** {_n_intentos_rep} intentos reprobados "
                f"en {_n_materias_con_rep} materias distintas.\n"
                f"De esas reprobaciones, {intentos_recuperados} ya fueron recuperadas (aprobó en intento posterior). "
                f"Por eso el índice actual es menor que el total de intentos reprobados."
            )
        return resp

    # "que materias ha reprobado?" / "cuales reprobo?" / "tiene reprobadas?"
    _reprobada_signals = ["reprobar", "reprobada", "reprobado", "reprobadas", "ha reprobar"]
    if any(s in q_exp for s in _reprobada_signals) and not any(s in q_exp for s in ["que pasa", "si reprobar", "impacto", "consecuencia", "bloquea"]):
        # Usar historial_calculo (último estado por materia) para saber cuáles siguen reprobadas HOY
        _hc = _session_ref.get("historial_calculo")
        df_canon = _hc if (_hc is not None and hasattr(_hc, "empty") and not _hc.empty) else df
        rep = df_canon[df_canon["estatus"].str.upper() == "REPROBADA"]
        if rep.empty:
            return "El estudiante no tiene materias reprobadas."
        conteo = rep.groupby("clave").size()
        mapa = _cargar_mapa()

        # Separar por nivel de riesgo
        criticas = []
        normales = []

        for clave in conteo.index:
            filas = rep[rep["clave"] == clave]
            nombre = filas.iloc[0].get("nombre", "")
            # Contar intentos históricos reprobados desde el raw df
            veces = int(((df["clave"] == clave) & (df["estatus"].str.upper() == "REPROBADA")).sum())
            # Cuantas materias bloquea
            cascada = _cadena_impacto(clave, mapa)
            entry = (clave, nombre, veces, len(cascada))
            if veces >= 2:
                criticas.append(entry)
            else:
                normales.append(entry)

        # Ordenar normales por impacto (las que bloquean mas primero)
        normales.sort(key=lambda x: -x[3])

        lineas = []
        # Siempre mostrar el índice al inicio del bloque de reprobadas
        _hc2 = _session_ref.get("historial_calculo")
        df_calc2 = _hc2 if _hc2 is not None else df
        _n_rep2 = int((df_calc2["estatus"].str.upper() == "REPROBADA").sum())
        _n_curs2 = int(df_calc2["estatus"].str.upper().isin(["APROBADA", "REPROBADA"]).sum())
        _idx2 = round((_n_rep2 / _n_curs2 * 100), 1) if _n_curs2 > 0 else 0.0
        lineas = [
            f"**Índice de reprobación: {_idx2}%** ({_n_rep2} reprobadas / {_n_curs2} cursadas)",
            "",
            f"El estudiante tiene {len(conteo)} materia(s) reprobada(s) ({len(rep)} intentos en total).",
            "",
        ]

        if criticas:
            lineas.append("ATENCION — Materias en riesgo:")
            for clave, nombre, veces, n_bloq in criticas:
                estado = "BAJA DEFINITIVA" if veces >= 3 else "TERCERA OPORTUNIDAD (ultimo intento)"
                lineas.append(f"  ! {clave} {nombre} — {veces} reprobaciones — {estado}")
            lineas.append("")

        # Separar las que bloquean y las que no
        con_impacto = [(c, n, v, b) for c, n, v, b in normales if b > 0]
        sin_impacto = [(c, n, v, b) for c, n, v, b in normales if b == 0]

        if con_impacto:
            lineas.append("Reprobadas que bloquean otras materias (priorizar):")
            for clave, nombre, veces, n_bloq in con_impacto:
                lineas.append(f"  - {clave} {nombre} — bloquea {n_bloq} materias en cadena")
            lineas.append("")

        if sin_impacto:
            lineas.append(f"Reprobadas sin impacto en seriacion ({len(sin_impacto)}):")
            for clave, nombre, veces, n_bloq in sin_impacto:
                lineas.append(f"  - {clave} {nombre}")

        if not criticas and not con_impacto:
            lineas.append("")
            lineas.append("Ninguna de las reprobadas bloquea otras materias. El impacto en la trayectoria es menor.")
        elif con_impacto:
            lineas.append("")
            lineas.append(f"Recomendacion: priorizar aprobar las {len(con_impacto)} materias que bloquean seriacion.")

        return "\n".join(lineas)

    # "que materias lleva en curso?" / "que esta cursando?"
    _en_curso_signals = ["en curso", "cursando", "lleva actualmente", "esta llevando", "carga actual"]
    if any(s in q_exp or s in q for s in _en_curso_signals):
        ec = df[df["estatus"].str.upper().isin(["EN_CURSO", "RECURSANDO"])]
        if ec.empty:
            return "El estudiante no tiene materias en curso registradas."
        total_cred = ec["creditos"].sum() if "creditos" in ec.columns else 0
        lineas = [f"**{len(ec)} materias en curso** ({total_cred} creditos)\n"]
        for _, row in ec.iterrows():
            extra = " **(RECURSANDO)**" if str(row.get("estatus", "")).upper() == "RECURSANDO" else ""
            cred = row.get("creditos", "")
            lineas.append(f"- {row.get('clave','')} {row.get('nombre','')}{extra} — {cred}cr")
        return "\n".join(lineas)

    # "cuantas materias ha aprobado?" / "materias aprobadas"
    _aprobada_signals = ["aprobada", "aprobado", "aprobadas", "ha aprobar", "cuantas aprobar"]
    if any(s in q_exp for s in _aprobada_signals) and "no aprobar" not in q_exp:
        apr = df[df["estatus"].str.upper() == "APROBADA"]
        mapa = _cargar_mapa()
        pct = round(len(apr) / len(mapa) * 100, 1)
        return (
            f"**{len(apr)} materias aprobadas** de {len(mapa)} del plan ({pct}%)\n\n"
            f"Pendientes: {len(mapa) - len(apr)} materias"
        )

    # "cual es su promedio?" / "promedio del alumno"
    if "promedio" in q and datos:
        return f"**Promedio general: {datos.promedio_general}**"

    # "cuantos creditos lleva?" / "creditos del alumno"
    if "credito" in q:
        cred_total = _session_ref.get("creditos_totales", 404)
        cred_acum = _session_ref.get("creditos_acumulados", getattr(datos, 'total_creditos', 0) if datos else 0)
        pct = round((cred_acum / cred_total) * 100, 1) if cred_total > 0 else 0
        falt = max(0, cred_total - cred_acum)
        return (
            f"**Creditos: {cred_acum} / {cred_total}** ({pct}%)\n\n"
            f"Faltan **{falt} creditos** para completar el plan."
        )

    # "cual es su situacion?" / "es condicional?" / "es regular?"
    if datos and ("situacion" in q or "condicional" in q_exp or "regular" in q_exp or "irregular" in q_exp):
        sit = str(datos.situacion)
        extra = ""
        if "CONDICIONAL" in sit.upper():
            extra = "\n\nRestricciones: carga fija de exactamente 3 materias por semestre (ni mas ni menos)."
        return f"**Situacion: {sit}**{extra}"

    # "en que semestre va?" / "semestre actual"
    if "semestre" in q and ("va" in q or "actual" in q or "cual" in q or "esta" in q):
        resultado = _session_ref.get("resultado_experto")
        if resultado:
            sem = resultado.get("semestre_cursado", "?")
            restantes = max(0, 8 - int(sem)) if str(sem).isdigit() else "?"
            return f"**Semestre actual: {sem} de 8** — le faltan {restantes} semestres"

    # "que calificacion saco en X?" / "como le fue en X?" / "nota de X"
    _cal_signals = ["calificacion", "calificaciones", "nota", "notas", "como le fue", "como salio",
                    "cuanto saco", "que saco", "cuanto le fue", "que calificacion"]

    # "¿hay alguna materia donde sacó 7?" — búsqueda por VALOR numérico
    import re as _re
    _num_match = _re.search(r'\b(saco|obtuvo|tiene|calificacion de|nota de|con un|con nota)\s*([0-9]+(?:\.[0-9]+)?)\b', q)
    if not _num_match:
        _num_match = _re.search(r'\b([0-9]+(?:\.[0-9]+)?)\s*(de calificacion|de nota|en calificacion)\b', q)
    if _num_match:
        # Identificar el grupo que tiene el número
        grupos = [g for g in _num_match.groups() if g and _re.match(r'^[0-9]', g)]
        if grupos:
            cal_val = grupos[0]
            return buscar_por_calificacion.invoke({"calificacion": cal_val})

    if any(s in q for s in _cal_signals):
        # Extraer el nombre/clave de la materia de la pregunta
        _stopwords_cal = {"que", "cual", "cuanto", "como", "le", "fue", "saco", "en", "la", "el",
                          "calificacion", "nota", "salio", "de", "materia", "clase", "obtuvo", "tiene",
                          "alumno", "estudiante"}
        palabras = [p.strip("?,.'\"") for p in pregunta.split() if _norm(p.strip("?,.'\"")) not in _stopwords_cal and len(p.strip("?,.'\"")) > 2]
        if palabras:
            consulta = " ".join(palabras)
            matches = _buscar_en_mapa(consulta)
            if matches:
                lineas = []
                for clave, info in matches[:2]:
                    hist = df[df["clave"].str.upper() == clave]
                    if hist.empty:
                        lineas.append(f"{clave} {info.get('nombre','')}: sin registros en el historial.")
                        continue
                    for _, row in hist.iterrows():
                        cal = row.get("calificacion", "")
                        est = row.get("estatus", "")
                        per = row.get("periodo", "")
                        cal_str = str(cal) if str(cal) not in ("", "nan", "None") else "Sin calificación"
                        lineas.append(f"{clave} {info.get('nombre','')}: **{cal_str}** | {est} | Periodo: {per}")
                if lineas:
                    return "\n".join(lineas)

    return None


def respuesta_local(pregunta: str) -> Optional[str]:
    """Intenta responder sin LLM usando reglas locales.
    Retorna None si no hay match (la pregunta pasa al LLM que tambien conoce las reglas)."""
    q = _norm(pregunta)

    # Preguntas complejas que SIEMPRE deben ir al LLM (requieren razonamiento)
    _llm_only = ["como va", "esta en riesgo", "diagnostico",
                 "que deberia cargar", "candidatas", "criticas",
                 "cuanto le falta", "cuantos semestres",
                 # Preguntas sobre DATOS del estudiante (no sobre la regla)
                 "ya tiene", "tiene cubierta", "ya cumple", "cumple con",
                 "lleva la actividad", "tiene la actividad",
                 "tiene deportiva", "tiene cultural",
                 "cuantas eleccion", "progreso preesp",
                 "que periodo", "que cargo en", "que llevo en"]
    for signal in _llm_only:
        if _norm(signal) in q:
            return None

    # 1. Detectar simulaciones "que pasa si reprueba X"
    sim = _detectar_simulacion(pregunta)
    if sim:
        return sim

    # 2. Consultas de datos directas (sin LLM)
    data_resp = _consulta_datos_local(pregunta)
    if data_resp:
        return data_resp

    # 3. Buscar reglas locales
    q_expanded = _expandir_sinonimos(q)

    mejor_match = None
    mejor_score = 0

    for keywords, respuesta in _REGLAS_LOCALES:
        kw_norm = [_norm(k) for k in keywords]
        matches = sum(1 for kw in kw_norm if kw in q or kw in q_expanded)
        if matches == len(kw_norm) and matches > mejor_score:
            mejor_score = matches
            mejor_match = respuesta

    return mejor_match


# ═══════════════════════════════════════════════════════════════════════════
#  SIMULADOR "QUE PASA SI" — logica pura, sin LLM
# ═══════════════════════════════════════════════════════════════════════════

def simular_reprobacion(claves: List[str]) -> str:
    """Simula el impacto de reprobar una o varias materias. Retorna texto con analisis."""
    mapa = _cargar_mapa()
    df = _session_ref.get("historial_df")
    aprobadas_set = set()
    if df is not None and not df.empty:
        aprobadas_set = set(df[df["estatus"].str.upper() == "APROBADA"]["clave"].str.upper())

    resultados = []
    total_bloqueadas = set()

    for clave_input in claves:
        # Buscar la materia
        matches = _buscar_en_mapa(clave_input)
        if not matches:
            resultados.append(f"'{clave_input}' no encontrada en el plan.")
            continue

        clave, info = matches[0]
        cascada = _cadena_impacto(clave, mapa)
        cascada_pendiente = [c for c in cascada if c not in aprobadas_set]
        total_bloqueadas.update(cascada_pendiente)

        # Contar reprobaciones previas
        intentos_previos = 0
        if df is not None and not df.empty:
            rep = df[(df["clave"].str.upper() == clave) & (df["estatus"].str.upper() == "REPROBADA")]
            intentos_previos = len(rep)

        resultado = f"** {clave} - {info.get('nombre', '')} **\n"
        if intentos_previos == 0:
            resultado += "  Seria su primera reprobacion. Le quedarian 2 intentos.\n"
        elif intentos_previos == 1:
            resultado += "  ALERTA: Ya tiene 1 reprobacion. Entraria en TERCERA OPORTUNIDAD (ultimo intento).\n"
        elif intentos_previos >= 2:
            resultado += "  CRITICO: Ya tiene 2+ reprobaciones. Seria BAJA DEFINITIVA de esta materia.\n"

        if cascada_pendiente:
            resultado += f"  Materias bloqueadas en cascada: {len(cascada_pendiente)}\n"
            for c in cascada_pendiente[:6]:
                nombre_dep = mapa.get(c, {}).get("nombre", c)
                resultado += f"    - {c} ({nombre_dep})\n"
            if len(cascada_pendiente) > 6:
                resultado += f"    ... y {len(cascada_pendiente) - 6} mas\n"
        else:
            resultado += "  No bloquea ninguna materia pendiente.\n"

        resultados.append(resultado)

    # Resumen
    header = f"SIMULACION: Impacto de reprobar {len(claves)} materia(s)\n"
    header += "=" * 50 + "\n\n"
    footer = f"\nRESUMEN: Total de materias bloqueadas en cascada (sin duplicados): {len(total_bloqueadas)}"
    if total_bloqueadas:
        footer += f"\nMaterias afectadas: {', '.join(sorted(total_bloqueadas)[:10])}"
        if len(total_bloqueadas) > 10:
            footer += f" (+{len(total_bloqueadas) - 10} mas)"

    return header + "\n".join(resultados) + footer


import re as _re
_TOOL_CALL_PAT = _re.compile(r'^\s*\{\s*"name"\s*:', _re.MULTILINE)


def _es_mensaje_tool_call(msg) -> bool:
    """True si el mensaje es un paso intermedio de tool-calling (no respuesta final)."""
    # 1. Tiene tool_calls estructurados — mensaje de invocación, no de respuesta
    if getattr(msg, 'tool_calls', None):
        return True
    # 2. El contenido es JSON crudo de tool call (DeepSeek a veces lo embebe en content)
    content = getattr(msg, 'content', '') or ''
    if isinstance(content, str):
        stripped = content.strip()
        if _TOOL_CALL_PAT.search(stripped) and '"parameters"' in stripped:
            return True
    return False


def ejecutar_consulta(agent, pregunta: str, chat_history: List = None) -> str:
    import time
    if chat_history is None:
        chat_history = []

    # Intentar respuesta local primero (0 costo, instantanea)
    local = respuesta_local(pregunta)
    if local:
        return local

    messages = _trim_history(chat_history) + [HumanMessage(content=pregunta)]

    for intento in range(3):
        try:
            resultado = agent.invoke({"messages": messages})
            for msg in reversed(resultado.get("messages", [])):
                if isinstance(msg, AIMessage) and msg.content and not _es_mensaje_tool_call(msg):
                    return _extraer_texto(msg.content)
            return "No pude procesar tu pregunta."
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                if intento < 2:
                    time.sleep(15)
                    continue
                return "Servicio de IA saturado. Espera unos segundos e intenta de nuevo."
            return f"Error: {err}"
    return "Sin respuesta despues de varios intentos."


def ejecutar_consulta_stream(agent, pregunta: str, chat_history: List = None) -> Generator[str, None, None]:
    import time
    if chat_history is None:
        chat_history = []

    messages = _trim_history(chat_history) + [HumanMessage(content=pregunta)]

    for intento in range(3):
        try:
            got_response = False
            for event in agent.stream({"messages": messages}, stream_mode="messages"):
                msg, _ = event
                # Saltar mensajes intermedios de tool-calling
                if isinstance(msg, AIMessage) and msg.content and not _es_mensaje_tool_call(msg):
                    got_response = True
                    yield _extraer_texto(msg.content)
            if not got_response:
                yield "No pude procesar tu pregunta."
            return
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                if intento < 2:
                    time.sleep(10 * (intento + 1))
                    continue
                yield "Servicio de IA saturado. Espera unos segundos e intenta de nuevo."
                return
            yield f"Error: {err}"
            return
