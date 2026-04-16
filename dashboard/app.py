import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
import json
import tempfile
import os

# Imports locales
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsers import KardexParser, HistorialParser
from services import AcademicProcessor
from services.supabase_service import SupabaseService as DatabaseService
from agents.sistema_experto_seriacion import (
    ejecutar_sistema_experto,
    EL_RECOMENDADAS_POR_CICLO,
    EL_ACUMULADAS_CICLO,
    PREESP_RECOMENDADAS_POR_CICLO,
    PREESP_ACUMULADAS_CICLO,
)
from config import settings
from agents.agente_asesor import (
    crear_agente,
    ejecutar_consulta,
    ejecutar_consulta_stream,
    set_session_state,
    simular_reprobacion,
    ALL_TOOLS,
    consultar_preespecialidades,
    consultar_creditos_categoria,
    consultar_eleccion_libre as _tool_eleccion_libre,
    consultar_cocurriculares,
)
from langchain_core.messages import HumanMessage, AIMessage

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from generar_mapa_curricular import generar_mapa


# Configuración de página
st.set_page_config(
    page_title="Reporte de Estado Académico",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS personalizados
st.markdown("""
<style>
    .metric-box {
        padding: 20px;
        border-radius: 10px;
        background-color: #f0f2f6;
        margin: 10px 0;
        color: #1f1f1f;
    }
    .alerta-critica {
        background-color: #ffdddd;
        border-left: 4px solid #ff4444;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
        color: #000000;
    }
    .alerta-advertencia {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
        color: #000000;
    }
    .alerta-estatus {
        background-color: #ff6b6b;
        border: 2px solid #ff0000;
        padding: 20px;
        margin: 15px 0;
        border-radius: 10px;
        color: #ffffff;
        font-size: 18px;
        font-weight: bold;
        text-align: center;
    }
    .requisito-completado {
        color: #28a745;
    }
    .requisito-pendiente {
        color: #dc3545;
    }
    .badge-intento {
        background-color: #ffc107;
        color: #000;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 10px;
        font-weight: bold;
        margin-left: 5px;
    }

    /* ── Botones de navegación entre secciones ── */
    div[data-testid="stButton"].nav-next > button {
        height: 60px !important;
        font-size: 1.1rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.4px;
        background: linear-gradient(135deg, #1565c0 0%, #0d47a1 100%) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 18px rgba(21,101,192,0.45) !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }
    div[data-testid="stButton"].nav-next > button:hover {
        transform: translateY(-3px) !important;
        box-shadow: 0 8px 24px rgba(21,101,192,0.55) !important;
    }
    div[data-testid="stButton"].nav-next > button:active {
        transform: translateY(0) !important;
    }

    /* Banner CTA previo al botón */
    .nav-cta-banner {
        margin-top: 36px;
        padding: 18px 24px 16px 24px;
        background: linear-gradient(135deg, #f0f7ff 0%, #e8f0fe 100%);
        border-radius: 14px 14px 0 0;
        border: 1.5px solid #3b82f6;
        border-bottom: none;
        text-align: center;
    }
    .nav-cta-banner .nav-cta-label {
        font-size: 0.72rem;
        font-weight: 700;
        color: #1565c0;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        margin-bottom: 4px;
    }
    .nav-cta-banner .nav-cta-desc {
        font-size: 0.97rem;
        color: #1e3a5f;
        font-weight: 500;
        margin: 0;
    }
    /* Pegar el botón al banner (quitar radio superior del botón) */
    .nav-btn-attached div[data-testid="stButton"] > button {
        border-radius: 0 0 12px 12px !important;
        border: 1.5px solid #3b82f6 !important;
        border-top: none !important;
    }
</style>
""", unsafe_allow_html=True)


def cargar_mapa_curricular() -> dict:
    """Carga el mapa curricular oficial (real_completo, semestres 1-8)."""
    try:
        mapa_path = Path(__file__).parent.parent / "data" / "mapa_curricular_2021ID_real_completo.json"
        if mapa_path.exists():
            with open(mapa_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error cargando JSON: {e}")

    return {}


NOMBRES_CICLO = {
    0: "Co-curricular",
    1: "Semestre 1",
    2: "Semestre 2",
    3: "Semestre 3",
    4: "Semestre 4",
    5: "Semestre 5",
    6: "Semestre 6",
    7: "Semestre 7",
    8: "Semestre 8",
}


def crear_grafica_progreso_ciclo(ciclo: int, progreso: dict) -> go.Figure:
    """Crea gráfica de donut para un ciclo"""
    nombre_ciclo = NOMBRES_CICLO.get(ciclo, f"Ciclo {ciclo}")
    
    labels = []
    values = []
    colores = []
    
    if progreso.get("finalizadas", 0) > 0:
        labels.append("Finalizadas")
        values.append(progreso.get("finalizadas", 0))
        colores.append("#28a745")
    
    if progreso.get("en_curso", 0) > 0:
        labels.append("En Curso")
        values.append(progreso.get("en_curso", 0))
        colores.append("#ffc107")

    if progreso.get("recursando", 0) > 0:
        labels.append("Recursando")
        values.append(progreso.get("recursando", 0))
        colores.append("#ff8c00")

    if progreso.get("reprobadas", 0) > 0:
        labels.append("Reprobadas")
        values.append(progreso.get("reprobadas", 0))
        colores.append("#dc3545")
    
    if progreso.get("pendientes", 0) > 0:
        labels.append("Pendientes")
        values.append(progreso.get("pendientes", 0))
        colores.append("#6c757d")
    
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        marker=dict(colors=colores),
        hole=0.4,
        textinfo="none",
    )])
    
    fig.update_layout(
        title=nombre_ciclo,
        showlegend=True,
        height=400
    )
    
    return fig


def obtener_materias_por_estatus_ciclo(historial_filtrado_df, mapa_curricular_lista):
    """
    Devuelve un dict {ciclo: {estatus_label: [{Clave, Nombre, Créditos, Categoría}]}}
    para poder mostrar qué materias componen cada segmento de las gráficas.
    """
    status_map = {}
    for _, row in historial_filtrado_df.iterrows():
        clave = str(row.get("clave", "")).strip().upper()
        status_map[clave] = row.get("estatus", "")

    result = {}
    for ciclo in range(1, 9):
        materias_ciclo = [m for m in mapa_curricular_lista if m.get("ciclo") == ciclo]
        grupos = {
            "Finalizadas": [], "En Curso": [], "Recursando": [],
            "Reprobadas": [], "Pendientes": [],
        }
        for m in materias_ciclo:
            clave = str(m.get("clave", "")).strip().upper()
            estatus = status_map.get(clave, "")
            info = {
                "Clave": clave,
                "Nombre": m.get("nombre", ""),
                "Créditos": m.get("creditos", 0),
                "Categoría": m.get("categoria", ""),
            }
            if estatus == "APROBADA":
                grupos["Finalizadas"].append(info)
            elif estatus == "EN_CURSO":
                grupos["En Curso"].append(info)
            elif estatus == "RECURSANDO":
                grupos["Recursando"].append(info)
            elif estatus == "REPROBADA":
                grupos["Reprobadas"].append(info)
            else:
                # Solo marcar como pendiente si es materia obligatoria (BASICA, no-PID).
                # Las ELECCION_LIBRE y PRE_ESPECIALIDAD no cursadas no son pendientes individuales:
                # el alumno elige cuáles tomar de un pool, no está obligado a tomar todas.
                cat = m.get("categoria", "").upper().replace("-", "_").replace(" ", "_")
                es_opcional = "ELECCI" in cat or "LIBRE" in cat or "PRE" in cat
                clave_pid = clave.startswith("PID")
                if not es_opcional and not clave_pid:
                    grupos["Pendientes"].append(info)
        result[ciclo] = grupos
    return result


def detectar_sabaticos(historial_df):
    """
    Detecta semestres sabáticos a partir de los periodos del kardex.

    Periodos normales (hábiles): terminan en 01 (Primavera) o 03 (Otoño).
    Periodos de vacaciones: terminan en 02 (Verano) o 04 (Invierno).

    Un sabático es un semestre hábil (01 o 03) donde el estudiante
    no cursó ninguna materia, dentro del rango entre su primer y último
    semestre registrado.

    Returns:
        dict con: sabaticos, cantidad, max_permitidos, restantes,
                  semestres_activos, tiempo_max_años, semestres_max,
                  periodos_normales_cursados, periodos_vacaciones
    """
    base = {
        "sabaticos": [], "cantidad": 0, "max_permitidos": 3, "restantes": 3,
        "semestres_activos": 0, "tiempo_max_años": 8.0, "semestres_max": 16,
        "periodos_normales_cursados": [], "periodos_vacaciones": [],
    }

    if historial_df.empty or "periodo" not in historial_df.columns:
        return base

    periodos = set()
    for p in historial_df["periodo"].dropna().astype(str).tolist():
        p = p.strip()
        if len(p) == 6 and p.isdigit():
            periodos.add(p)

    if not periodos:
        return base

    # Excluir periodos donde TODAS las materias son BAJA_TEMPORAL (BTT)
    periodos_btt = set()
    if "estatus" in historial_df.columns:
        for p in periodos:
            materias_periodo = historial_df[historial_df["periodo"].astype(str).str.strip() == p]
            if not materias_periodo.empty and (materias_periodo["estatus"] == "BAJA_TEMPORAL").all():
                periodos_btt.add(p)
    periodos_activos = periodos - periodos_btt

    periodos_normales = sorted(p for p in periodos_activos if p[-2:] in ("01", "03"))
    periodos_vacaciones = sorted(p for p in periodos_activos if p[-2:] in ("02", "04"))

    if not periodos_normales:
        return base

    primer_p = periodos_normales[0]
    ultimo_p = periodos_normales[-1]

    # Generar todos los semestres hábiles esperados entre el primero y el último
    esperados = []
    año = int(primer_p[:4])
    sufijo = int(primer_p[4:])
    while True:
        periodo = f"{año:04d}{sufijo:02d}"
        if periodo > ultimo_p:
            break
        esperados.append(periodo)
        if sufijo == 1:
            sufijo = 3
        else:
            año += 1
            sufijo = 1

    sabaticos = [p for p in esperados if p not in set(periodos_normales)]
    cantidad = len(sabaticos)
    max_permitidos = 3
    restantes = max(0, max_permitidos - cantidad)
    semestres_activos = len(periodos_normales)
    tiempo_max_años = 8.0   # máximo absoluto: 8 años / 16 semestres sin excepción
    semestres_max = 16

    return {
        "sabaticos": sabaticos,
        "cantidad": cantidad,
        "max_permitidos": max_permitidos,
        "restantes": restantes,
        "semestres_activos": semestres_activos,
        "tiempo_max_años": tiempo_max_años,
        "semestres_max": semestres_max,
        "periodos_normales_cursados": periodos_normales,
        "periodos_vacaciones": periodos_vacaciones,
    }


def filtrar_ultimo_estatus(historial_df: pd.DataFrame) -> pd.DataFrame:
    """
    Filtra el historial para quedarse solo con el último registro de cada materia.
    Si una materia fue reprobada y luego aprobada, solo mantiene el registro aprobado.
    REGLA: Si algún registro de una materia es APROBADA, siempre se prioriza ese.
    """
    if historial_df.empty:
        return historial_df

    # Asegurar que periodo existe y convertir a string para ordenar
    if "periodo" not in historial_df.columns:
        return historial_df

    # Crear columna de prioridad: APROBADA tiene máxima prioridad
    df = historial_df.copy()
    df["_prioridad_aprobada"] = (df["estatus"] == "APROBADA").astype(int)

    # Ordenar: primero por prioridad APROBADA (desc), luego por periodo (desc)
    df_ordenado = df.sort_values(
        ["_prioridad_aprobada", "periodo"],
        ascending=[False, False],
        na_position='last'
    )

    # Quedarse con el primer registro de cada clave (APROBADA si existe, sino más reciente)
    df_ultimo = df_ordenado.drop_duplicates(subset=["clave"], keep="first")

    # Limpiar columna auxiliar
    df_ultimo = df_ultimo.drop(columns=["_prioridad_aprobada"])

    # Reordenar por ciclo y clave para mantener orden lógico
    if "ciclo" in df_ultimo.columns:
        df_ultimo = df_ultimo.sort_values(["ciclo", "clave"], na_position='last')

    return df_ultimo


def normalizar_ultima_carga(historial_df: pd.DataFrame) -> pd.DataFrame:
    """
    Corrige la última carga del kardex:
    si una materia del periodo más reciente tiene 0 créditos o no tiene
    calificación final, debe considerarse activa y no reprobada cerrada.
    """
    if historial_df.empty or "periodo" not in historial_df.columns:
        return historial_df

    df = historial_df.copy()
    df["periodo"] = df["periodo"].astype(str)

    periodos_validos = [p for p in df["periodo"].dropna().astype(str).tolist() if p.isdigit()]
    if not periodos_validos:
        return df

    ultimo_periodo = max(periodos_validos)
    mask_ultimo = df["periodo"].astype(str).eq(ultimo_periodo)

    if "creditos" in df.columns:
        creditos = pd.to_numeric(df["creditos"], errors="coerce").fillna(0)
    else:
        creditos = pd.Series(0, index=df.index)

    if "calificacion" in df.columns:
        calificaciones = pd.to_numeric(df["calificacion"], errors="coerce")
    else:
        calificaciones = pd.Series(pd.NA, index=df.index)

    mask_reprobada_abierta = (
        mask_ultimo
        & df["estatus"].astype(str).eq("REPROBADA")
        & (
            creditos.eq(0)
            | calificaciones.isna()
            | calificaciones.eq(0)
        )
    )

    df.loc[mask_reprobada_abierta, "estatus"] = "EN_CURSO"
    if "calificacion" in df.columns:
        df.loc[mask_reprobada_abierta, "calificacion"] = pd.NA

    return df


def marcar_recursando(historial_filtrado: pd.DataFrame, historial_completo: pd.DataFrame) -> pd.DataFrame:
    """
    Marca como RECURSANDO las materias que están EN_CURSO pero fueron reprobadas
    en algún periodo anterior, o que aparecen múltiples veces en el kardex.
    Permite distinguir un primer intento de un recurse.
    
    Reglas:
    1. EN_CURSO con reprobación previa
    2. EN_CURSO con calificación < 7
    3. Materia que aparece múltiples veces, con al menos una sin valor (EN_CURSO)
    """
    if historial_filtrado.empty:
        return historial_filtrado

    historial_completo = normalizar_ultima_carga(historial_completo)

    materias_alguna_vez_reprobadas = set(
        historial_completo[historial_completo["estatus"] == "REPROBADA"]["clave"].unique()
    )

    # Detectar materias que aparecen múltiples veces en el historial completo
    # y tienen al menos una aparición EN_CURSO (sin calificación)
    claves_multiples_apariciones = set()
    claves_con_sin_calificacion = set()
    
    for clave in historial_completo["clave"].unique():
        registros_clave = historial_completo[historial_completo["clave"] == clave]
        
        # Si aparece más de una vez
        if len(registros_clave) > 1:
            claves_multiples_apariciones.add(clave)
            
            # Detectar si hay al menos una aparición EN_CURSO (sin valor)
            if (registros_clave["estatus"] == "EN_CURSO").any():
                claves_con_sin_calificacion.add(clave)

    df = historial_filtrado.copy()

    # Condición 1: EN_CURSO pero fue reprobada en algún periodo anterior
    mask_reprobada_antes = (df["estatus"] == "EN_CURSO") & (df["clave"].isin(materias_alguna_vez_reprobadas))

    # Condición 2: EN_CURSO con calificación registrada menor a 7 (no aprobó pero aún no figura como REPROBADA)
    if "calificacion" in df.columns:
        cal = pd.to_numeric(df["calificacion"], errors="coerce")
        mask_calificacion_baja = (df["estatus"] == "EN_CURSO") & cal.notna() & (cal < 7)
    else:
        mask_calificacion_baja = pd.Series(False, index=df.index)

    # Condición 3: Materia que aparece múltiples veces y tiene una versión EN_CURSO
    mask_multiples_apariciones = (df["estatus"] == "EN_CURSO") & (df["clave"].isin(claves_con_sin_calificacion))

    df.loc[mask_reprobada_antes | mask_calificacion_baja | mask_multiples_apariciones, "estatus"] = "RECURSANDO"
    return df


def calcular_eleccion_libre(historial_df: pd.DataFrame, mapa_curricular) -> dict:
    """
    Calcula el progreso de materias de elección libre por ciclo anual.
    El mapa_curricular puede ser dict {clave: info} o list [{clave, ...}].
    Usa semestres 1-8 del real_completo:
    - Ciclo anual 1: semestres 1-2 → 2 materias de EL requeridas
    - Ciclo anual 2: semestres 3-4 → 2 materias de EL requeridas
    - Ciclos anuales 3 y 4 combinados: semestres 5-8 → 8 materias totales
    """
    # Normalizar mapa a dict {clave: info}
    if isinstance(mapa_curricular, list):
        mapa_dict = {m.get("clave", ""): m for m in mapa_curricular if isinstance(m, dict)}
    else:
        mapa_dict = mapa_curricular if isinstance(mapa_curricular, dict) else {}

    eleccion_libre = {
        1: {"aprobadas": 0, "en_curso": 0, "requeridas": 2, "claves": [], "nombres": []},
        2: {"aprobadas": 0, "en_curso": 0, "requeridas": 2, "claves": [], "nombres": []},
        "3_y_4": {"aprobadas": 0, "en_curso": 0, "requeridas": 8, "claves": [], "nombres": []}
    }
    
    # Primero identificar qué pre-especialidad tiene más materias aprobadas (será la de titulación)
    # CORRECCIÓN: Invertir la lógica - los códigos ID342X son ITIC, ID341X son IoN
    pre_especialidades = {"IoN": 0, "ITIC": 0}
    
    for _, row in historial_df.iterrows():
        clave = row.get("clave", "")
        nombre = row.get("nombre", "")
        estatus = row.get("estatus", "")
        
        if clave in mapa_dict:
            categoria = mapa_dict[clave].get("categoria", "")
            if categoria in ("PRE_ESPECIALIDAD", "PRE-ESPECIALIDAD", "PREESPECIALIDAD") and estatus == "APROBADA":
                # CORRECCIÓN: Identificación basada en el nombre de la materia desde el historial
                if "inteligencia" in nombre.lower() and ("negocios" in nombre.lower() or "organizacional" in nombre.lower()):
                    pre_especialidades["IoN"] += 1
                elif "innovaci" in nombre.lower() and "tic" in nombre.lower():
                    pre_especialidades["ITIC"] += 1
                # Fallback por código si no hay nombre claro
                elif clave in ["ID3420", "ID3421", "ID3422", "ID3423", "ID3424"]:
                    pre_especialidades["IoN"] += 1
                elif clave in ["ID3416", "ID3417", "ID3418", "ID3419", "ID3469"]:
                    pre_especialidades["ITIC"] += 1
    
    # Determinar pre-especialidad de titulación (la que tiene más aprobadas)
    pre_titulacion = "IoN" if pre_especialidades["IoN"] > pre_especialidades["ITIC"] else "ITIC"
    
    # Ahora contar materias de elección libre - USAR EL HISTORIAL ACADÉMICO COMO FUENTE DE VERDAD
    for _, row in historial_df.iterrows():
        clave = row.get("clave", "")
        nombre = row.get("nombre", "")
        estatus = row.get("estatus", "")
        
        if clave not in mapa_dict:
            continue
            
        ciclo = mapa_dict[clave].get("ciclo", 0)          # semestre 1-8
        categoria = mapa_dict[clave].get("categoria", "")
        
        # Helper: clasificar en ciclo anual visual
        def ciclo_anual_de(sem):
            if sem in (1, 2):
                return 1
            elif sem in (3, 4):
                return 2
            else:
                return "3_y_4"

        # Caso 1: Materias explícitamente de elección libre
        if "ELECCI" in categoria.upper() and "LIBRE" in categoria.upper():
            c_anual = ciclo_anual_de(ciclo)
            if estatus == "APROBADA":
                eleccion_libre[c_anual]["aprobadas"] += 1
            elif estatus in ("EN_CURSO", "RECURSANDO"):
                eleccion_libre[c_anual]["en_curso"] += 1
            eleccion_libre[c_anual]["claves"].append(clave)
            eleccion_libre[c_anual]["nombres"].append(nombre)

        # Caso 2: Materias de la pre-especialidad NO usada → cuentan como EL en ciclos 3y4
        elif categoria in ("PRE_ESPECIALIDAD", "PRE-ESPECIALIDAD", "PREESPECIALIDAD") and ciclo >= 5:
            # Determinar a qué pre-especialidad pertenece
            if "inteligencia" in nombre.lower() and ("negocios" in nombre.lower() or "organizacional" in nombre.lower()):
                pre_materia = "IoN"
            elif "innovaci" in nombre.lower() and "tic" in nombre.lower():
                pre_materia = "ITIC"
            elif clave in ["ID3420", "ID3421", "ID3422", "ID3423", "ID3424"]:
                pre_materia = "IoN"
            elif clave in ["ID3416", "ID3417", "ID3418", "ID3419", "ID3469"]:
                pre_materia = "ITIC"
            else:
                pre_materia = None

            # Si NO es la pre-especialidad de titulación, cuenta como elección libre
            if pre_materia and pre_materia != pre_titulacion:
                if estatus == "APROBADA":
                    eleccion_libre["3_y_4"]["aprobadas"] += 1
                elif estatus in ("EN_CURSO", "RECURSANDO"):
                    eleccion_libre["3_y_4"]["en_curso"] += 1
                eleccion_libre["3_y_4"]["claves"].append(clave)
                eleccion_libre["3_y_4"]["nombres"].append(nombre)
    
    return eleccion_libre, pre_titulacion, pre_especialidades


def calcular_progreso_preespecialidades(historial_df: pd.DataFrame, mapa_curricular) -> dict:
    """
    Calcula el progreso en cada pre-especialidad.
    Cada pre-especialidad necesita 5 materias para completarse.
    El mapa_curricular puede ser dict {clave: info} o list [{clave, ...}].
    """
    # Normalizar mapa a dict {clave: info}
    if isinstance(mapa_curricular, list):
        mapa_dict = {m.get("clave", ""): m for m in mapa_curricular if isinstance(m, dict)}
    else:
        mapa_dict = mapa_curricular if isinstance(mapa_curricular, dict) else {}

    # Identificar materias de pre-especialidad desde el historial
    preespecialidades = {}
    materias_procesadas = {}  # {clave: estatus_mas_reciente}
    
    # Buscar en el historial las materias de pre-especialidad
    for _, row in historial_df.iterrows():
        clave = row.get("clave", "")
        nombre = row.get("nombre", "")
        estatus = row.get("estatus", "")
        periodo = row.get("periodo", "")
        
        # Verificar si está en el mapa como PRE-ESPECIALIDAD
        if clave in mapa_dict:
            categoria = mapa_dict[clave].get("categoria", "")
            if categoria in ("PRE_ESPECIALIDAD", "PRE-ESPECIALIDAD", "PREESPECIALIDAD"):
                # Determinar a qué pre-especialidad pertenece por el nombre del historial
                if "inteligencia" in nombre.lower() and ("negocios" in nombre.lower() or "organizacional" in nombre.lower()):
                    pre_esp = "Inteligencia Organizacional y de Negocios"
                elif "innovaci" in nombre.lower() and "tic" in nombre.lower():
                    pre_esp = "Innovación en TIC"
                else:
                    # Fallback por código
                    if clave in ["ID3420", "ID3421", "ID3422", "ID3423", "ID3424"]:
                        pre_esp = "Inteligencia Organizacional y de Negocios"
                    elif clave in ["ID3416", "ID3417", "ID3418", "ID3419", "ID3469"]:
                        pre_esp = "Innovación en TIC"
                    else:
                        continue  # Skip si no podemos identificar
                
                # Guardar o actualizar el estatus más reciente (último periodo)
                if clave not in materias_procesadas or periodo > materias_procesadas[clave]["periodo"]:
                    materias_procesadas[clave] = {
                        "pre_esp": pre_esp,
                        "estatus": estatus,
                        "periodo": periodo,
                        "nombre": nombre
                    }
    
    # Ahora contar por pre-especialidad usando solo el estatus más reciente
    for clave, datos in materias_procesadas.items():
        pre = datos["pre_esp"]
        estatus = datos["estatus"]
        
        # Inicializar si no existe
        if pre not in preespecialidades:
            preespecialidades[pre] = {"total": 0, "aprobadas": 0, "en_curso": 0, "claves": []}
        
        # Agregar clave
        preespecialidades[pre]["claves"].append(clave)
        preespecialidades[pre]["total"] += 1
        
        # Contar estado actual (última aparición de la materia)
        if estatus == "APROBADA":
            preespecialidades[pre]["aprobadas"] += 1
        elif estatus in ("EN_CURSO", "RECURSANDO"):
            preespecialidades[pre]["en_curso"] += 1
    
    return preespecialidades


def combinar_historial_y_kardex(
    historial_df: pd.DataFrame,
    kardex_df: pd.DataFrame,
    aprobadas_historial: set,
) -> pd.DataFrame:
    """
    Combina los datos del historial académico (fuente de verdad para APROBADAS)
    con los datos del kardex (detalle de periodos, intentos, EN_CURSO, REPROBADA).

    Reglas:
    - Si el historial dice APROBADA → se mantiene APROBADA sin importar el kardex.
    - Del kardex se toman: periodos, intentos, EN_CURSO, REPROBADA para materias
      que NO están aprobadas en el historial.
    - Materias que están en el historial pero NO en el kardex se agregan como
      APROBADA (si tienen calificación) o PENDIENTE.
    """
    if kardex_df.empty:
        return historial_df.copy()

    # Empezar con los registros del kardex (tienen periodos e intentos)
    merged = kardex_df.copy()

    # REGLA PRINCIPAL: Forzar APROBADA para materias aprobadas según historial
    mask_aprobada = merged["clave"].isin(aprobadas_historial)
    # Solo forzar si el kardex NO la tiene ya como APROBADA (evitar perder datos)
    mask_no_aprobada_kardex = merged["estatus"] != "APROBADA"
    mask_forzar = mask_aprobada & mask_no_aprobada_kardex

    # Para materias que el historial dice APROBADA pero el kardex dice otra cosa:
    # Buscar si hay algún registro APROBADA en el kardex para esa clave
    claves_ya_aprobadas_kardex = set(
        merged.loc[merged["estatus"] == "APROBADA", "clave"].unique()
    )
    # Solo forzar las que no tienen ningún registro APROBADA en el kardex
    mask_forzar = mask_forzar & ~merged["clave"].isin(claves_ya_aprobadas_kardex)

    if mask_forzar.any():
        # Tomar el registro más reciente de cada clave y marcarlo como APROBADA
        for clave in merged.loc[mask_forzar, "clave"].unique():
            idx_clave = merged[merged["clave"] == clave].index
            # Tomar el último registro (periodo más reciente)
            ultimo_idx = idx_clave[-1]
            merged.loc[ultimo_idx, "estatus"] = "APROBADA"

    # Agregar materias del historial que NO están en el kardex
    claves_kardex = set(merged["clave"].unique())
    for _, row in historial_df.iterrows():
        clave = row.get("clave", "")
        if clave not in claves_kardex and row.get("estatus") == "APROBADA":
            merged = pd.concat([merged, pd.DataFrame([{
                "clave": clave,
                "nombre": row.get("nombre", ""),
                "periodo": "",
                "ciclo": row.get("ciclo", 0),
                "calificacion": row.get("calificacion"),
                "creditos": row.get("creditos", 0),
                "estatus": "APROBADA",
            }])], ignore_index=True)

    return merged


@st.fragment
def _widget_disponibilidad_horaria():
    """
    Fragment de disponibilidad horaria.
    - st.pills para toggle rápido de horas (L-V) y días completos.
    - st.data_editor para control celda a celda.
    Los pills y el data_editor se sincronizan bidireccionalmente.
    """
    import pandas as _pd_disp

    horas_rango = list(range(7, 22))
    dias_semana = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado"]
    DIAS_CORTO  = {"Lunes": "Lun", "Martes": "Mar", "Miercoles": "Mié",
                   "Jueves": "Jue", "Viernes": "Vie", "Sabado": "Sáb"}
    SEMANA = [d for d in dias_semana if d != "Sabado"]
    HORAS_OPTS = [f"{h:02d}:00" for h in horas_rango]

    # ── Inicializar df ───────────────────────────────────────────────
    if "disp_df" not in st.session_state:
        data = {
            dia: ([False] * len(horas_rango) if dia == "Sabado"
                  else [7 <= h < 17 for h in horas_rango])
            for dia in dias_semana
        }
        st.session_state.disp_df = _pd_disp.DataFrame(data, index=HORAS_OPTS)

    def _computar_pills(df):
        """Devuelve (horas_activas_llv, dias_todos) calculados desde df."""
        h_act = [HORAS_OPTS[i] for i, h in enumerate(horas_rango)
                 if all(df.loc[HORAS_OPTS[i], d] for d in SEMANA)]
        d_act = [dia for dia in dias_semana if all(df[dia])]
        return h_act, d_act

    def _sync_pills(df):
        """Actualiza las keys de session_state de los pills para reflejar df."""
        h, d = _computar_pills(df)
        st.session_state["_pills_h"] = h
        st.session_state["_pills_d"] = d

    # Inicializar keys de pills si no existen
    if "_pills_h" not in st.session_state:
        _sync_pills(st.session_state.disp_df)

    # ── Presets rápidos ──────────────────────────────────────────────
    col_q1, col_q2, col_q3, col_q4 = st.columns(4)
    with col_q1:
        if st.button("☀️ Matutino (7-15)", key="quick_mat"):
            for dia in dias_semana:
                st.session_state.disp_df[dia] = [7 <= h < 15 and dia != "Sabado" for h in horas_rango]
            _sync_pills(st.session_state.disp_df)
            st.rerun(scope="fragment")
    with col_q2:
        if st.button("🌙 Vespertino (14-22)", key="quick_vesp"):
            for dia in dias_semana:
                st.session_state.disp_df[dia] = [14 <= h < 22 and dia != "Sabado" for h in horas_rango]
            _sync_pills(st.session_state.disp_df)
            st.rerun(scope="fragment")
    with col_q3:
        if st.button("📅 Todo disponible", key="quick_todo"):
            for dia in dias_semana:
                st.session_state.disp_df[dia] = [True] * len(horas_rango)
            _sync_pills(st.session_state.disp_df)
            st.rerun(scope="fragment")
    with col_q4:
        if st.button("🔄 Reiniciar", key="quick_reset"):
            for dia in dias_semana:
                st.session_state.disp_df[dia] = (
                    [False] * len(horas_rango) if dia == "Sabado"
                    else [7 <= h < 17 for h in horas_rango]
                )
            _sync_pills(st.session_state.disp_df)
            st.rerun(scope="fragment")

    # ── Pills: horas activas en L–V ──────────────────────────────────
    horas_en_df, dias_en_df = _computar_pills(st.session_state.disp_df)

    st.caption("**Horas activas en Lun–Vie** — selecciona/deselecciona para activar o desactivar esa hora en todos los días entre semana")
    sel_horas = st.pills(
        "horas_lv",
        options=HORAS_OPTS,
        selection_mode="multi",
        key="_pills_h",
        label_visibility="collapsed",
    )

    if set(sel_horas or []) != set(horas_en_df):
        nueva_h = set(sel_horas or [])
        for hora_str in nueva_h - set(horas_en_df):
            for dia in SEMANA:
                st.session_state.disp_df.loc[hora_str, dia] = True
        for hora_str in set(horas_en_df) - nueva_h:
            for dia in SEMANA:
                st.session_state.disp_df.loc[hora_str, dia] = False
        st.rerun(scope="fragment")

    # ── Pills: días completos ────────────────────────────────────────
    st.caption("**Días completos** — selecciona/deselecciona para activar o desactivar todas las horas de ese día")
    sel_dias = st.pills(
        "dias",
        options=list(DIAS_CORTO.keys()),
        format_func=lambda d: DIAS_CORTO[d],
        selection_mode="multi",
        key="_pills_d",
        label_visibility="collapsed",
    )

    if set(sel_dias or []) != set(dias_en_df):
        nueva_d = set(sel_dias or [])
        for dia in nueva_d - set(dias_en_df):
            st.session_state.disp_df[dia] = [True] * len(horas_rango)
        for dia in set(dias_en_df) - nueva_d:
            st.session_state.disp_df[dia] = [False] * len(horas_rango)
        st.rerun(scope="fragment")

    # ── data_editor (control celda a celda) ─────────────────────────
    edited_df = st.data_editor(
        st.session_state.disp_df,
        use_container_width=True,
        height=560,
    )

    if not edited_df.equals(st.session_state.disp_df):
        st.session_state.disp_df = edited_df
        _sync_pills(edited_df)          # sincronizar pills con cambios manuales
        st.rerun(scope="fragment")

    # ── Resumen ──────────────────────────────────────────────────────
    disp = {
        dia: [horas_rango[i] for i, val in enumerate(st.session_state.disp_df[dia]) if val]
        for dia in dias_semana
    }
    st.session_state.disp = disp
    horas_totales = sum(len(v) for v in disp.values())
    dias_activos  = sum(1 for v in disp.values() if v)
    st.caption(f"**{horas_totales}** horas disponibles en **{dias_activos}** días")



def obtener_periodos_oferta(plan_estudios: str = "2021ID") -> list:
    """Obtiene periodos disponibles de oferta académica para un plan."""
    ruta_oferta = Path(__file__).parent.parent / "agents" / "OfertaAcademica"
    if not ruta_oferta.exists():
        return []

    periodos = set()
    archivos = sorted(list(ruta_oferta.glob("*.xls")) + list(ruta_oferta.glob("*.xlsx")))
    for archivo in archivos:
        try:
            df = pd.read_excel(archivo, header=1)
            if not {"Plan Estudio", "Periodo"}.issubset(set(df.columns)):
                continue
            sub = df[df["Plan Estudio"].astype(str).str.strip().eq(plan_estudios)]
            if sub.empty:
                continue
            for p in sub["Periodo"].dropna().astype(str).tolist():
                if p.isdigit():
                    periodos.add(p)
        except Exception:
            continue

    return sorted(periodos)


def obtener_nombre_temporada(periodo: str) -> str:
    """Convierte YYYYPP a temporada legible."""
    sufijo = str(periodo)[-2:]
    temporadas = {
        "01": "Primavera",
        "02": "Verano",
        "03": "Otoño",
        "04": "Invierno",
    }
    return temporadas.get(sufijo, "Periodo")


def formatear_periodo(periodo: str) -> str:
    """Formato amigable de periodo: YYYYPP - Temporada."""
    p = str(periodo).strip()
    return f"{p} - {obtener_nombre_temporada(p)}"


def _init_agente():
    """Inicializa el agente y el estado del chat (se llama una vez)."""
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "agente_executor" not in st.session_state:
        st.session_state.agente_executor = None
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False

    # Recrear agente si no existe o si cambió el modelo
    _modelo_actual = "deepseek/deepseek-chat-v3-0324"
    if st.session_state.agente_executor is None or st.session_state.get("_agente_modelo") != _modelo_actual:
        try:
            executor = crear_agente(modelo=_modelo_actual)
            if executor:
                st.session_state.agente_executor = executor
                st.session_state._agente_modelo = _modelo_actual
        except Exception:
            pass

    # Inyectar session_state al agente
    session_dict = {}
    for key in [
        "datos_estudiante", "resultado_experto",
        "creditos_totales", "creditos_acumulados",
        "nivel_ingles_texto", "nivel_ingles_aprobado", "ingles_completo",
        "codigos_ingles_aprobados", "cargas_generadas",
        "especialidad_forzada",
        "eleccion_libre_info", "preespecialidades_info",
        "alertas_academicas",
    ]:
        if key in st.session_state:
            session_dict[key] = st.session_state[key]
    # El agente siempre ve el historial en modo simulación (sin EN_CURSO)
    if "historial_calculo" in st.session_state:
        session_dict["historial_df"] = st.session_state["historial_calculo"]
    elif "historial_df" in st.session_state:
        session_dict["historial_df"] = st.session_state["historial_df"]
    set_session_state(session_dict)



import unicodedata as _unicodedata
def _norm(s: str) -> str:
    return _unicodedata.normalize("NFD", s.lower()).encode("ascii", "ignore").decode()

# Mapa de pestanas para navegacion automatica
_TAB_MAP = {
    "historia academica": "Situación Académica",
    "resumen general": "Situación Académica",
    "progreso": "Situación Académica",
    "creditos": "Situación Académica",
    "promedio": "Situación Académica",
    "ingles": "Situación Académica",
    "deportiva": "Situación Académica",
    "cultural": "Situación Académica",
    "eleccion libre": "Situación Académica",
    "especialidad": "Situación Académica",
    "pre-especialidad": "Situación Académica",
    "sistema experto": "Materias Candidatas para Cargar",
    "candidatas": "Materias Candidatas para Cargar",
    "generador de cargas": "Generador de Cargas",
    "horarios": "Generador de Cargas",
    "mapa curricular": "Mapa Curricular",
    "oferta": "Oferta & Candidatas",
}


def _detectar_tab_en_respuesta(texto: str):
    """Detecta si la respuesta del agente menciona una pestana del sistema."""
    texto_lower = _norm(texto) if texto else ""
    for keyword, tab_name in _TAB_MAP.items():
        if _norm(keyword) in texto_lower:
            return tab_name
    return None


def _enviar_mensaje_chat(texto: str):
    """Procesa un mensaje en el chat del agente."""
    st.session_state.chat_messages.append({"role": "user", "content": texto})

    # Intentar respuesta local primero (sin API) para chips registrados
    _local_tool = _CHIP_LOCAL.get(texto)
    respuesta = None
    if _local_tool == "consultar_preespecialidades":
        try:
            respuesta = consultar_preespecialidades.invoke({})
        except Exception:
            respuesta = None
    elif _local_tool == "consultar_creditos_categoria":
        try:
            respuesta = consultar_creditos_categoria.invoke({})
        except Exception:
            respuesta = None

    if not respuesta:
        if st.session_state.agente_executor is None:
            respuesta = "Asistente no disponible. Verificar que OPENROUTER_API_KEY esté configurada en .env"
        else:
            lc_history = []
            for msg in st.session_state.chat_messages[:-1]:
                if msg["role"] == "user":
                    lc_history.append(HumanMessage(content=msg["content"]))
                else:
                    lc_history.append(AIMessage(content=msg["content"]))

            respuesta = ejecutar_consulta(
                st.session_state.agente_executor,
                texto,
                chat_history=lc_history,
            )

    st.session_state.chat_messages.append({"role": "assistant", "content": respuesta})


def _generar_pdf_asesoria() -> bytes:
    """Genera un PDF completo de asesoria curricular con toda la informacion del estudiante."""
    from io import BytesIO
    from datetime import datetime

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch, cm
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable, KeepTogether,
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    except ImportError:
        return None

    # ── Colores ──
    C_PRIMARY = HexColor("#1a1a2e")
    C_ACCENT = HexColor("#667eea")
    C_GRAY = HexColor("#64748b")
    C_LIGHT = HexColor("#f1f5f9")
    C_RED = HexColor("#dc2626")
    C_GREEN = HexColor("#16a34a")
    C_ORANGE = HexColor("#ea580c")
    C_WHITE = HexColor("#ffffff")
    C_BLACK = HexColor("#0f172a")

    # ── Estilos ──
    styles = getSampleStyleSheet()
    s_title = ParagraphStyle("T", parent=styles["Heading1"], fontSize=16, textColor=C_PRIMARY,
                              spaceAfter=2, fontName="Helvetica-Bold")
    s_subtitle = ParagraphStyle("ST", parent=styles["Normal"], fontSize=9, textColor=C_GRAY,
                                 spaceAfter=10)
    s_h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, textColor=C_PRIMARY,
                           spaceBefore=14, spaceAfter=6, fontName="Helvetica-Bold")
    s_h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=10, textColor=C_ACCENT,
                           spaceBefore=8, spaceAfter=4, fontName="Helvetica-Bold")
    s_body = ParagraphStyle("B", parent=styles["Normal"], fontSize=9, leading=13,
                             textColor=C_BLACK, spaceAfter=2)
    s_small = ParagraphStyle("SM", parent=s_body, fontSize=8, textColor=C_GRAY)
    s_bold = ParagraphStyle("BD", parent=s_body, fontName="Helvetica-Bold")
    s_alert = ParagraphStyle("AL", parent=s_body, textColor=C_RED, fontName="Helvetica-Bold")
    s_ok = ParagraphStyle("OK", parent=s_body, textColor=C_GREEN, fontName="Helvetica-Bold")
    s_chat_user = ParagraphStyle("CU", parent=s_body, leftIndent=10, textColor=C_PRIMARY,
                                  fontName="Helvetica-Bold", fontSize=8, leading=11)
    s_chat_bot = ParagraphStyle("CB", parent=s_body, leftIndent=10, textColor=C_GRAY,
                                 fontSize=8, leading=11)

    def _hr():
        return HRFlowable(width="100%", thickness=0.5, color=HexColor("#e2e8f0"), spaceAfter=6, spaceBefore=6)

    def _kv_table(rows):
        """Tabla clave-valor compacta."""
        t = Table(rows, colWidths=[140, 320])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), C_GRAY),
            ("TEXTCOLOR", (1, 0), (1, -1), C_BLACK),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        return t

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.7*inch, rightMargin=0.7*inch,
                            topMargin=0.5*inch, bottomMargin=0.5*inch)

    story = []
    now = datetime.now()
    datos = st.session_state.get("datos_estudiante")

    # ══════════════════════════════════════════════════════════
    # HEADER
    # ══════════════════════════════════════════════════════════
    story.append(Paragraph("Reporte de Asesoria Curricular", s_title))
    story.append(Paragraph(
        f"Universidad del Caribe — Plan IDeIO 2021 — Generado: {now.strftime('%d/%m/%Y %H:%M')}",
        s_subtitle
    ))
    story.append(_hr())

    if not datos:
        story.append(Paragraph("No hay datos del estudiante cargados.", s_body))
        doc.build(story)
        buf.seek(0)
        return buf.getvalue()

    # ══════════════════════════════════════════════════════════
    # 1. DATOS DEL ESTUDIANTE
    # ══════════════════════════════════════════════════════════
    story.append(Paragraph("1. Datos del Estudiante", s_h2))
    story.append(_kv_table([
        ["Matricula:", str(datos.matricula)],
        ["Nombre:", str(datos.nombre)],
        ["Plan de estudios:", str(datos.plan_estudios)],
        ["Situacion:", str(datos.situacion)],
        ["Promedio general:", str(datos.promedio_general)],
    ]))

    # ══════════════════════════════════════════════════════════
    # 2. AVANCE ACADEMICO
    # ══════════════════════════════════════════════════════════
    story.append(Paragraph("2. Avance Academico", s_h2))

    cred_total = st.session_state.get("creditos_totales", 404)
    cred_acum = st.session_state.get("creditos_acumulados", datos.total_creditos)
    cred_falt = max(0, cred_total - cred_acum)
    pct = round((cred_acum / cred_total) * 100, 1) if cred_total > 0 else 0

    resultado = st.session_state.get("resultado_experto")
    sem = resultado.get("semestre_cursado", 0) if resultado else 0
    sem_obj = resultado.get("semestre_objetivo", 0) if resultado else 0
    esp = resultado.get("especialidad_detectada", "No detectada") if resultado else "No detectada"

    avance_esperado = round((sem / 8) * 100) if sem > 0 else 0
    diferencia = pct - avance_esperado
    if diferencia >= -5:
        regularidad = "AL CORRIENTE"
        reg_style = s_ok
    elif diferencia >= -15:
        regularidad = "LIGERAMENTE ATRASADO"
        reg_style = ParagraphStyle("W", parent=s_body, textColor=C_ORANGE, fontName="Helvetica-Bold")
    else:
        regularidad = "SIGNIFICATIVAMENTE ATRASADO"
        reg_style = s_alert

    # Contar materias
    df = st.session_state.get("historial_df")
    n_aprobadas = 0
    n_en_curso = 0
    n_reprobadas_total = 0
    if df is not None and not df.empty:
        n_aprobadas = len(df[df["estatus"].str.upper() == "APROBADA"])
        n_en_curso = len(df[df["estatus"].str.upper().isin(["EN_CURSO", "RECURSANDO"])])
        n_reprobadas_total = len(df[df["estatus"].str.upper() == "REPROBADA"])

    mapa = cargar_mapa_curricular()
    if isinstance(mapa, dict):
        total_mat = len(mapa)
    elif isinstance(mapa, list):
        total_mat = len(mapa)
    else:
        total_mat = 86
    n_pendientes = total_mat - n_aprobadas

    story.append(_kv_table([
        ["Creditos:", f"{cred_acum} / {cred_total}  ({pct}%)  —  Faltan: {cred_falt}"],
        ["Semestre actual:", f"{sem} de 8  —  Restantes: {max(0, 8 - sem)}"],
        ["Materias aprobadas:", f"{n_aprobadas} de {total_mat}  —  Pendientes: {n_pendientes}  —  En curso: {n_en_curso}"],
        ["Especialidad:", str(esp)],
    ]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"Regularidad: {regularidad}  (avance real {pct}% vs esperado ~{avance_esperado}%)", reg_style))

    # ══════════════════════════════════════════════════════════
    # 3. ALERTAS Y RIESGOS
    # ══════════════════════════════════════════════════════════
    story.append(Paragraph("3. Alertas y Riesgos", s_h2))

    alertas = []
    sit = str(datos.situacion).upper()
    if "CONDICIONAL" in sit or "IRREGULAR" in sit:
        alertas.append(f"Alumno con situacion {datos.situacion} — maximo 4 materias por semestre")

    # Inglés
    ing_ok = st.session_state.get("ingles_completo", False)
    nivel_ing = st.session_state.get("nivel_ingles_texto", "No disponible")
    if not ing_ok and sem >= 6:
        alertas.append(f"Ingles incompleto en semestre avanzado (nivel actual: {nivel_ing})")

    # Reprobadas multiples
    if df is not None and not df.empty:
        rep = df[df["estatus"].str.upper() == "REPROBADA"]
        if not rep.empty:
            conteo = rep.groupby("clave").size()
            for clave, veces in conteo.items():
                nombre_mat = ""
                match = df[df["clave"] == clave]
                if not match.empty:
                    nombre_mat = match.iloc[0].get("nombre", "")
                if veces >= 3:
                    alertas.append(f"BAJA DEFINITIVA: {clave} {nombre_mat} ({veces} reprobaciones)")
                elif veces == 2:
                    alertas.append(f"TERCERA OPORTUNIDAD: {clave} {nombre_mat} — proximo intento es el ultimo")

    if alertas:
        for a in alertas:
            story.append(Paragraph(f"  {a}", s_alert))
    else:
        story.append(Paragraph("Sin alertas. Situacion academica regular.", s_ok))

    # ══════════════════════════════════════════════════════════
    # 4. REQUISITOS DE EGRESO
    # ══════════════════════════════════════════════════════════
    story.append(Paragraph("4. Requisitos de Egreso", s_h2))

    nivel_num = st.session_state.get("nivel_ingles_aprobado", 0)

    requisitos_data = [
        ["Requisito", "Estado", "Detalle"],
        ["Ingles (Topicos 2)",
         "Completo" if ing_ok else "Pendiente",
         f"Nivel {nivel_num}/6 — {nivel_ing}"],
    ]

    req_table = Table(requisitos_data, colWidths=[150, 80, 230])
    req_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (1, 1), (1, 1), HexColor("#dcfce7") if ing_ok else HexColor("#fee2e2")),
    ]))
    story.append(req_table)

    # ── Numeracion dinamica ──
    _sec = [4]  # ya usamos 1-4 arriba
    def _secnum(titulo):
        _sec[0] += 1
        return f"{_sec[0]}. {titulo}"

    # ══════════════════════════════════════════════════════════
    # 5. MATERIAS CANDIDATAS (Sistema Experto)
    # ══════════════════════════════════════════════════════════
    story.append(Paragraph(_secnum("Materias Recomendadas para Siguiente Semestre"), s_h2))

    if resultado and resultado.get("candidatas_detalles"):
        candidatas = resultado["candidatas_detalles"]
        story.append(Paragraph(
            f"El sistema experto recomienda {len(candidatas)} materias para el semestre {sem_obj}.",
            s_body
        ))

        por_prioridad = {}
        for c in candidatas:
            p = c.get("prioridad", 5)
            por_prioridad.setdefault(p, []).append(c)

        etiquetas = {1: "URGENTE", 2: "IMPORTANTE", 3: "CERRAR CICLO", 4: "CICLO ACTUAL", 5: "ELECCIÓN LIBRE", 6: "CO-CURRICULAR"}

        for p in sorted(por_prioridad.keys()):
            label = etiquetas.get(p, "?")
            story.append(Paragraph(f"Prioridad {p} — {label}", s_h3))

            table_data = [["Clave", "Materia", "Ciclo", "Cr", "Razon"]]
            for c in por_prioridad[p]:
                table_data.append([
                    str(c.get("clave", "")),
                    str(c.get("nombre", ""))[:40],
                    str(c.get("ciclo", "")),
                    str(c.get("creditos", "")),
                    str(c.get("razon", ""))[:50],
                ])

            t = Table(table_data, colWidths=[50, 160, 35, 25, 190])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("ALIGN", (2, 0), (3, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_LIGHT]),
            ]))
            story.append(t)
    else:
        story.append(Paragraph(
            "El sistema experto aun no se ha ejecutado. Cargar documentos y revisar la pestana Sistema Experto.",
            s_small
        ))

    # ══════════════════════════════════════════════════════════
    # 6. COMPARACION CARGA ACTUAL VS RECOMENDADA
    # ══════════════════════════════════════════════════════════
    story.append(Paragraph(_secnum("Comparacion: Carga Actual vs Recomendada"), s_h2))

    en_curso_claves = set()
    if df is not None and not df.empty:
        en_curso_claves = set(df[df["estatus"].str.upper().isin(["EN_CURSO", "RECURSANDO"])]["clave"].str.upper())

    if not en_curso_claves:
        story.append(Paragraph("El estudiante no tiene materias en curso registradas.", s_small))
    elif not resultado:
        story.append(Paragraph("El sistema experto no se ha ejecutado. No se puede comparar.", s_small))
    else:
        candidatas_claves = {c["clave"].upper() for c in resultado.get("candidatas_detalles", [])}
        coinciden = en_curso_claves & candidatas_claves
        solo_curso = en_curso_claves - candidatas_claves
        solo_rec = candidatas_claves - en_curso_claves

        story.append(_kv_table([
            ["En curso:", f"{len(en_curso_claves)} materias"],
            ["Coinciden con recomendacion:", f"{len(coinciden)}  ({', '.join(sorted(coinciden)) if coinciden else '-'})"],
        ]))

        if solo_curso:
            story.append(Paragraph(
                f"Cursando pero NO recomendadas: {', '.join(sorted(solo_curso))}",
                ParagraphStyle("W2", parent=s_body, textColor=C_ORANGE)
            ))
        if solo_rec:
            top_rec = sorted(solo_rec)[:8]
            story.append(Paragraph(
                f"Recomendadas pero NO cursando: {', '.join(top_rec)}"
                + (f" (+{len(solo_rec)-8} mas)" if len(solo_rec) > 8 else ""),
                s_body
            ))
        if not solo_curso and not solo_rec:
            story.append(Paragraph("La carga actual es consistente con las recomendaciones.", s_ok))

    # ══════════════════════════════════════════════════════════
    # 7. HISTORIAL DE REPROBADAS
    # ══════════════════════════════════════════════════════════
    story.append(Paragraph(_secnum("Historial de Materias Reprobadas"), s_h2))

    has_reprobadas = False
    if df is not None and not df.empty:
        rep = df[df["estatus"].str.upper() == "REPROBADA"]
        if not rep.empty:
            has_reprobadas = True
            rep_data = [["Clave", "Materia", "Calificacion", "Periodo", "Intentos"]]
            conteo = rep.groupby("clave").size()
            for clave in conteo.index:
                filas = rep[rep["clave"] == clave]
                nombre = filas.iloc[0].get("nombre", "")
                for _, row in filas.iterrows():
                    rep_data.append([
                        str(row.get("clave", "")),
                        str(nombre)[:35],
                        str(row.get("calificacion", "")),
                        str(row.get("periodo", "")),
                        str(int(conteo[clave])),
                    ])

            t = Table(rep_data, colWidths=[50, 180, 65, 65, 50])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), C_WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("ALIGN", (2, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, HexColor("#fff1f2")]),
            ]))
            story.append(t)

    if not has_reprobadas:
        story.append(Paragraph("El estudiante no tiene materias reprobadas.", s_ok))

    # ══════════════════════════════════════════════════════════
    # 8. CONVERSACION DE ASESORIA
    # ══════════════════════════════════════════════════════════
    story.append(Paragraph(_secnum("Registro de Consultas al Asistente"), s_h2))

    if st.session_state.chat_messages:
        story.append(Paragraph(
            "Preguntas realizadas durante la sesion de asesoria y respuestas del sistema.",
            s_small
        ))
        story.append(Spacer(1, 4))

        for msg in st.session_state.chat_messages:
            if msg["role"] == "user":
                story.append(Paragraph(f"Asesor:  {msg['content']}", s_chat_user))
            else:
                texto = msg["content"].replace("\n", "<br/>").replace("  ", " ")
                if len(texto) > 800:
                    texto = texto[:800] + "..."
                story.append(Paragraph(f"Sistema:  {texto}", s_chat_bot))
            story.append(Spacer(1, 3))
    else:
        story.append(Paragraph("No se realizaron consultas al asistente durante esta sesion.", s_small))

    # ══════════════════════════════════════════════════════════
    # FOOTER
    # ══════════════════════════════════════════════════════════
    story.append(Spacer(1, 16))
    story.append(_hr())
    story.append(Paragraph(
        f"Documento generado automaticamente por el Sistema Experto de Asesoria Curricular — "
        f"{now.strftime('%d/%m/%Y %H:%M')}",
        ParagraphStyle("FT", parent=s_small, alignment=TA_CENTER)
    ))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


# Chips de accion rapida
_CHIPS = [
    "¿Cómo va este estudiante?",
    "¿Está en riesgo académico?",
    "¿Qué materias debería cargar?",
    "¿Cómo va en su pre-especialidad?",
    "¿Cuáles son sus materias críticas por seriación?",
    "¿Qué le falta para egresar?",
]

# Chips que se resuelven localmente (sin llamar al LLM)
_CHIP_LOCAL = {
    "¿Cómo va en su pre-especialidad?": "consultar_preespecialidades",
    "¿Qué le falta para egresar?": "consultar_creditos_categoria",
}


@st.dialog("Asistente Curricular", width="large")
def _chat_dialog():
    """Dialog modal con el chat del agente."""

    st.markdown("""
    <style>
    div[data-testid="stDialog"] > div {border-radius:12px;}
    div[data-testid="stDialog"] h2 {font-size:1.05rem;font-weight:600;letter-spacing:-.01em;color:#1a1a2e;}
    div[data-testid="stChatMessage"] {padding:10px 14px;margin:2px 0;border-radius:10px;}
    div[data-testid="stChatMessage"] p {font-size:14px;line-height:1.55;}
    </style>
    """, unsafe_allow_html=True)

    # ── Toolbar ──
    t1, t2, t3 = st.columns([5, 1, 1])
    with t1:
        st.caption("Consulta situacion academica, materias, seriacion o requisitos.")
    with t2:
        if st.session_state.chat_messages:
            pdf_bytes = _generar_pdf_asesoria()
            if pdf_bytes:
                st.download_button(
                    "PDF",
                    data=pdf_bytes,
                    file_name="asesoria_curricular.pdf",
                    mime="application/pdf",
                    key="download_pdf_btn",
                    use_container_width=True,
                )
    with t3:
        if st.button("Limpiar", key="clear_chat_btn", type="tertiary"):
            st.session_state.chat_messages = []
            st.rerun(scope="fragment")

    # ── Mensajes ──
    chat_container = st.container(height=370)
    with chat_container:
        for msg in st.session_state.chat_messages:
            role = "human" if msg["role"] == "user" else "assistant"
            with st.chat_message(role):
                st.markdown(msg["content"])

    # ── Boton de navegacion si la ultima respuesta menciona una pestana ──
    if st.session_state.chat_messages:
        last_msg = st.session_state.chat_messages[-1]
        if last_msg["role"] == "assistant":
            tab_detectada = _detectar_tab_en_respuesta(last_msg["content"])
            if tab_detectada:
                if st.button(f"Ir a: {tab_detectada}", key="nav_tab_btn", type="primary", use_container_width=True):
                    st.session_state._navigate_tab = tab_detectada
                    st.rerun()  # full rerun cierra dialog y navega

    # ── Chips de accion rapida (2 filas de 3) ──
    if not st.session_state.chat_messages:
        row1 = st.columns(3)
        for i in range(3):
            with row1[i]:
                if st.button(_CHIPS[i], key=f"chip_{i}", use_container_width=True):
                    with st.spinner("Consultando..."):
                        _enviar_mensaje_chat(_CHIPS[i])
                    st.rerun(scope="fragment")
        row2 = st.columns(3)
        for i in range(3, 6):
            with row2[i - 3]:
                if st.button(_CHIPS[i], key=f"chip_{i}", use_container_width=True):
                    with st.spinner("Consultando..."):
                        _enviar_mensaje_chat(_CHIPS[i])
                    st.rerun(scope="fragment")

    # ── Input libre ──
    with st.form("agent_chat_form", clear_on_submit=True, border=False):
        cols = st.columns([6, 1])
        with cols[0]:
            user_input = st.text_input(
                "q",
                placeholder="Escribe tu consulta...",
                label_visibility="collapsed",
            )
        with cols[1]:
            submitted = st.form_submit_button("Enviar", use_container_width=True)

    if submitted and user_input and user_input.strip():
        with st.spinner("Consultando..."):
            _enviar_mensaje_chat(user_input.strip())
        st.rerun(scope="fragment")


def _render_agente_chat():
    """Renderiza la burbuja flotante del agente, visible en todas las vistas."""
    import streamlit.components.v1 as components

    _init_agente()

    if st.button("open_agent", key="agent_bubble_btn"):
        _chat_dialog()

    # ── Navegacion pendiente: clic en la pestana via JS ──
    pending_tab = st.session_state.pop("_navigate_tab", None)
    if pending_tab:
        import streamlit.components.v1 as _nav_comp
        # Los tabs de Streamlit son button[role="tab"] con el texto del tab
        _nav_comp.html(f"""
        <script>
        (function() {{
            const pdoc = window.parent.document;
            const target = "{pending_tab}";
            const tabs = pdoc.querySelectorAll('button[role="tab"]');
            for (const tab of tabs) {{
                if (tab.textContent.includes(target)) {{
                    tab.click();
                    tab.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    break;
                }}
            }}
        }})();
        </script>
        """, height=0)

    components.html("""
    <script>
    (function() {
        const pdoc = window.parent.document;

        function hideAgentBtn() {
            pdoc.querySelectorAll('button[kind="secondary"]').forEach(b => {
                if (b.textContent.trim() === 'open_agent') {
                    let el = b;
                    for (let i = 0; i < 5 && el; i++) {
                        el = el.parentElement;
                        if (el && el.getAttribute &&
                            (el.getAttribute('data-testid') === 'stButton' ||
                             el.getAttribute('data-testid') === 'element-container')) {
                            el.style.cssText = 'position:fixed!important;bottom:-9999px!important;' +
                                'left:-9999px!important;width:1px!important;height:1px!important;' +
                                'overflow:hidden!important;opacity:0!important;';
                            return;
                        }
                    }
                    b.parentElement.style.cssText =
                        'position:fixed!important;bottom:-9999px!important;left:-9999px!important;' +
                        'width:1px!important;height:1px!important;overflow:hidden!important;' +
                        'opacity:0!important;';
                }
            });
        }

        hideAgentBtn();
        const obs = new MutationObserver(hideAgentBtn);
        obs.observe(pdoc.body, { childList: true, subtree: true });

        function findTargetBtn() {
            let btn = null;
            pdoc.querySelectorAll('button').forEach(b => {
                if (b.textContent.trim() === 'open_agent') btn = b;
            });
            return btn;
        }

        function makeBubbleOnClick() {
            return function() {
                const btn = findTargetBtn();
                if (btn) { btn.click(); return; }
                // Streamlit puede tardar un ciclo en remontar el boton tras rerun
                let tries = 0;
                const iv = setInterval(function() {
                    const b2 = findTargetBtn();
                    if (b2) { b2.click(); clearInterval(iv); }
                    else if (++tries >= 5) clearInterval(iv);
                }, 100);
            };
        }

        // Si el bubble ya existe (re-render de Streamlit), solo re-adjuntar onclick y salir
        const _existingBubble = pdoc.getElementById('agent-chat-bubble');
        if (_existingBubble) {
            _existingBubble.onclick = makeBubbleOnClick();
            return;
        }

        const css = pdoc.createElement('style');
        css.textContent = `
            #agent-chat-bubble {
                position: fixed;
                bottom: 24px;
                right: 24px;
                z-index: 999999;
                width: 56px;
                height: 56px;
                border-radius: 16px;
                background: #1a1a2e;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                border: none;
                outline: none;
                box-shadow: 0 2px 12px rgba(0,0,0,.18);
                transition: transform .2s ease, box-shadow .2s ease, background .2s ease;
            }
            #agent-chat-bubble:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(0,0,0,.25);
                background: #2d2d4e;
            }
            #agent-chat-bubble:active {
                transform: translateY(0) scale(.96);
            }
            #agent-chat-bubble svg {
                width: 24px;
                height: 24px;
                fill: none;
                stroke: #fff;
                stroke-width: 1.8;
                stroke-linecap: round;
                stroke-linejoin: round;
            }
            #agent-bubble-tooltip {
                position: fixed;
                bottom: 38px;
                right: 90px;
                background: #1a1a2e;
                color: #fff;
                padding: 6px 12px;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 500;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
                white-space: nowrap;
                opacity: 0;
                pointer-events: none;
                transition: opacity .2s ease;
                z-index: 999998;
                letter-spacing: -.01em;
            }
            #agent-bubble-tooltip::after {
                content: '';
                position: absolute;
                right: -5px;
                top: 50%;
                transform: translateY(-50%);
                border: 5px solid transparent;
                border-left-color: #1a1a2e;
            }
            #agent-chat-bubble:hover ~ #agent-bubble-tooltip {
                opacity: 1;
            }
        `;
        pdoc.head.appendChild(css);

        const bubble = pdoc.createElement('button');
        bubble.id = 'agent-chat-bubble';
        bubble.setAttribute('aria-label', 'Abrir asistente curricular');
        bubble.innerHTML = `
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7
                    8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8
                    8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48
                    0 0 1 8 8v.5z"/>
            </svg>`;
        bubble.onclick = makeBubbleOnClick();

        const tip = pdoc.createElement('div');
        tip.id = 'agent-bubble-tooltip';
        tip.textContent = 'Asistente curricular';

        const wrap = pdoc.createElement('div');
        wrap.id = 'agent-bubble-wrap';
        wrap.appendChild(bubble);
        wrap.appendChild(tip);
        pdoc.body.appendChild(wrap);
    })();
    </script>
    """, height=0)



def main():
    """Función principal de la aplicación"""

    # CSS para compactar el sidebar
    st.markdown("""
        <style>
        section[data-testid="stSidebar"] .block-container { padding-top: 0.5rem; padding-bottom: 0.5rem; }
        section[data-testid="stSidebar"] h1 { font-size: 1.1rem; margin-bottom: 0.2rem; }
        section[data-testid="stSidebar"] h2 { font-size: 0.95rem; margin-top: 0.4rem; margin-bottom: 0.1rem; }
        section[data-testid="stSidebar"] h3 { font-size: 0.85rem; margin-top: 0.3rem; margin-bottom: 0.1rem; }
        section[data-testid="stSidebar"] p { margin-bottom: 0.2rem; }
        section[data-testid="stSidebar"] hr { margin: 0.3rem 0; }
        section[data-testid="stSidebar"] .stFileUploader { margin-bottom: 0.2rem; }
        section[data-testid="stSidebar"] .stRadio { margin-bottom: 0.1rem; }
        </style>
    """, unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuración")

        # ── PREFERENCIA DE ESPECIALIDAD (solo cuando ambos archivos cargados) ──
        if "datos_estudiante" in st.session_state:
            st.subheader("🎯 Especialidad")
            st.caption("Línea de preespecialidad. Si aún no se define, el sistema la infiere.")
            _esp_opciones = {
                "Sin preferencia (el sistema infiere)": None,
                "TICS — Tecnologías de Información y Comunicación": "TICS",
                "Business Intelligence — Inteligencia de Negocios": "BUSINESS_INTELLIGENCE",
            }
            _esp_sel = st.radio(
                "Especialidad del estudiante",
                list(_esp_opciones.keys()),
                index=0,
                label_visibility="collapsed",
                key="radio_especialidad",
            )
            st.session_state.especialidad_forzada = _esp_opciones[_esp_sel]
            st.markdown("---")

        # ── PASO 1: Subir Historial Académico (PRIMERO) ──
        st.subheader("📄 Paso 1: Historial Académico")
        st.caption("Fuente principal de materias aprobadas.")
        historial_file = st.file_uploader(
            "Cargar Historial Académico (PDF)",
            type="pdf",
            key="historial_uploader",
            help="El historial académico oficial contiene todas las materias aprobadas, ciclos y categorías"
        )

        if historial_file is not None:
            # Procesar automáticamente cuando se sube un archivo nuevo.
            # Se compara el file_id para no reprocesar en cada rerender de Streamlit.
            if st.session_state.get("_historial_file_id") != historial_file.file_id:
                try:
                    with st.spinner("Procesando historial académico..."):
                        with open("temp_historial.pdf", "wb") as f:
                            f.write(historial_file.getvalue())

                        # Generar mapa curricular
                        mapa = generar_mapa("temp_historial.pdf")

                        # Parsear historial para extraer materias con estatus
                        historial_parser = HistorialParser()
                        historial_parser.parse_historial("temp_historial.pdf")

                        if os.path.exists("temp_historial.pdf"):
                            os.remove("temp_historial.pdf")

                        # Guardar mapa en disco para referencia legacy
                        mapa_path = Path(__file__).parent.parent / "data" / "mapa_curricular_2021ID.json"
                        mapa_path.parent.mkdir(exist_ok=True)
                        with open(mapa_path, "w", encoding="utf-8") as f:
                            json.dump(mapa, f, ensure_ascii=False, indent=2)

                        st.session_state.creditos_totales = historial_parser.creditos_totales
                        st.session_state.creditos_acumulados = historial_parser.creditos_acumulados

                        # Guardar materias aprobadas y DataFrame del historial
                        aprobadas = historial_parser.obtener_aprobadas()
                        historial_ac_df = historial_parser.to_dataframe()
                        st.session_state.aprobadas_historial = aprobadas
                        st.session_state.historial_academico_df = historial_ac_df

                        # Guardar nivel de inglés
                        st.session_state.codigos_ingles_aprobados = historial_parser.codigos_ingles_aprobados
                        st.session_state.nivel_ingles_texto = historial_parser.nivel_ingles_texto
                        st.session_state.nivel_ingles_aprobado = historial_parser.nivel_ingles_aprobado
                        st.session_state.ingles_completo = historial_parser.ingles_completo

                        # Guardar identidad del historial para validación cruzada con kardex
                        st.session_state.historial_matricula = historial_parser.matricula
                        st.session_state.historial_nombre = historial_parser.nombre

                        # Marcar este archivo como ya procesado
                        st.session_state._historial_file_id = historial_file.file_id

                        n_aprobadas = len(aprobadas)

                except Exception as e:
                    import traceback
                    st.error(f"❌ Error al procesar historial: {str(e)}")
                    st.code(traceback.format_exc())

        # Mostrar estado del historial
        if "aprobadas_historial" in st.session_state:
            n_apr = len(st.session_state.aprobadas_historial)
            cr_ac = st.session_state.get("creditos_acumulados", "—")
            cr_tot = st.session_state.get("creditos_totales", "—")
            st.caption(f"Cargado · {n_apr} aprobadas · {cr_ac}/{cr_tot} créditos")
        else:
            st.warning("⚠️ Sube el historial académico primero")

        st.markdown("---")

        # ── PASO 2: Subir Kardex (DESPUÉS) ──
        st.subheader("📄 Paso 2: Kardex")
        st.caption("Agrega periodos, intentos y materias en curso.")

        pdf_file = st.file_uploader(
            "Cargar Kardex (PDF)",
            type="pdf",
            help="Selecciona el archivo PDF del kardex del estudiante"
        )

        if pdf_file is not None:
            if "aprobadas_historial" not in st.session_state:
                st.warning("⚠️ Se recomienda subir el historial académico antes del kardex para mejores resultados.")

            if st.session_state.get("_kardex_file_id") == pdf_file.file_id:
                # Ya procesado: solo mostrar estado
                if "datos_estudiante" in st.session_state:
                    _dat = st.session_state.datos_estudiante
                    st.caption(f"Cargado · {_dat.situacion}")
            else:
              try:
                with st.spinner("Procesando kardex..."):
                    # Guardar archivo temporal
                    with open("temp_kardex.pdf", "wb") as f:
                        f.write(pdf_file.getvalue())
                    temp_path = "temp_kardex.pdf"

                    # Parsear kardex
                    parser = KardexParser()
                    datos = parser.parse_kardex(temp_path)
                    kardex_df = parser.to_dataframe()

                    # Validar que kardex y historial corresponden al mismo estudiante
                    hist_mat = st.session_state.get("historial_matricula", "")
                    if hist_mat and datos.matricula and hist_mat != datos.matricula:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                        st.error(
                            f"❌ Los archivos no corresponden al mismo estudiante.\n\n"
                            f"**Historial académico:** matrícula `{hist_mat}`\n\n"
                            f"**Kardex subido:** matrícula `{datos.matricula}`\n\n"
                            "Por favor sube el kardex del mismo estudiante."
                        )
                        st.stop()

                    # Guardar en BD local
                    db = DatabaseService()
                    db.crear_estudiante(datos.matricula, {
                        "nombre": datos.nombre,
                        "plan_estudios": datos.plan_estudios,
                        "situacion": datos.situacion,
                        "total_creditos": datos.total_creditos,
                        "promedio_general": datos.promedio_general
                    })

                    db.crear_registro_historial(
                        datos.matricula,
                        [
                            {
                                "clave": m.clave,
                                "nombre": m.nombre,
                                "periodo": m.periodo,
                                "ciclo": m.ciclo,
                                "calificacion": m.calificacion,
                                "creditos": m.creditos,
                                "estatus": m.estatus
                            }
                            for m in datos.materias
                        ]
                    )

                    # MERGE: Combinar con historial académico si está disponible
                    aprobadas_hist = st.session_state.get("aprobadas_historial", set())
                    historial_ac_df = st.session_state.get("historial_academico_df", pd.DataFrame())

                    if aprobadas_hist:
                        historial_combinado = combinar_historial_y_kardex(
                            historial_ac_df, kardex_df, aprobadas_hist
                        )
                    else:
                        historial_combinado = kardex_df

                    st.session_state.datos_estudiante = datos
                    st.session_state.historial_df = historial_combinado
                    st.session_state._scroll_sidebar_top = True
                    st.session_state._kardex_file_id = pdf_file.file_id

                    # Limpiar archivo temporal
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

                    n_aprobadas_final = (historial_combinado["estatus"] == "APROBADA").sum()
                    st.toast(f"✅ Kardex procesado — {n_aprobadas_final} materias aprobadas", icon="✅")
              except Exception as e:
                import traceback
                st.error(f"❌ Error al procesar PDF: {str(e)}")
                st.code(traceback.format_exc())
              else:
                st.rerun()  # rerender con datos_estudiante ya en session_state → muestra especialidad

    # Auto-scroll sidebar al top cuando se acaban de cargar ambos archivos
    if st.session_state.get("_scroll_sidebar_top", False):
        st.session_state._scroll_sidebar_top = False
        import streamlit.components.v1 as _comp_scroll
        _comp_scroll.html("""
        <script>
        (function() {
            var sb = window.parent.document.querySelector(
                'section[data-testid="stSidebar"] > div'
            );
            if (sb) { sb.scrollTop = 0; }
        })();
        </script>
        """, height=0)

    # ── Página de bienvenida (definida aquí para poder usarla antes de cargar datos) ──
    def _pg_inicio():
        st.markdown("""
<style>
.intro-hero {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
    border-radius: 12px;
    padding: 48px 40px 40px 40px;
    margin-bottom: 32px;
    color: #ffffff;
}
.intro-hero h1 {
    font-size: 2rem;
    font-weight: 700;
    margin: 0 0 10px 0;
    letter-spacing: -0.5px;
    color: #ffffff;
}
.intro-hero p {
    font-size: 1.05rem;
    color: #c9d6e3;
    margin: 0;
    line-height: 1.7;
    max-width: 680px;
}
.intro-badge {
    display: inline-block;
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #a8c4e0;
    margin-bottom: 18px;
}
.step-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
}
.step-card {
    background: #ffffff;
    border: 1px solid #e8ecf0;
    border-radius: 10px;
    padding: 22px 22px 18px 22px;
    position: relative;
}
.step-number {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #0f3460;
    background: #eaf0fb;
    border-radius: 4px;
    padding: 2px 8px;
    display: inline-block;
    margin-bottom: 10px;
}
.step-card h3 {
    font-size: 0.98rem;
    font-weight: 700;
    color: #1a1a2e;
    margin: 0 0 7px 0;
}
.step-card p {
    font-size: 0.875rem;
    color: #555e6e;
    margin: 0;
    line-height: 1.6;
}
.step-card .step-hint {
    font-size: 0.78rem;
    color: #0f3460;
    font-weight: 600;
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid #eef0f4;
}
.info-row {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 28px;
}
.info-chip {
    background: #f4f6fa;
    border: 1px solid #dde2ec;
    border-radius: 8px;
    padding: 12px 18px;
    font-size: 0.85rem;
    color: #333;
    flex: 1;
    min-width: 160px;
}
.info-chip strong {
    display: block;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #0f3460;
    margin-bottom: 3px;
}
.divider-label {
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #8a92a6;
    margin: 28px 0 14px 0;
}
</style>

<div class="intro-hero">
    <div class="intro-badge">Universidad del Caribe &nbsp;·&nbsp; IDeIO 2021</div>
    <h1>Asesor de Trayectoria Académica</h1>
    <p>
        Herramienta de apoyo a la tutoría que analiza el historial del estudiante,
        detecta alertas académicas, recomienda materias para el próximo semestre
        y genera combinaciones de carga optimizadas según su disponibilidad horaria.
    </p>
</div>
""", unsafe_allow_html=True)

        # Banner CTA: sólo visible cuando ambos archivos están cargados
        if "datos_estudiante" in st.session_state:
            _ambos_listos = "aprobadas_historial" in st.session_state
            _desc_inicio = ("Historial y Kardex cargados — revisa el resumen del estudiante."
                            if _ambos_listos else
                            "Cuando hayas cargado los archivos, revisa la situación académica del estudiante.")
            st.markdown(f"""
<div class="nav-cta-banner" style="margin-top:20px;">
  <div class="nav-cta-label">✅ Siguiente paso</div>
  <div class="nav-cta-desc">{_desc_inicio}</div>
</div>""", unsafe_allow_html=True)
            st.markdown('<div class="nav-btn-attached">', unsafe_allow_html=True)
            if st.button(
                "🎓  Ver Situación Académica",
                type="primary",
                use_container_width=True,
                key="btn_next_historia",
            ):
                st.switch_page(st.Page(_pg_historia, title="Situación Académica", icon=":material/history_edu:"))
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="divider-label">Archivos que necesitas</div>', unsafe_allow_html=True)
        st.markdown("""
<div class="info-row">
  <div class="info-chip">
    <strong>Historial académico</strong>
    PDF oficial del historial académico del estudiante exportado desde el sistema escolar.
  </div>
  <div class="info-chip">
    <strong>Kardex del estudiante</strong>
    PDF oficial con promedio, créditos y situación académica actualizada.
  </div>
  <div class="info-chip">
    <strong>Plan de estudios</strong>
    El sistema trabaja con el plan <strong>IDeIO 2021</strong>. Verifica que ambos documentos
    correspondan a ese plan.
  </div>
</div>
""", unsafe_allow_html=True)

        st.markdown('<div class="divider-label">Para comenzar, sigue estos pasos</div>', unsafe_allow_html=True)
        st.markdown("""
<div class="step-grid">

  <div class="step-card">
    <span class="step-number">Paso 1</span>
    <h3>Cargar el Historial Académico</h3>
    <p>En el panel izquierdo, sube el <strong>PDF del historial académico</strong> del estudiante.
    El sistema extrae las materias cursadas, calificaciones y semestres.</p>
    <div class="step-hint">Panel izquierdo &rarr; Paso 1: Historial Académico</div>
  </div>

  <div class="step-card">
    <span class="step-number">Paso 2</span>
    <h3>Cargar el Kardex</h3>
    <p>Sube el <strong>PDF del kardex</strong> del estudiante. El sistema extrae automáticamente
    los créditos, promedio, situación académica y datos del plan de estudios.</p>
    <div class="step-hint">Panel izquierdo &rarr; Paso 2: Kardex (PDF)</div>
  </div>

  <div class="step-card">
    <span class="step-number">Paso 3</span>
    <h3>Revisar la Situación Académica</h3>
    <p>Consulta el resumen del estudiante: alertas activas, créditos acumulados,
    índice de reprobación y proyección de egreso.</p>
    <div class="step-hint">Menú &rarr; Situación Académica</div>
  </div>

  <div class="step-card">
    <span class="step-number">Paso 4</span>
    <h3>Ver Materias Candidatas</h3>
    <p>El sistema experto analiza las seriaciones, prioridades y especialidad elegida
    para sugerir las materias más adecuadas a inscribir el próximo semestre.</p>
    <div class="step-hint">Menú &rarr; Materias Candidatas para Cargar</div>
  </div>

  <div class="step-card">
    <span class="step-number">Paso 5</span>
    <h3>Generar Combinaciones de Carga</h3>
    <p>Con la oferta académica disponible y tu horario libre, el generador propone
    hasta tres combinaciones sin choques de horario, ordenadas por prioridad.</p>
    <div class="step-hint">Menú &rarr; Generador de Cargas</div>
  </div>

  <div class="step-card">
    <span class="step-number">Opcional</span>
    <h3>Explorar el Mapa Curricular</h3>
    <p>Visualiza el avance del estudiante sobre el mapa oficial del plan 2021ID,
    con estado por materia: aprobada, pendiente, en curso o reprobada.</p>
    <div class="step-hint">Menú &rarr; Mapa Curricular</div>
  </div>

</div>
""", unsafe_allow_html=True)

        st.info(
            "Si tienes dudas mientras usas el sistema, el asistente de chat (esquina inferior derecha) "
            "puede responder preguntas sobre cualquier sección.",
            icon=":material/help:",
        )

    # Verificar si hay datos — mostrar sólo la bienvenida si aún no se cargaron archivos
    if "datos_estudiante" not in st.session_state:
        pg = st.navigation([
            st.Page(_pg_inicio, title="Cómo usar el sistema", icon=":material/home:", default=True),
        ], position="sidebar")
        pg.run()
        _render_agente_chat()
        return

    datos = st.session_state.datos_estudiante
    historial_df = st.session_state.historial_df

    # Datos compartidos entre pestañas
    mapa_curricular = cargar_mapa_curricular()
    # Normalizar: si es dict {clave: info}, convertir a lista de dicts
    if isinstance(mapa_curricular, dict):
        mapa_curricular = [
            {**info, "clave": str(clave).strip().upper()}
            for clave, info in mapa_curricular.items()
            if isinstance(info, dict)
        ]
    processor = AcademicProcessor(mapa_curricular)
    historial_df = normalizar_ultima_carga(historial_df)
    historial_filtrado = filtrar_ultimo_estatus(historial_df)
    historial_filtrado = marcar_recursando(historial_filtrado, historial_df)

    # ── Modo simulación: el semestre actual aún NO ha comenzado ──
    # EN_CURSO (primer intento) → se elimina (aún no cursada)
    # RECURSANDO (vor reprobación)  → se cambia a REPROBADA
    historial_calculo = historial_filtrado.copy()
    historial_calculo.loc[historial_calculo["estatus"] == "RECURSANDO", "estatus"] = "REPROBADA"
    historial_calculo = historial_calculo[
        historial_calculo["estatus"] != "EN_CURSO"
    ].reset_index(drop=True)
    # Almacenar para el agente IA
    st.session_state.historial_calculo = historial_calculo

    # Sobrescribir ciclos usando el mapa oficial (semestres 1-8) para todos los DataFrames.
    # Así se garantiza que historial_df y historial_filtrado usen semestres aunque
    # el kardex o historial parser hayan asignado ciclos anuales.
    _mapa_ciclos = {m.get("clave", ""): m.get("ciclo", None) for m in mapa_curricular}

    def _ciclo_oficial(clave):
        c = _mapa_ciclos.get(str(clave).strip().upper())
        return int(c) if c is not None else None

    for _df in (historial_df, historial_filtrado):
        if "clave" not in _df.columns:
            continue
        _override = _df["clave"].apply(_ciclo_oficial)
        _df["ciclo"] = _override.combine_first(_df["ciclo"].astype("float64")).astype("Int64")

    info_sabaticos = detectar_sabaticos(historial_df)

    creditos_totales = st.session_state.get("creditos_totales", 404)
    creditos_acumulados = st.session_state.get("creditos_acumulados", datos.total_creditos)
    creditos_faltantes = max(0, creditos_totales - creditos_acumulados)

    # ── Pre-calcular datos para el agente ──
    try:
        _el_info, _pre_tit, _pre_count = calcular_eleccion_libre(historial_calculo, mapa_curricular)
        st.session_state.eleccion_libre_info = {
            "ciclos": _el_info,
            "pre_titulacion": _pre_tit,
            "pre_count": _pre_count,
        }
    except Exception:
        pass
    try:
        _preesp = calcular_progreso_preespecialidades(historial_calculo, mapa_curricular)
        st.session_state.preespecialidades_info = _preesp
    except Exception:
        pass

    # ========== PÁGINAS PRINCIPALES (navegación en sidebar) ==========

    def _pg_historia():
        st.title("Situación Académica")
        st.caption("Usa las pestañas inferiores para navegar el historial académico y su progreso.")
        tab1, tab2, tab3, tab4 = st.tabs([
            "📋 Resumen General",
            "📈 Progreso",
            "📚 Elección Libre y Adicionales",
            "🎓 Pre-Especialidades",
        ])

        with tab1:
            st.header(f"👤 {datos.nombre}  —  {datos.matricula}")

            # Alerta si el estatus NO es Regular
            if datos.situacion.upper() != "REGULAR":
                st.markdown(f"""
                <div class='alerta-estatus'>
                    ⚠️ ATENCIÓN: ESTATUS ACADÉMICO - {datos.situacion.upper()} ⚠️
                </div>
                """, unsafe_allow_html=True)

            # Métricas principales
            _mat_reprobadas = (historial_calculo["estatus"] == "REPROBADA").sum()
            _mat_cursadas = historial_calculo["estatus"].isin(["APROBADA", "REPROBADA"]).sum()
            _indice_reprobacion = (_mat_reprobadas / _mat_cursadas * 100) if _mat_cursadas > 0 else 0.0

            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Plan de Estudios", datos.plan_estudios)
            with col2:
                _pct_cred = (creditos_acumulados / creditos_totales * 100) if creditos_totales > 0 else 0
                st.metric("Créditos", f"{creditos_acumulados}/{creditos_totales}",
                         delta=f"{_pct_cred:.1f}% completado")
            with col3:
                st.metric("Promedio General", f"{datos.promedio_general:.2f}")
            with col4:
                if datos.situacion.upper() == "REGULAR":
                    st.metric("Situación", datos.situacion)
                else:
                    st.metric("Índice de Reprobación", f"{_indice_reprobacion:.1f}%",
                             help=f"{_mat_reprobadas} reprobadas / {_mat_cursadas} cursadas")
            with col5:
                if datos.situacion.upper() == "REGULAR":
                    st.metric("Índice de Reprobación", f"{_indice_reprobacion:.1f}%",
                             help=f"{_mat_reprobadas} reprobadas / {_mat_cursadas} cursadas")
                else:
                    st.metric("Materias reprobadas", int(_mat_reprobadas))

            # ── Semestres sabáticos ──
            if info_sabaticos["cantidad"] > 0:
                st.markdown("---")
                _n_sab = info_sabaticos["cantidad"]
                _rest = info_sabaticos["restantes"]
                _color_sab = "#e67e22" if _rest > 0 else "#e74c3c"
                st.markdown(
                    f'<div style="background:#fff8e1;border-left:4px solid {_color_sab};'
                    f'padding:15px;margin:10px 0;border-radius:5px;color:#000;">'
                    f'<strong>Semestres sab\u00e1ticos detectados: {_n_sab} de 3 permitidos</strong><br>'
                    f'Semestres activos cursados: {info_sabaticos["semestres_activos"]}'
                    f' &nbsp;|&nbsp; Restantes disponibles: {_rest}'
                    f' &nbsp;|&nbsp; Tiempo m\u00e1ximo ajustado: {info_sabaticos["tiempo_max_años"]:.1f} a\u00f1os'
                    f' ({info_sabaticos["semestres_max"]} semestres)'
                    f'</div>',
                    unsafe_allow_html=True
                )
                with st.expander("Ver detalle de semestres sabáticos"):
                    _sab_rows = []
                    for p in info_sabaticos["sabaticos"]:
                        _año = p[:4]
                        _suf = p[4:]
                        _temp = {"01": "Primavera", "03": "Otoño"}.get(_suf, p[4:])
                        _sab_rows.append({"Periodo": p, "Temporada": f"{_temp} {_año}"})
                    st.dataframe(pd.DataFrame(_sab_rows), use_container_width=True, hide_index=True)

                    if info_sabaticos["periodos_vacaciones"]:
                        st.caption("Periodos de vacaciones (verano/invierno) donde cursó materias:")
                        _vac_rows = []
                        for p in info_sabaticos["periodos_vacaciones"]:
                            _año = p[:4]
                            _suf = p[4:]
                            _temp = {"02": "Verano", "04": "Invierno"}.get(_suf, p[4:])
                            _vac_rows.append({"Periodo": p, "Temporada": f"{_temp} {_año}"})
                        st.dataframe(pd.DataFrame(_vac_rows), use_container_width=True, hide_index=True)

            # ── Barra de progreso general ──
            st.markdown("---")
            st.subheader("📊 Progreso de la Carrera")

            porcentaje_creditos = (creditos_acumulados / creditos_totales * 100) if creditos_totales > 0 else 0

            ciclos_cursados = sorted(set(historial_df['ciclo'].dropna().astype(int))) if 'ciclo' in historial_df.columns else []
            ciclos_unicos = len(ciclos_cursados)

            from datetime import datetime as _dt
            años_aprox = 0
            semestre_actual = 1
            _num_sabaticos = info_sabaticos["cantidad"]
            _max_semestres = info_sabaticos["semestres_max"]      # 16 + sabáticos (máx 3)
            _max_años = info_sabaticos["tiempo_max_años"]          # 8 + 0.5 * sabáticos
            semestre_calendario = 1
            try:
                matricula_str = datos.matricula.strip()
                if len(matricula_str) >= 2:
                    año_entrada = 2000 + int(matricula_str[:2])
                    _inicio = _dt(año_entrada, 8, 1)
                    _hoy = _dt.now()
                    _meses = (_hoy.year - _inicio.year) * 12 + (_hoy.month - _inicio.month)
                    _meses = max(0, _meses)
                    semestre_calendario = max(1, (_meses // 6) + 1)
                    semestre_actual = max(1, semestre_calendario - _num_sabaticos)
                    años_aprox = round(_meses / 12, 1)
            except Exception:
                semestre_actual = max(1, ciclos_unicos * 2)
                semestre_calendario = semestre_actual + _num_sabaticos

            # Ritmo basado en semestres activos (sin sabáticos)
            _ritmo = creditos_acumulados / semestre_actual if semestre_actual > 0 else 0
            _sem_activos_proy = (creditos_totales / _ritmo) if _ritmo > 0 else 999
            _sem_proyectados = _sem_activos_proy + _num_sabaticos  # proyección calendario

            if semestre_calendario >= _max_semestres and creditos_acumulados < creditos_totales:
                _color_ritmo = "#7b0000"
                _etiqueta_ritmo = (
                    f"&#x26A0; CR&Iacute;TICO TOTAL &mdash; l&iacute;mite de {_max_semestres} semestres alcanzado"
                )
            elif _sem_proyectados <= _max_semestres * 0.5625:
                _color_ritmo = "#27ae60"
                _etiqueta_ritmo = "En tiempo"
            elif _sem_proyectados <= _max_semestres * 0.6875:
                _color_ritmo = "#a8e063"
                _etiqueta_ritmo = "Leve retraso"
            elif _sem_proyectados <= _max_semestres * 0.8125:
                _color_ritmo = "#fdcb6e"
                _etiqueta_ritmo = "Retraso moderado"
            elif _sem_proyectados < _max_semestres:
                _color_ritmo = "#e17055"
                _etiqueta_ritmo = "Retraso grave"
            else:
                _color_ritmo = "#d63031"
                _etiqueta_ritmo = (
                    f"CR&Iacute;TICO &mdash; proyecci&oacute;n supera el l&iacute;mite de {_max_semestres} semestres"
                )

            _fill_pct = min(porcentaje_creditos, 100.0)
            _inner = (
                f'<div style="width:{_fill_pct:.2f}%;height:100%;background:{_color_ritmo};'
                f'position:absolute;left:0;top:0;border-radius:6px 0 0 6px;"></div>'
                '<div style="position:absolute;left:25%;top:0;width:2px;height:100%;'
                'background:rgba(255,255,255,0.7);z-index:2;"></div>'
                '<div style="position:absolute;left:50%;top:0;width:2px;height:100%;'
                'background:rgba(255,255,255,0.7);z-index:2;"></div>'
                '<div style="position:absolute;left:75%;top:0;width:2px;height:100%;'
                'background:rgba(255,255,255,0.7);z-index:2;"></div>'
                f'<div style="position:absolute;top:0;left:0;width:100%;height:100%;'
                f'display:flex;align-items:center;justify-content:center;z-index:3;pointer-events:none;">'
                f'<span style="font-size:22px;font-weight:800;color:#fff;'
                f'text-shadow:0 1px 4px rgba(0,0,0,0.45);">{_fill_pct:.1f}%</span>'
                f'</div>'
            )

            _ritmo_fmt = f"{_ritmo:.1f}" if _ritmo > 0 else "—"
            if _sem_proyectados >= 999:
                _sem_proy_fmt = "N/A"
            elif _sem_proyectados > _max_semestres:
                _sem_proy_fmt = f"<span style='color:#d63031;font-weight:700;'>L&iacute;mite alcanzado</span>"
            else:
                _sem_proy_fmt = f"{_sem_proyectados:.0f}"
            _sab_badge = ""
            if _num_sabaticos > 0:
                _sab_badge = (
                    f' &nbsp;|&nbsp; <span style="color:#e67e22;">Sab\u00e1ticos: {_num_sabaticos}/3'
                    f' &nbsp;&bull;&nbsp; L\u00edmite: {_max_años:.1f} a\u00f1os ({_max_semestres} sem)</span>'
                )
            _barra_html = (
                '<div style="background:#f7f7f7;border:1.5px solid #d0d0d0;border-radius:10px;'
                'padding:12px 14px;margin-bottom:8px;">'
                '<div style="font-size:13px;color:#555;margin-bottom:8px;font-weight:600;">'
                f'Progreso general'
                f' &nbsp;|&nbsp; {creditos_acumulados}/{creditos_totales} cr\u00e9ditos'
                f' &nbsp;|&nbsp; Sem. activo {semestre_actual} ({años_aprox} a\u00f1os)'
                f' &nbsp;|&nbsp; Ritmo: {_ritmo_fmt} cr/sem &nbsp;&bull;&nbsp; Proyecci\u00f3n: {_sem_proy_fmt} sem'
                f'{_sab_badge}'
                '</div>'
                '<div style="position:relative;width:100%;height:72px;background:#e0e0e0;'
                'border-radius:6px;overflow:hidden;">'
                f'{_inner}'
                '</div>'
                '<div style="font-size:14px;color:#888;margin-top:8px;">'
                f'Ritmo actual: <span style="color:{_color_ritmo};font-weight:bold;">&#9632;</span>'
                f' {_etiqueta_ritmo} &nbsp;&mdash;&nbsp;'
                'Referencias: '
                '<span style="color:#27ae60;font-weight:bold;">&#9632;</span> &le;4.5 a&ntilde;os &nbsp;'
                '<span style="color:#a8e063;font-weight:bold;">&#9632;</span> 4.5-5.5 &nbsp;'
                '<span style="color:#fdcb6e;font-weight:bold;">&#9632;</span> 5.5-6.5 &nbsp;'
                '<span style="color:#e17055;font-weight:bold;">&#9632;</span> 6.5-8 &nbsp;'
                f'<span style="color:#d63031;font-weight:bold;">&#9632;</span> &ge;{_max_semestres} sem &nbsp;'
                '<span style="color:#7b0000;font-weight:bold;">&#9632;</span> L&iacute;mite alcanzado'
                '</div></div>'
            )
            st.markdown(_barra_html, unsafe_allow_html=True)

            # ── Alertas académicas ──
            st.markdown("---")
            st.subheader("⚠️ Alertas Académicas")

            try:
                alertas = processor.identificar_alertas(historial_df, datos.situacion)
                st.session_state.alertas_academicas = alertas

                import re as _re_alerta

                _TIPO_LABEL = {
                    "BAJA_AUTOMÁTICA":      ("Materias con riesgo de baja automática",      "CRITICA"),
                    "TERCERA_OPORTUNIDAD":  ("Materias en tercera oportunidad",              "CRITICA"),
                    "ALUMNO_IRREGULAR":     ("Situación académica irregular",                "ADVERTENCIA"),
                    "MATERIAS_REPROBADAS":  ("Materias pendientes de regularizar",           "ADVERTENCIA"),
                    "ATRASO_PRÁCTICAS_I":   ("Atraso en Prácticas Profesionales I",          "ADVERTENCIA"),
                    "ATRASO_PRÁCTICAS_II":  ("Atraso en Prácticas Profesionales II",         "ADVERTENCIA"),
                    "PREREQUISITO_SALTADO": ("Prerrequisitos sin acreditar",                 "ADVERTENCIA"),
                }

                def _clave_chip(clave):
                    return (f"<span style='font-family:monospace;font-size:12px;"
                            f"background:#eef0f4;padding:1px 6px;border-radius:3px;'>{clave}</span>")

                def _bullet_list(items_html):
                    rows = "".join(f"<li style='margin:4px 0;'>{it}</li>" for it in items_html)
                    return f"<ul style='margin:6px 0 2px 16px;padding:0;list-style:disc;'>{rows}</ul>"

                def _highlight_inline(text):
                    """Resalta pares CLAVE - Nombre en texto plano."""
                    return _re_alerta.sub(
                        r'([A-Z]{2,}\d{3,}) - ([^.,;(<\n]+)',
                        lambda m: f"{_clave_chip(m.group(1))} <strong>{m.group(2).strip()}</strong>",
                        text,
                    )

                def _render_card(label, sev, body_html):
                    bg     = "#fff5f5" if sev == "CRITICA" else "#fffbf0"
                    border = "#dc3545" if sev == "CRITICA" else "#c0842a"
                    st.markdown(
                        f"<div style='background:{bg};border-left:4px solid {border};"
                        f"border-radius:6px;padding:12px 16px;margin:8px 0;'>"
                        f"<div style='font-size:13px;font-weight:700;color:{border};"
                        f"margin-bottom:5px;letter-spacing:.01em;'>{label}</div>"
                        f"<div style='font-size:13px;color:#333;line-height:1.65;'>{body_html}</div>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                # ── Agrupar alertas por tipo ──────────────────────────────────
                from collections import OrderedDict as _OD
                grupos = _OD()
                for _a in alertas:
                    _t = _a.get("tipo", "OTRO")
                    grupos.setdefault(_t, []).append(_a)

                if alertas:
                    for tipo, grupo in grupos.items():
                        label_def, sev_def = _TIPO_LABEL.get(tipo, ("Alerta académica", "ADVERTENCIA"))
                        # Tomar severidad máxima del grupo
                        sev = "CRITICA" if any(a.get("severidad") == "CRITICA" for a in grupo) else sev_def

                        # ── Tipos que se agrupan en lista ──────────────────────
                        if tipo in ("BAJA_AUTOMÁTICA", "TERCERA_OPORTUNIDAD"):
                            items = []
                            for _a in grupo:
                                _d = _a.get("descripcion", "").replace("⚠️ CRÍTICO: ", "").replace("⚠️ ", "")
                                # Extraer "CLAVE - Nombre (detalle)" de la descripción
                                _m = _re_alerta.search(r'materia ([A-Z]{2,}\d{3,}) - ([^(]+)\(([^)]+)\)', _d)
                                if _m:
                                    items.append(
                                        f"{_clave_chip(_m.group(1))} <strong>{_m.group(2).strip()}</strong>"
                                        f" <span style='color:#666;font-size:12px;'>({_m.group(3).strip()})</span>"
                                    )
                                else:
                                    items.append(_highlight_inline(_d))
                            body = _bullet_list(items) if len(items) > 1 else _highlight_inline(
                                grupo[0].get("descripcion","").replace("⚠️ CRÍTICO: ","").replace("⚠️ ","")
                            )
                            _render_card(label_def, sev, body)

                        elif tipo == "PREREQUISITO_SALTADO":
                            items = []
                            for _a in grupo:
                                _d = _a.get("descripcion", "")
                                # Patrón: "aprobó CLAVE1 - Nombre1 sin haber aprobado su prerequisito CLAVE2 - Nombre2."
                                _m = _re_alerta.search(
                                    r'aprobó ([A-Z]{2,}\d{3,}) - ([^s]+?) sin haber aprobado su prerequisito ([A-Z]{2,}\d{3,}) - ([^.]+)',
                                    _d
                                )
                                if _m:
                                    items.append(
                                        f"{_clave_chip(_m.group(1))} <strong>{_m.group(2).strip()}</strong>"
                                        f" &nbsp;→&nbsp; falta prerrequisito: "
                                        f"{_clave_chip(_m.group(3))} <strong>{_m.group(4).strip()}</strong>"
                                    )
                                else:
                                    items.append(_highlight_inline(_d))
                            intro = "Se detectaron materias aprobadas sin acreditar sus prerrequisitos. Verificar con coordinación académica:"
                            body  = intro + _bullet_list(items)
                            _render_card(label_def, sev, body)

                        elif tipo in ("ALUMNO_IRREGULAR", "MATERIAS_REPROBADAS"):
                            # Ya traen lista con ";" internamente — usar primera descripción
                            _d = grupo[0].get("descripcion", "").replace("⚠️ ", "")
                            if ";" in _d and ":" in _d:
                                idx   = _d.index(":")
                                intro = _d[:idx + 1].strip()
                                items = [i.strip() for i in _d[idx + 1:].split(";") if i.strip()]
                                def _fmt(item):
                                    parts = item.split(" - ", 1)
                                    if len(parts) == 2:
                                        return (f"{_clave_chip(parts[0].strip())} "
                                                f"<strong>{parts[1].strip()}</strong>")
                                    return item
                                body = intro + _bullet_list([_fmt(i) for i in items])
                            else:
                                body = _highlight_inline(_d)
                            _render_card(label_def, sev, body)

                        else:
                            # Tipos únicos (atrasos, etc.) — renderizar tal cual
                            _d = grupo[0].get("descripcion", "").replace("⚠️ CRÍTICO: ","").replace("⚠️ ","")
                            _render_card(label_def, sev, _highlight_inline(_d))
                else:
                    st.success("Sin alertas académicas. Todo en orden.")
            except Exception as e:
                st.warning(f"Error al calcular alertas: {str(e)}")

        # ===================================================================
        # PESTAÑA 2: PROGRESO
        # ===================================================================
        with tab2:
            st.header("📈 Progreso Académico")
            _vista_progreso = st.selectbox(
                "Ver progreso por:",
                ["Ciclo", "Semestre"],
                key="sel_vista_progreso"
            )

            if _vista_progreso == "Ciclo":

                try:
                    progreso_ciclos = processor.calcular_progreso_por_ciclo(historial_calculo)
                    materias_por_estatus = obtener_materias_por_estatus_ciclo(historial_calculo, mapa_curricular)

                    def _agrupar_ciclos_anuales(progreso_ciclos, sems):
                        """Suma los ProgresoCiclo de los semestres indicados."""
                        fin = en_c = rec = rep = pend = tot = 0
                        for s in sems:
                            if s in progreso_ciclos:
                                p = progreso_ciclos[s]
                                fin  += p.finalizadas
                                en_c += p.en_curso
                                rec  += p.recursando
                                rep  += p.reprobadas
                                pend += p.pendientes
                                tot  += p.total
                        pct = (fin / tot * 100) if tot > 0 else 0
                        return {"finalizadas": fin, "en_curso": en_c, "recursando": rec,
                                "reprobadas": rep, "pendientes": pend, "total": tot, "porcentaje": pct}

                    grupos_anuales = [
                        ("Ciclo 1", [1, 2]),
                        ("Ciclo 2", [3, 4]),
                        ("Ciclo 3 y 4", [5, 6, 7, 8]),
                    ]

                    cols_ca = st.columns(3)
                    for col, (nombre_ca, sems_ca) in zip(cols_ca, grupos_anuales):
                        datos_ca = _agrupar_ciclos_anuales(progreso_ciclos, sems_ca)
                        with col:
                            st.subheader(nombre_ca)
                            fig_ca = go.Figure(data=[go.Pie(
                                labels=["Finalizadas", "En Curso", "Recursando", "Reprobadas", "Pendientes"],
                                values=[datos_ca["finalizadas"], datos_ca["en_curso"],
                                        datos_ca["recursando"], datos_ca["reprobadas"], datos_ca["pendientes"]],
                                marker=dict(colors=["#28a745", "#ffc107", "#ff8c00", "#dc3545", "#6c757d"]),
                                hole=0.45,
                                textinfo="none",
                            )])
                            fig_ca.update_layout(showlegend=True, height=380,
                                                 margin=dict(t=30, b=10, l=10, r=10))
                            st.plotly_chart(fig_ca, use_container_width=True)
                            total_ca = datos_ca["total"]
                            lineas_ca = [f"<strong>{datos_ca['porcentaje']:.1f}% Completado</strong>",
                                         f"✅ Finalizadas: {datos_ca['finalizadas']}/{total_ca}",
                                         f"⏳ En Curso: {datos_ca['en_curso']}/{total_ca}"]
                            if datos_ca["recursando"] > 0:
                                lineas_ca.append(f"🟠 Recursando: {datos_ca['recursando']}/{total_ca}")
                            lineas_ca.append(f"❌ Reprobadas: {datos_ca['reprobadas']}/{total_ca}")
                            lineas_ca.append(f"⚪ Pendientes: {datos_ca['pendientes']}/{total_ca}")
                            st.markdown(f"<div class='metric-box'>{'<br>'.join(lineas_ca)}</div>",
                                        unsafe_allow_html=True)

                            # Lista de materias por segmento del ciclo anual
                            _mat_ca = {}
                            for _s in ["Finalizadas", "En Curso", "Recursando", "Reprobadas", "Pendientes"]:
                                _mat_ca[_s] = sum([materias_por_estatus.get(s, {}).get(_s, []) for s in sems_ca], [])
                            _opc_ca = [s for s in ["Finalizadas", "En Curso", "Recursando", "Reprobadas", "Pendientes"] if _mat_ca.get(s)]
                            if _opc_ca:
                                _total_ca = sum(len(_mat_ca[s]) for s in _opc_ca)
                                with st.expander(f"Ver materias ({_total_ca})"):
                                    _sel_ca = st.selectbox(
                                        "Filtrar por:", _opc_ca,
                                        key=f"sel_ca_{'_'.join(map(str, sems_ca))}"
                                    )
                                    st.dataframe(
                                        pd.DataFrame(_mat_ca[_sel_ca]),
                                        use_container_width=True, hide_index=True
                                    )

                except Exception as e:
                    st.warning(f"Error al calcular progreso por ciclo anual: {str(e)}")

            else:  # Semestre
                try:
                    progreso_ciclos = processor.calcular_progreso_por_ciclo(historial_calculo)
                    materias_por_estatus = obtener_materias_por_estatus_ciclo(historial_calculo, mapa_curricular)
                    ciclos_validos = sorted(c for c in progreso_ciclos.keys() if 1 <= c <= 8)

                    if ciclos_validos:
                        st.caption("**Semestres 1–4**")
                        cols_fila1 = st.columns(4)
                        for i, ciclo in enumerate(range(1, 5)):
                            with cols_fila1[i]:
                                if ciclo in progreso_ciclos:
                                    progreso = progreso_ciclos[ciclo]
                                    fig = crear_grafica_progreso_ciclo(ciclo, {
                                        "finalizadas": progreso.finalizadas,
                                        "en_curso": progreso.en_curso,
                                        "recursando": progreso.recursando,
                                        "reprobadas": progreso.reprobadas,
                                        "pendientes": progreso.pendientes
                                    })
                                    st.plotly_chart(fig, use_container_width=True)
                                    total_sem = progreso.total
                                    lineas = [
                                        f"<strong>{progreso.porcentaje:.1f}% Completado</strong>",
                                        f"✅ Finalizadas: {progreso.finalizadas}/{total_sem}",
                                        f"⏳ En Curso: {progreso.en_curso}/{total_sem}",
                                    ]
                                    if progreso.recursando > 0:
                                        lineas.append(f"🟠 Recursando: {progreso.recursando}/{total_sem}")
                                    lineas.append(f"❌ Reprobadas: {progreso.reprobadas}/{total_sem}")
                                    lineas.append(f"⚪ Pendientes: {progreso.pendientes}/{total_sem}")
                                    st.markdown(f"<div class='metric-box'>{'<br>'.join(lineas)}</div>",
                                                unsafe_allow_html=True)

                                    _mat_sem = materias_por_estatus.get(ciclo, {})
                                    _opc_sem = [s for s in ["Finalizadas", "En Curso", "Recursando", "Reprobadas", "Pendientes"] if _mat_sem.get(s)]
                                    if _opc_sem:
                                        _total_sem = sum(len(_mat_sem[s]) for s in _opc_sem)
                                        with st.expander(f"Ver materias ({_total_sem})"):
                                            _sel_sem = st.selectbox("Filtrar por:", _opc_sem, key=f"sel_sem_{ciclo}")
                                            st.dataframe(pd.DataFrame(_mat_sem[_sel_sem]), use_container_width=True, hide_index=True)
                                else:
                                    st.info(f"Sem. {ciclo}: Sin datos")

                        st.markdown("---")
                        st.caption("**Semestres 5–8**")
                        cols_fila2 = st.columns(4)
                        for i, ciclo in enumerate(range(5, 9)):
                            with cols_fila2[i]:
                                if ciclo in progreso_ciclos:
                                    progreso = progreso_ciclos[ciclo]
                                    fig = crear_grafica_progreso_ciclo(ciclo, {
                                        "finalizadas": progreso.finalizadas,
                                        "en_curso": progreso.en_curso,
                                        "recursando": progreso.recursando,
                                        "reprobadas": progreso.reprobadas,
                                        "pendientes": progreso.pendientes
                                    })
                                    st.plotly_chart(fig, use_container_width=True)
                                    total_sem = progreso.total
                                    lineas = [
                                        f"<strong>{progreso.porcentaje:.1f}% Completado</strong>",
                                        f"✅ Finalizadas: {progreso.finalizadas}/{total_sem}",
                                        f"⏳ En Curso: {progreso.en_curso}/{total_sem}",
                                    ]
                                    if progreso.recursando > 0:
                                        lineas.append(f"🟠 Recursando: {progreso.recursando}/{total_sem}")
                                    lineas.append(f"❌ Reprobadas: {progreso.reprobadas}/{total_sem}")
                                    lineas.append(f"⚪ Pendientes: {progreso.pendientes}/{total_sem}")
                                    st.markdown(f"<div class='metric-box'>{'<br>'.join(lineas)}</div>",
                                                unsafe_allow_html=True)

                                    _mat_sem2 = materias_por_estatus.get(ciclo, {})
                                    _opc_sem2 = [s for s in ["Finalizadas", "En Curso", "Recursando", "Reprobadas", "Pendientes"] if _mat_sem2.get(s)]
                                    if _opc_sem2:
                                        _total_sem2 = sum(len(_mat_sem2[s]) for s in _opc_sem2)
                                        with st.expander(f"Ver materias ({_total_sem2})"):
                                            _sel_sem2 = st.selectbox("Filtrar por:", _opc_sem2, key=f"sel_sem2_{ciclo}")
                                            st.dataframe(pd.DataFrame(_mat_sem2[_sel_sem2]), use_container_width=True, hide_index=True)
                                else:
                                    st.info(f"Sem. {ciclo}: Sin datos")
                    else:
                        st.info("No hay datos de progreso por semestre.")
                except Exception as e:
                    st.warning(f"Error al calcular progreso por semestre: {str(e)}")

            # ── Tabla de historial por ciclo ──
            st.markdown("---")
            st.subheader("📚 Historial Académico por Ciclo")

            if historial_df.empty or "periodo" not in historial_df.columns:
                st.warning("⚠️ No se encontraron materias en el PDF. Verifica que el formato del kardex sea compatible.")
            else:
                estatus_color = {
                    "APROBADA": "🟢",
                    "REPROBADA": "🔴",
                    "EN_CURSO": "🟡",
                    "RECURSANDO": "🟠",
                    "SIN_REGISTRAR": "⚪"
                }

                conteo_materias = historial_df.groupby("clave").size().to_dict()
                historial_limpio = historial_calculo.copy()
                historial_limpio["intentos"] = historial_limpio["clave"].map(conteo_materias)
                historial_limpio = historial_limpio.sort_values(["periodo"], ascending=False)

                def crear_badge_intento(row):
                    intentos = row["intentos"]
                    if intentos >= 3:
                        return " 🔴 3ª VEZ"
                    elif intentos == 2:
                        return " 🟡 2ª VEZ"
                    return ""

                historial_limpio["badge_intento"] = historial_limpio.apply(crear_badge_intento, axis=1)

                if "ciclo" in historial_limpio.columns:
                    grupos = historial_limpio.sort_values(["ciclo", "clave"]).groupby("ciclo", sort=True)
                else:
                    grupos = historial_limpio.sort_values(["periodo", "clave"]).groupby("periodo", sort=True)

                for grupo_key, grupo_df in grupos:
                    ciclo_num = int(grupo_key) if "ciclo" in historial_limpio.columns else 0
                    nombre_ciclo = NOMBRES_CICLO.get(ciclo_num, f"Ciclo {ciclo_num}")
                    expandir = ciclo_num == 1

                    grupo_df_unico = grupo_df.drop_duplicates(subset=["clave"], keep="first")
                    aprobadas = (grupo_df_unico["estatus"] == "APROBADA").sum()
                    total = len(grupo_df_unico)
                    creditos = grupo_df_unico[grupo_df_unico["estatus"] == "APROBADA"]["creditos"].sum()

                    with st.expander(f"📅 {nombre_ciclo}  |  {aprobadas}/{total} aprobadas  |  {creditos} créditos", expanded=expandir):
                        display_df = grupo_df_unico[["clave", "nombre", "calificacion", "creditos", "estatus", "badge_intento"]].copy()
                        display_df["calificacion"] = display_df["calificacion"].apply(
                            lambda x: "S/A" if (x is None or (isinstance(x, float) and pd.isna(x))) else f"{x:.1f}" if isinstance(x, (int, float)) else str(x)
                        )
                        display_df["nombre"] = display_df["nombre"] + display_df["badge_intento"]
                        display_df["estatus"] = display_df["estatus"].map(lambda e: f"{estatus_color.get(e, '')} {e}")
                        display_df = display_df[["clave", "nombre", "calificacion", "creditos", "estatus"]]
                        display_df.columns = ["Clave", "Asignatura", "Calificación", "Créditos", "Estatus"]
                        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # ===================================================================
        # PESTAÑA 3: ELECCIÓN LIBRE Y ADICIONALES
        # ===================================================================
        with tab3:
            st.header("📚 Materias de Elección Libre")
            st.caption("Ciclo 1 y 2: 2 materias cada uno | Ciclos 3 y 4 combinados: 8 materias (incluye materias de pre-especialidad no usada)")

            try:
                eleccion_libre, pre_titulacion, pre_especialidades_count = calcular_eleccion_libre(historial_calculo, mapa_curricular)

                col_el1, col_el2, col_el3 = st.columns(3)

                with col_el1:
                    st.subheader("📘 Ciclo 1")
                    el1 = eleccion_libre[1]
                    progreso_el1 = (el1["aprobadas"] / el1["requeridas"] * 100) if el1["requeridas"] > 0 else 0
                    st.progress(min(progreso_el1 / 100, 1.0))
                    st.markdown(f"""
                    <div class='metric-box'>
                        <strong>{progreso_el1:.0f}% Completado</strong><br>
                        ✅ Aprobadas: {el1["aprobadas"]}/{el1["requeridas"]}<br>
                        ⏳ En Curso: {el1["en_curso"]}<br>
                        📚 Faltan: {max(0, el1["requeridas"] - el1["aprobadas"])} materias
                    </div>
                    """, unsafe_allow_html=True)
                    if el1["claves"]:
                        with st.expander(f"Ver materias ({len(el1['claves'])})"):
                            st.dataframe(pd.DataFrame({"Clave": el1["claves"], "Nombre": el1["nombres"]}), use_container_width=True, hide_index=True)

                with col_el2:
                    st.subheader("📗 Ciclo 2")
                    el2 = eleccion_libre[2]
                    progreso_el2 = (el2["aprobadas"] / el2["requeridas"] * 100) if el2["requeridas"] > 0 else 0
                    st.progress(min(progreso_el2 / 100, 1.0))
                    st.markdown(f"""
                    <div class='metric-box'>
                        <strong>{progreso_el2:.0f}% Completado</strong><br>
                        ✅ Aprobadas: {el2["aprobadas"]}/{el2["requeridas"]}<br>
                        ⏳ En Curso: {el2["en_curso"]}<br>
                        📚 Faltan: {max(0, el2["requeridas"] - el2["aprobadas"])} materias
                    </div>
                    """, unsafe_allow_html=True)
                    if el2["claves"]:
                        with st.expander(f"Ver materias ({len(el2['claves'])})"):
                            st.dataframe(pd.DataFrame({"Clave": el2["claves"], "Nombre": el2["nombres"]}), use_container_width=True, hide_index=True)

                with col_el3:
                    st.subheader("📙 Ciclos 3 y 4")
                    el34 = eleccion_libre["3_y_4"]
                    progreso_el34 = (el34["aprobadas"] / el34["requeridas"] * 100) if el34["requeridas"] > 0 else 0
                    st.progress(min(progreso_el34 / 100, 1.0))
                    st.markdown(f"""
                    <div class='metric-box'>
                        <strong>{progreso_el34:.0f}% Completado</strong><br>
                        ✅ Aprobadas: {el34["aprobadas"]}/{el34["requeridas"]}<br>
                        ⏳ En Curso: {el34["en_curso"]}<br>
                        📚 Faltan: {max(0, el34["requeridas"] - el34["aprobadas"])} materias<br>
                        <em style="font-size: 0.85em;">Pre-especialidad de titulación: {pre_titulacion}</em>
                    </div>
                    """, unsafe_allow_html=True)
                    if el34["claves"]:
                        with st.expander(f"Ver materias ({len(el34['claves'])})"):
                            st.dataframe(pd.DataFrame({"Clave": el34["claves"], "Nombre": el34["nombres"]}), use_container_width=True, hide_index=True)

                if pre_especialidades_count["IoN"] < 5 or pre_especialidades_count["ITIC"] < 5:
                    st.info("💡 **Consejo**: Materias de la pre-especialidad no completada pueden contar como elección libre en Ciclos 3 y 4")
                    with st.expander("Ver detalle de pre-especialidades y elección libre"):
                        col_info1, col_info2 = st.columns(2)
                        with col_info1:
                            st.markdown("**Inteligencia Organizacional y de Negocios (IoN)**")
                            st.markdown(f"✅ Aprobadas: {pre_especialidades_count['IoN']}/5")
                            if pre_titulacion == "ITIC" and pre_especialidades_count['IoN'] > 0:
                                st.success(f"Tienes {pre_especialidades_count['IoN']} materia(s) de IoN que cuentan como elección libre")
                        with col_info2:
                            st.markdown("**Innovación en TIC (ITIC)**")
                            st.markdown(f"✅ Aprobadas: {pre_especialidades_count['ITIC']}/5")
                            if pre_titulacion == "IoN" and pre_especialidades_count['ITIC'] > 0:
                                st.success(f"Tienes {pre_especialidades_count['ITIC']} materia(s) de ITIC que cuentan como elección libre")

                        faltan_el = max(0, el34["requeridas"] - el34["aprobadas"])
                        pre_no_usada = "IoN" if pre_titulacion == "ITIC" else "ITIC"
                        materias_pre_no_usada = 5 - pre_especialidades_count[pre_no_usada]
                        if faltan_el > 0 and materias_pre_no_usada > 0:
                            st.info(f"📊 Te faltan {faltan_el} materias de elección libre en Ciclos 3y4. Puedes tomar hasta {materias_pre_no_usada} materias de {pre_no_usada} que contarán como elección libre.")

            except Exception as e:
                st.warning(f"Error al calcular elección libre: {str(e)}")
                import traceback
                st.code(traceback.format_exc())

            # ── Requisitos adicionales ──
            st.markdown("---")
            st.subheader("📋 Requisitos Adicionales")

            try:
                ingles_ok = st.session_state.get("ingles_completo", False)
                requisitos = processor.calcular_requisitos(historial_calculo, ingles_completo=ingles_ok)
            except Exception:
                requisitos = {"Actividad Deportiva": False, "Actividad Cultural": False, "Inglés": False}

            col1, col2, col3 = st.columns(3)
            iconos = {True: "✅", False: "❌"}
            with col1:
                st.markdown(f"**{iconos[requisitos.get('Actividad Deportiva', False)]} Actividad Deportiva**")
            with col2:
                st.markdown(f"**{iconos[requisitos.get('Actividad Cultural', False)]} Actividad Cultural**")
            with col3:
                st.markdown(f"**{iconos[requisitos.get('Inglés', False)]} Inglés**")

            # ── Detalle de progreso de Inglés ──
            st.markdown("---")
            st.subheader("📖 Progreso de Inglés")

            # Cadena completa de inglés para mostrar progreso
            cadena_ingles_display = [
                {"nivel": 1, "nombre": "Nivel 1 Inglés", "codigos": ["LI1101"]},
                {"nivel": 2, "nombre": "Nivel 2 Inglés", "codigos": ["LI1102"]},
                {"nivel": 3, "nombre": "Nivel 3 Inglés", "codigos": ["LI1103"]},
                {"nivel": 4, "nombre": "Nivel 4 Inglés", "codigos": ["LI1104"]},
                {"nivel": 5, "nombre": "Tópicos Selectos I", "codigos": ["LI0109"]},
                {"nivel": 6, "nombre": "Tópicos Selectos II", "codigos": ["LI0110"]},
            ]

            nivel_historial = st.session_state.get("nivel_ingles_texto", "")
            # Usar el número de nivel directamente (guardado desde el parser, evita
            # problemas de codificación NFD/NFC al recomparar texto del PDF)
            nivel_num = st.session_state.get("nivel_ingles_aprobado", 0)

            # Buscar estado de cada nivel en el kardex
            ingles_rows = []
            for nivel_info in cadena_ingles_display:
                # Buscar en historial filtrado si alguno de los códigos existe
                estatus_nivel = "PENDIENTE"
                clave_encontrada = ""
                for codigo in nivel_info["codigos"]:
                    mask = historial_calculo["clave"] == codigo
                    if mask.any():
                        row = historial_calculo[mask].iloc[0]
                        estatus_nivel = row["estatus"]
                        clave_encontrada = codigo
                        break

                # Si no está en el kardex pero el historial dice que está aprobado
                if estatus_nivel == "PENDIENTE" and nivel_info["nivel"] <= nivel_num:
                    estatus_nivel = "APROBADA"
                    clave_encontrada = nivel_info["codigos"][0]

                if estatus_nivel == "APROBADA":
                    icono = "✅"
                elif estatus_nivel in ("EN_CURSO", "RECURSANDO"):
                    icono = "🟠" if estatus_nivel == "RECURSANDO" else "🟡"
                elif estatus_nivel == "REPROBADA":
                    icono = "🔴"
                else:
                    icono = "⚪"

                ingles_rows.append({
                    "Nivel": nivel_info["nivel"],
                    "Materia": nivel_info["nombre"],
                    "Clave": clave_encontrada if clave_encontrada else "-",
                    "Estado": f"{icono} {estatus_nivel}",
                })

            import pandas as _pd_ing
            df_ingles = _pd_ing.DataFrame(ingles_rows)
            st.dataframe(df_ingles, use_container_width=True, hide_index=True)

            # Resumen
            aprobados_count = sum(1 for r in ingles_rows if "APROBADA" in r["Estado"])
            en_curso_count = sum(1 for r in ingles_rows if "EN_CURSO" in r["Estado"] or "RECURSANDO" in r["Estado"])
            if nivel_historial:
                st.caption(f"📊 Último nivel aprobado según historial: **{nivel_historial}** ({aprobados_count}/6 niveles)")
            if ingles_ok:
                st.success("✅ Requisito de inglés completado (Tópicos 2 aprobado)")
            else:
                faltan = 6 - aprobados_count
                st.info(f"📚 Faltan {faltan} nivel(es) para completar el requisito de inglés (hasta Tópicos Selectos II)")

        # ===================================================================
        # PESTAÑA 4: PRE-ESPECIALIDADES
        # ===================================================================
        with tab4:
            st.header("🎓 Progreso en Pre-Especialidades")
            st.caption("Cada pre-especialidad requiere 5 materias para completarse. La pre-especialidad con más materias aprobadas será tu titulación.")

            try:
                preespecialidades = calcular_progreso_preespecialidades(historial_calculo, mapa_curricular)

                if preespecialidades:
                    cols_pre = st.columns(len(preespecialidades))
                    for idx, (nombre, datos_pre) in enumerate(preespecialidades.items()):
                        with cols_pre[idx]:
                            aprobadas = datos_pre["aprobadas"]
                            en_curso = datos_pre["en_curso"]
                            total_requerido = 5
                            porcentaje = (aprobadas / total_requerido * 100) if total_requerido > 0 else 0

                            if aprobadas >= 5:
                                color_badge = "🟢"
                                estado = "COMPLETADA"
                            elif aprobadas >= 3:
                                color_badge = "🟡"
                                estado = "EN PROGRESO"
                            else:
                                color_badge = "⚪"
                                estado = "INICIAL"

                            fig = go.Figure(data=[go.Pie(
                                labels=["Aprobadas", "En Curso", "Pendientes"],
                                values=[aprobadas, en_curso, max(0, total_requerido - aprobadas - en_curso)],
                                marker=dict(colors=["#28a745", "#ffc107", "#e0e0e0"]),
                                hole=0.5
                            )])
                            fig.update_layout(
                                title=f"{color_badge} {nombre}",
                                showlegend=True,
                                height=350
                            )
                            st.plotly_chart(fig, use_container_width=True)
                            st.markdown(f"""
                            <div class='metric-box'>
                                <strong>{porcentaje:.1f}% Completado</strong><br>
                                <strong>Estado: {estado}</strong><br>
                                ✅ Aprobadas: {aprobadas}/5<br>
                                ⏳ En Curso: {en_curso}<br>
                                📚 Faltan: {max(0, 5 - aprobadas)} materias
                            </div>
                            """, unsafe_allow_html=True)

                            # Lista de materias de esta pre-especialidad
                            if datos_pre.get("claves"):
                                _mapa_dict_pre = {str(m.get("clave", "")).upper(): m for m in mapa_curricular}
                                _status_pre = {}
                                for _, _r in historial_calculo.iterrows():
                                    _status_pre[str(_r.get("clave", "")).upper()] = _r.get("estatus", "")
                                _filas_pre = []
                                for _cl in datos_pre["claves"]:
                                    _mi = _mapa_dict_pre.get(_cl, {})
                                    _filas_pre.append({
                                        "Clave": _cl,
                                        "Nombre": _mi.get("nombre", ""),
                                        "Estado": _status_pre.get(_cl, "PENDIENTE"),
                                    })
                                with st.expander(f"Ver materias ({len(_filas_pre)})"):
                                    st.dataframe(pd.DataFrame(_filas_pre), use_container_width=True, hide_index=True)
                else:
                    st.info("No se detectaron materias de pre-especialidad en el historial.")
            except Exception as e:
                st.warning(f"Error al calcular pre-especialidades: {str(e)}")

        st.markdown("""
<div class="nav-cta-banner">
  <div class="nav-cta-label">📌 Siguiente paso</div>
  <div class="nav-cta-desc">El sistema experto analiza seriaciones y prioridades para sugerir las mejores materias a inscribir.</div>
</div>""", unsafe_allow_html=True)
        st.markdown('<div class="nav-btn-attached">', unsafe_allow_html=True)
        if st.button("🧠  Ver Materias Candidatas para Cargar", key="btn_next_experto", type="primary", use_container_width=True):
            st.switch_page(st.Page(_pg_experto, title="Materias Candidatas para Cargar", icon=":material/psychology:"))
        st.markdown('</div>', unsafe_allow_html=True)

    def _pg_experto():
        st.divider()

        if historial_df.empty:
            st.info("⚠️ Sube y procesa el **Historial Académico** (Paso 1 en el sidebar) para ver las materias candidatas.")
        else:
            # ── Preparar historial para el sistema experto ──
            plan_estudios = str(getattr(datos, "plan_estudios", "2021ID") or "2021ID").strip()

            historial_aprobado = []
            for _, row in historial_df.iterrows():
                clave = str(row.get("clave", "")).strip().upper()
                if not clave:
                    continue
                estatus = str(row.get("estatus", "")).upper()
                ciclo = row.get("ciclo")
                try:
                    ciclo = int(ciclo) if pd.notna(ciclo) else 1
                except Exception:
                    ciclo = 1
                cal = row.get("calificacion", 0.0)
                cred = row.get("creditos", 0)
                try:
                    cal = float(cal) if pd.notna(cal) else 0.0
                except Exception:
                    cal = 0.0
                try:
                    cred = int(float(cred)) if pd.notna(cred) else 0
                except Exception:
                    cred = 0
                historial_aprobado.append({
                    "clave": clave,
                    "ciclo": ciclo,
                    "estatus": estatus,
                    "calificacion": cal,
                    "creditos": cred,
                    "nombre": str(row.get("nombre", "")).strip(),
                    "periodo": str(row.get("periodo", "")).strip(),
                })

            # ── Cargar mapa curricular ──
            mapa_path = Path(__file__).parent.parent / "data" / f"mapa_curricular_{plan_estudios}_real_completo.json"
            mapa_curricular = None
            if mapa_path.exists():
                try:
                    with open(mapa_path, "r", encoding="utf-8") as f:
                        datos_mapa = json.load(f)
                        if isinstance(datos_mapa, dict):
                            mapa_curricular = []
                            for clave, info in datos_mapa.items():
                                if isinstance(info, dict):
                                    info["clave"] = str(clave).strip().upper()
                                    mapa_curricular.append(info)
                except Exception:
                    pass

            # ── Ejecutar sistema experto ──
            # Se ignoran materias EN_CURSO/RECURSANDO para que el sistema
            # recomiende como si el alumno aún no hubiera cargado este semestre,
            # permitiendo comparar la recomendación vs la carga real.
            historial_para_experto = [
                h for h in historial_aprobado
                if h["estatus"] not in ("EN_CURSO", "RECURSANDO")
            ]
            # Modo simulación: EN_CURSO no contribuye a detección de especialidad
            # (el semestre actual aún no ha comenzado).
            especialidad_forzada = st.session_state.get("especialidad_forzada", None)
            resultado = ejecutar_sistema_experto(
                historial_academico=historial_para_experto,
                mapa_curricular=mapa_curricular,
                plan_estudios=plan_estudios,
                especialidad_forzada=especialidad_forzada,
                en_curso_para_especialidad=[],
            )

            # Guardar para pestaña de generador de cargas
            st.session_state.resultado_experto = resultado

            debug_info = resultado.get("debug", {})
            sem_cursado = resultado.get("semestre_cursado", 0)
            sem_objetivo = resultado.get("semestre_objetivo", 0)
            ciclo_act  = sem_objetivo
            esp        = resultado.get("especialidad_detectada") or None
            elim_a     = debug_info.get("eliminadas_regla_a", 0)
            elim_b     = debug_info.get("eliminadas_regla_b", 0)
            elim_c     = debug_info.get("eliminadas_regla_c", 0)
            elim_d     = debug_info.get("eliminadas_regla_d", 0)
            elim_e     = debug_info.get("eliminadas_regla_e", 0)
            ini_count  = debug_info.get("candidatas_iniciales_count", 0)

            # ── Métricas ──
            st.subheader("📊 Resultado del Análisis")
            col_met1, col_met2, col_met3 = st.columns(3)
            with col_met1:
                st.metric("Semestre objetivo", f"{sem_objetivo}", delta=f"Cursando sem. {sem_cursado}")
            with col_met2:
                st.metric("Materias candidatas", resultado.get("candidatas_count", 0))
            with col_met3:
                st.metric("Analizadas inicialmente", ini_count)

            # ── Tabla única de candidatas con secciones de color ──
            candidatas_detalles = resultado.get("candidatas_detalles", [])
            if candidatas_detalles:
                st.subheader("Materias recomendadas para el siguiente semestre")

                df_candidatas = pd.DataFrame(candidatas_detalles)

                if "prerequisitos" in df_candidatas.columns:
                    df_candidatas["prerequisitos"] = df_candidatas["prerequisitos"].apply(
                        lambda x: ", ".join(x) if isinstance(x, list) and x else "—"
                    )

                _nivel_config = {
                    1: {"color": "#b71c1c", "bg": "#ffebee", "titulo": "⚠️ Prerequisito faltante retroactivo", "desc": "Ya aprobaste la materia sucesora pero aún falta este prerequisito"},
                    2: {"color": "#d32f2f", "bg": "#fdecea", "titulo": "🔁 Materias reprobadas", "desc": "Pendientes de recursar para poder avanzar"},
                    3: {"color": "#ef6c00", "bg": "#fff3e0", "titulo": "📚 Pendientes de ciclos anteriores", "desc": "Cierra ciclos atrasados — ordenadas del ciclo más antiguo al más reciente"},
                    4: {"color": "#1565c0", "bg": "#e3f2fd", "titulo": "✅ Ciclo actual", "desc": "Materias que corresponden a tu ciclo objetivo — progresión natural"},
                    5: {"color": "#6a1b9a", "bg": "#f3e5f5", "titulo": "🎯 Elección libre", "desc": "Electivas disponibles (línea de especialidad no seleccionada)"},
                    6: {"color": "#00695c", "bg": "#e0f2f1", "titulo": "🌐 Co-curriculares pendientes", "desc": "Inglés u otras actividades co-curriculares que aún te faltan"},
                }

                niveles_presentes = sorted(df_candidatas["prioridad"].unique()) if "prioridad" in df_candidatas.columns else []

                total_creditos = 0
                total_basicas = 0
                total_optativas = 0

                # Construir tabla HTML
                _col_w = ["90px", "auto", "80px", "80px", "120px", "130px", "auto"]
                _th = "padding:10px 12px; text-align:left; border-right:2px solid #555; white-space:nowrap;"
                _th_c = "padding:10px 8px; text-align:center; border-right:2px solid #555; white-space:nowrap;"
                html = [
                    '<table style="width:100%; border-collapse:collapse; font-size:13px; '
                    'font-family: Source Sans Pro, sans-serif; border:1px solid #ccc;">',
                    '<colgroup>',
                    *[f'<col style="width:{w}">' for w in _col_w],
                    '</colgroup>',
                    '<thead><tr style="background:#262730; color:#fafafa;">',
                    f'<th style="{_th}">Clave</th>',
                    f'<th style="{_th}">Nombre</th>',
                    f'<th style="{_th_c}">Semestre</th>',
                    f'<th style="{_th_c}">Créditos</th>',
                    f'<th style="{_th}">Categoría</th>',
                    f'<th style="{_th}">Prerequisitos</th>',
                    f'<th style="padding:10px 12px; text-align:left;">Razón</th>',
                    '</tr></thead><tbody>',
                ]

                for nivel_num in niveles_presentes:
                    df_nivel = df_candidatas[df_candidatas["prioridad"] == nivel_num]
                    if df_nivel.empty:
                        continue

                    cfg = _nivel_config.get(nivel_num, {"color": "#757575", "bg": "#f5f5f5", "titulo": f"Nivel {nivel_num}", "desc": ""})
                    n_mat = len(df_nivel)
                    n_cred = int(df_nivel["creditos"].sum())
                    total_creditos += n_cred
                    total_basicas += len(df_nivel[df_nivel["categoria"] == "BASICA"])
                    total_optativas += len(df_nivel[df_nivel["categoria"] != "BASICA"])

                    # Fila separadora de sección (banda de color sólido)
                    html.append(
                        f'<tr style="background:{cfg["color"]}; color:white;">'
                        f'<td colspan="7" style="padding:9px 12px; font-weight:700; font-size:13px; '
                        f'border-top:3px solid rgba(0,0,0,0.15); letter-spacing:0.02em;">'
                        f'{cfg["titulo"]}'
                        f'<span style="font-weight:400; margin-left:10px; font-size:12px; opacity:0.9;">'
                        f'— {n_mat} materia{"s" if n_mat != 1 else ""} · {n_cred} créditos'
                        f'</span>'
                        f'<span style="font-weight:300; margin-left:14px; font-size:11px; opacity:0.75; font-style:italic;">'
                        f'{cfg["desc"]}'
                        f'</span>'
                        f'</td></tr>'
                    )

                    # Filas de materias con separador de columnas visible
                    _td = "padding:8px 12px; border-right:2px solid #ccc; vertical-align:top;"
                    _td_c = "padding:8px 8px; border-right:2px solid #ccc; text-align:center; vertical-align:top;"
                    for idx, (_, row) in enumerate(df_nivel.iterrows()):
                        prereqs = row.get("prerequisitos", "—")
                        razon = row.get("razon", "")
                        cat_display = str(row.get("categoria", "")).replace("_", " ").title()
                        # Alternate row shade for readability
                        row_bg = cfg["bg"] if idx % 2 == 0 else "white"
                        html.append(
                            f'<tr style="background:{row_bg}; border-bottom:1px solid #d0d0d0;">'
                            f'<td style="{_td} font-weight:700; font-family:monospace; font-size:12px;">{row["clave"]}</td>'
                            f'<td style="{_td}">{row["nombre"]}</td>'
                            f'<td style="{_td_c}">{row["ciclo"]}</td>'
                            f'<td style="{_td_c}">{row["creditos"]}</td>'
                            f'<td style="{_td} font-size:12px; color:#555;">{cat_display}</td>'
                            f'<td style="{_td} font-size:12px; font-family:monospace; color:#1a237e;">{prereqs}</td>'
                            f'<td style="padding:8px 10px; font-size:12px; color:#444; font-style:italic; vertical-align:top;">{razon}</td>'
                            f'</tr>'
                        )

                html.append('</tbody></table>')
                st.markdown("".join(html), unsafe_allow_html=True)

                # Resumen
                st.markdown("")
                col_est1, col_est2, col_est3 = st.columns(3)
                with col_est1:
                    st.metric("Créditos totales", total_creditos)
                with col_est2:
                    st.metric("Materias básicas", total_basicas)
                with col_est3:
                    st.metric("Materias optativas", total_optativas)
            else:
                st.info("No se encontraron materias candidatas disponibles en este momento.")

            # ── Explicación de la lógica (debajo de la tabla) ──
            st.divider()
            with st.expander("¿Cómo se eligieron estas materias?", expanded=False):

                # Resumen breve del proceso
                final_count = resultado.get("candidatas_count", 0)
                st.markdown(
                    f"Se analizaron **{ini_count}** materias candidatas y después de aplicar "
                    f"las reglas de seriación quedaron **{final_count}**. "
                    f"A continuación se explica por qué se recomienda cada una:"
                )
                st.markdown("")

                # Colores por nivel de prioridad
                _colores_nivel = {
                    1: "#ffebee",   # rojo claro — prereq faltante retroactivo
                    2: "#fdecea",   # rojo suave — reprobadas
                    3: "#fff3e0",   # naranja claro — ciclos anteriores
                    4: "#e3f2fd",   # azul claro — ciclo actual
                    5: "#f3e5f5",   # morado claro — elección libre
                    6: "#e0f2f1",   # verde agua — co-curriculares
                }

                # Agrupar candidatas por (nivel, razon)
                from collections import OrderedDict
                grupos = OrderedDict()
                for det in candidatas_detalles:
                    key = (det.get("prioridad", 99), det.get("nivel", "Otras"), det.get("razon", ""))
                    if key not in grupos:
                        grupos[key] = []
                    grupos[key].append(det)

                for (prio, nivel_nombre, razon), materias_grupo in grupos.items():
                    color = _colores_nivel.get(prio, "#f5f5f5")

                    if len(materias_grupo) == 1:
                        m = materias_grupo[0]
                        st.markdown(
                            f"<div style='background:{color}; padding:10px 14px; "
                            f"border-radius:8px; margin-bottom:8px; border-left:4px solid {color.replace('e','9').replace('f','b')};'>"
                            f"<strong>{m['clave']} — {m['nombre']}</strong> "
                            f"<span style='color:#666; font-size:0.9em;'>(Ciclo {m['ciclo']} · {m['creditos']} cr)</span><br>"
                            f"<span style='font-size:0.92em;'>{razon}</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                    else:
                        lista_html = "".join(
                            f"<li><strong>{m['clave']}</strong> — {m['nombre']} "
                            f"<span style='color:#666; font-size:0.9em;'>(Ciclo {m['ciclo']} · {m['creditos']} cr)</span></li>"
                            for m in materias_grupo
                        )
                        st.markdown(
                            f"<div style='background:{color}; padding:10px 14px; "
                            f"border-radius:8px; margin-bottom:8px; border-left:4px solid {color.replace('e','9').replace('f','b')};'>"
                            f"<strong>{nivel_nombre}</strong> — "
                            f"<span style='font-size:0.92em;'>{razon}</span>"
                            f"<ul style='margin:6px 0 2px 0;'>{lista_html}</ul>"
                            f"</div>",
                            unsafe_allow_html=True
                        )

                # Resumen de filtros aplicados
                filtros_activos = []
                if elim_a > 0: filtros_activos.append(f"Prerequisitos no cumplidos: -{elim_a}")
                if elim_b > 0: filtros_activos.append(f"Cadenas de seriación: -{elim_b}")
                if elim_c > 0: filtros_activos.append(f"Cuota de Elección Libre: -{elim_c}")
                if elim_d > 0: filtros_activos.append(f"Pre-especialidad ({esp or 'detectada'}): -{elim_d}")
                if elim_e > 0: filtros_activos.append(f"Prácticas pre-especialidad: -{elim_e}")
                if filtros_activos:
                    st.markdown("")
                    st.markdown(
                        "**Materias descartadas:** " + " · ".join(filtros_activos)
                    )

        st.markdown("""
<div class="nav-cta-banner">
  <div class="nav-cta-label">📅 Siguiente paso</div>
  <div class="nav-cta-desc">Genera combinaciones óptimas de materias para el próximo semestre sin choques de horario.</div>
</div>""", unsafe_allow_html=True)
        st.markdown('<div class="nav-btn-attached">', unsafe_allow_html=True)
        if st.button("📅  Ver Generador de Cargas", key="btn_next_cargas", type="primary", use_container_width=True):
            st.switch_page(st.Page(_pg_cargas, title="Generador de Cargas", icon=":material/calendar_month:"))
        st.markdown('</div>', unsafe_allow_html=True)

    def _pg_cargas():
        st.header("📅 Generador de Cargas Académicas")
        st.caption("Genera combinaciones óptimas de materias para tu próximo semestre usando optimización multi-objetivo (NSGA-III).")

        from services.oferta_service import cargar_oferta_csv, filtrar_oferta_por_candidatas
        from agents.generador_cargas import generar_cargas_nsga3
        import services.oferta_service as _oferta_mod
        _carpeta_oferta = Path(_oferta_mod.__file__).parent.parent / "agents" / "OfertaAcademica"

        # Verificar que existan candidatas del sistema experto
        if "resultado_experto" not in st.session_state or not st.session_state.resultado_experto:
            st.info("Primero ve a la pestaña **Sistema Experto** para generar las materias candidatas.")
        else:
            resultado_exp = st.session_state.resultado_experto
            candidatas_det = resultado_exp.get("candidatas_detalles", [])

            if not candidatas_det:
                st.warning("No hay materias candidatas. Revisa el Sistema Experto.")
            else:
                # --- Selector de oferta académica ---
                opciones_oferta = {
                    "Prueba Oferta Primavera (193)": str(_carpeta_oferta / "IRSecciones_193.csv"),
                    "Prueba Oferta Verano (194)": str(_carpeta_oferta / "IR_194_Limpio.csv"),
                    "Prueba Oferta Otoño (195)": str(_carpeta_oferta / "IR_195_Limpio.csv"),
                }
                oferta_seleccionada = st.selectbox(
                    "📂 Selecciona la oferta académica",
                    list(opciones_oferta.keys()),
                    key="selector_oferta_cargas",
                )
                ruta_oferta = opciones_oferta[oferta_seleccionada]

                # --- Cargar oferta académica ---
                df_oferta = cargar_oferta_csv(ruta_csv=ruta_oferta)
                if df_oferta.empty:
                    st.error("No se encontró el archivo de oferta académica (CSV) en `agents/OfertaAcademica/`.")
                else:
                    secciones_disp = filtrar_oferta_por_candidatas(df_oferta, candidatas_det)

                    if not secciones_disp:
                        st.warning("Ninguna materia candidata tiene secciones disponibles en la oferta académica actual.")
                    else:
                        materias_en_oferta = len(set(s["clave"] for s in secciones_disp))
                        st.success(f"Se encontraron **{len(secciones_disp)} secciones** de **{materias_en_oferta} materias** candidatas en la oferta académica.")

                        # --- Configuración del estudiante ---
                        st.subheader("⚙️ Configuración")

                        # Detectar si es condicionado
                        es_condicionado = False
                        if hasattr(st.session_state, "datos_estudiante") and st.session_state.datos_estudiante:
                            sit = str(getattr(st.session_state.datos_estudiante, "situacion", "")).upper()
                            es_condicionado = "CONDICIONADO" in sit

                        if es_condicionado:
                            st.warning("⚠️ Estudiante **condicionado**: máximo 3 materias.")
                            max_mat = 3
                            materias_deseadas = st.slider("Materias deseadas", 1, 3, 3, key="cargas_mat_deseadas")
                        else:
                            max_mat = 9
                            materias_deseadas = st.slider("Materias deseadas", 3, 9, 7, key="cargas_mat_deseadas")

                        # Mínimo de materias por carga: 3, salvo que la oferta tenga menos de 3 candidatas
                        min_mat_cargas = min(3, materias_en_oferta)

                        # --- Tabla de disponibilidad horaria (fragment) ---
                        st.subheader("🕐 Disponibilidad Horaria")
                        st.caption("Haz clic en las celdas para marcar (✓) o desmarcar (✗) tu disponibilidad.")
                        _widget_disponibilidad_horaria()
                        disp = st.session_state.get("disp", {})

                        # --- Botón para generar cargas ---
                        st.divider()

                        if st.button("🚀 Generar Cargas Académicas", type="primary", key="btn_generar_cargas"):
                            with st.spinner("Optimizando cargas con NSGA-III..."):
                                cargas = generar_cargas_nsga3(
                                    secciones_disponibles=secciones_disp,
                                    disponibilidad=disp,
                                    materias_deseadas=materias_deseadas,
                                    max_materias=max_mat,
                                    max_creditos=999,
                                    min_materias=min_mat_cargas,
                                    poblacion_size=100,
                                    generaciones=50,
                                    n_resultados=3,
                                )

                            if not cargas:
                                st.error("No se pudieron generar cargas válidas con tu disponibilidad horaria. Intenta ampliar tus horas disponibles.")
                            else:
                                st.session_state.cargas_generadas = cargas
                                st.success(f"Se generaron **{len(cargas)} cargas** optimizadas.")

                        # --- Mostrar resultados ---
                        if "cargas_generadas" in st.session_state and st.session_state.cargas_generadas:
                            cargas_gen = st.session_state.cargas_generadas

                            for idx_carga, carga in enumerate(cargas_gen):
                                etiqueta = carga.get("etiqueta", f"Carga {idx_carga + 1}")
                                es_recomendada = idx_carga == 0

                                with st.container():
                                    if es_recomendada:
                                        st.markdown(f"### ⭐ {etiqueta}")
                                    else:
                                        st.markdown(f"### 📋 {etiqueta}")

                                    # Explicación de diferencias vs Recomendada
                                    if idx_carga > 0:
                                        ref = cargas_gen[0]
                                        ref_claves = {s["clave"]: s for s in ref["secciones"]}
                                        cur_claves = {s["clave"]: s for s in carga["secciones"]}

                                        materias_nuevas = set(cur_claves) - set(ref_claves)
                                        materias_quitadas = set(ref_claves) - set(cur_claves)
                                        materias_comunes = set(cur_claves) & set(ref_claves)

                                        cambios_seccion = []
                                        for cl in materias_comunes:
                                            sec_ref = ref_claves[cl]
                                            sec_cur = cur_claves[cl]
                                            if sec_ref.get("seccion") != sec_cur.get("seccion"):
                                                h_ref = ", ".join(f"{b['dia'][:3]} {b['inicio']:02d}-{b['fin']:02d}" for b in sec_ref["horario"])
                                                h_cur = ", ".join(f"{b['dia'][:3]} {b['inicio']:02d}-{b['fin']:02d}" for b in sec_cur["horario"])
                                                cambios_seccion.append(f"- **{sec_cur['nombre']}**: horario cambia de ({h_ref}) a ({h_cur})")

                                        # Construir explicación detallada
                                        diff_lines = []
                                        razones = []

                                        if materias_quitadas:
                                            for c in materias_quitadas:
                                                s = ref_claves[c]
                                                diff_lines.append(f"- **Se quita {s['nombre']}** (nivel {s['prioridad']})")
                                                # Explicar por qué
                                                h_str = ", ".join(f"{b['dia'][:3]} {b['inicio']:02d}-{b['fin']:02d}" for b in s["horario"])
                                                razones.append(f"Quitar *{s['nombre']}* ({h_str}) libera espacio en el horario")

                                        if materias_nuevas:
                                            for c in materias_nuevas:
                                                s = cur_claves[c]
                                                diff_lines.append(f"- **Se agrega {s['nombre']}** (nivel {s['prioridad']})")

                                        if cambios_seccion:
                                            diff_lines.extend(cambios_seccion)
                                            razones.append("Cambiar de sección ofrece un horario diferente con otro profesor")

                                        # Comparar scores para explicar el trade-off
                                        ref_pri = ref.get("score_prioridad", 0)
                                        ref_comp = ref.get("score_compacidad", 0)
                                        cur_pri = carga.get("score_prioridad", 0)
                                        cur_comp = carga.get("score_compacidad", 0)

                                        if carga["total_materias"] < ref["total_materias"]:
                                            diff_mat = ref["total_materias"] - carga["total_materias"]
                                            razones.append(f"Carga más ligera ({carga['total_materias']} vs {ref['total_materias']} materias), reduce la presión académica del semestre")
                                        elif carga["total_materias"] > ref["total_materias"]:
                                            razones.append(f"Carga más completa ({carga['total_materias']} vs {ref['total_materias']} materias), avanza más rápido en la carrera")

                                        if cur_comp > ref_comp:
                                            razones.append(f"Horario más compacto ({cur_comp:.0%} vs {ref_comp:.0%}): menos huecos entre clases y días más concentrados")
                                        elif cur_comp < ref_comp:
                                            razones.append(f"Horario más disperso ({cur_comp:.0%} vs {ref_comp:.0%})")

                                        if cur_pri < ref_pri:
                                            razones.append(f"Sacrifica cobertura de prioridad ({cur_pri:.0%} vs {ref_pri:.0%}) a cambio de las ventajas anteriores")

                                        # Si aún no hay razones, dar una genérica
                                        if not razones:
                                            razones.append("Ofrece una combinación distinta de secciones con horarios alternativos")

                                        if not diff_lines:
                                            diff_lines.append("- Mismas materias, mismo horario")

                                        explicacion = "**Cambios vs Recomendada:**\n" + "\n".join(diff_lines)
                                        if razones:
                                            explicacion += "\n\n**¿Por qué esta alternativa?** " + ". ".join(razones) + "."

                                        st.info(explicacion)

                                    # Métricas
                                    mc1, mc2, mc3, mc4 = st.columns(4)
                                    mc1.metric("Materias", carga["total_materias"])
                                    mc2.metric("Créditos", carga["total_creditos"])
                                    mc3.metric("Prioridad", f"{carga['score_prioridad']:.0%}")
                                    mc4.metric("Compacidad", f"{carga['score_compacidad']:.0%}")

                                    # Tabla de materias
                                    filas_carga = []
                                    for sec in carga["secciones"]:
                                        horario_str = ", ".join(
                                            f"{b['dia'][:3]} {b['inicio']:02d}-{b['fin']:02d}"
                                            for b in sec["horario"]
                                        )
                                        filas_carga.append({
                                            "Clave": sec["clave"],
                                            "Materia": sec["nombre"],
                                            "Créditos": sec["creditos"],
                                            "Nivel": sec["prioridad"],
                                            "Horario": horario_str,
                                            "Profesor": sec.get("profesor", ""),
                                            "Razón": sec.get("razon", ""),
                                        })

                                    import pandas as _pd_cargas
                                    df_carga_display = _pd_cargas.DataFrame(filas_carga)
                                    st.dataframe(df_carga_display, use_container_width=True, hide_index=True)

                                    # Horario visual
                                    with st.expander("📅 Ver horario semanal"):
                                        grid = {}
                                        for sec in carga["secciones"]:
                                            for bloque in sec["horario"]:
                                                for h in range(bloque["inicio"], bloque["fin"]):
                                                    key = (h, bloque["dia"])
                                                    grid[key] = sec.get("nombre", sec["clave"])

                                        _dias_h = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado"]
                                        header_h = "".join(f'<th style="padding:4px 8px;text-align:center;font-size:12px;">{d[:3]}</th>' for d in _dias_h)
                                        filas_h = []
                                        _colores_mat = {}
                                        _paleta = ["#93c5fd", "#fbbf24", "#6ee7b7", "#f472b6", "#a78bfa", "#fb923c", "#22d3ee", "#e879f9", "#4ade80", "#f87171"]
                                        for h in range(7, 22):
                                            celdas_h = ""
                                            for dia in _dias_h:
                                                val = grid.get((h, dia))
                                                if val:
                                                    if val not in _colores_mat:
                                                        _colores_mat[val] = _paleta[len(_colores_mat) % len(_paleta)]
                                                    bg = _colores_mat[val]
                                                    celdas_h += f'<td style="background:{bg};text-align:center;padding:3px;font-size:11px;font-weight:bold;">{val}</td>'
                                                else:
                                                    celdas_h += '<td style="background:#f9fafb;text-align:center;padding:3px;font-size:10px;color:#ccc;">—</td>'
                                            filas_h.append(f'<tr><td style="padding:3px 6px;font-size:11px;font-weight:bold;">{h:02d}:00</td>{celdas_h}</tr>')

                                        tabla_horario = f"""
                                        <table style="border-collapse:collapse;width:100%;">
                                            <thead><tr><th style="padding:3px 6px;font-size:12px;">Hora</th>{header_h}</tr></thead>
                                            <tbody>{"".join(filas_h)}</tbody>
                                        </table>
                                        """
                                        st.markdown(tabla_horario, unsafe_allow_html=True)

                                    st.divider()

                        # ==============================================================
                        # SECCIÓN: COMPARACIÓN CON LA CARGA REAL DEL ESTUDIANTE
                        # ==============================================================
                        st.divider()
                        st.subheader("🔍 Comparación con la carga real del estudiante")
                        st.caption("Contrasta la carga real del estudiante con la recomendación del sistema.")

                        if "cargas_generadas" not in st.session_state or not st.session_state.cargas_generadas:
                            st.info("Genera las cargas académicas primero para ver la comparación con la carga real del estudiante.")
                        else:
                            cargas_gen_comp = st.session_state.cargas_generadas

                        # Extraer materias en curso del historial
                            _en_curso_reales = []
                            if not historial_filtrado.empty:
                                _mask_ec = historial_filtrado["estatus"].isin(["EN_CURSO", "RECURSANDO"])
                                for _, _r in historial_filtrado[_mask_ec].iterrows():
                                    _en_curso_reales.append({
                                        "clave": str(_r.get("clave", "")).strip().upper(),
                                        "nombre": str(_r.get("nombre", "")).strip(),
                                        "creditos": int(_r.get("creditos", 0)) if pd.notna(_r.get("creditos")) else 0,
                                        "estatus": str(_r.get("estatus", "")).strip(),
                                    })

                            if not _en_curso_reales:
                                st.info("No se detectaron materias en curso en el historial. El análisis de comparación requiere que el alumno tenga materias activas este semestre.")
                            else:
                                # --- Preparar datos base ---
                                _candidatas_dict = {
                                    d["clave"]: d for d in resultado_exp.get("candidatas_detalles", [])
                                }
                                _carga_rec = cargas_gen_comp[0] if cargas_gen_comp else None
                                _rec_claves = {s["clave"]: s for s in (_carga_rec["secciones"] if _carga_rec else [])}
                                _ec_claves = {m["clave"] for m in _en_curso_reales}

                                # --- Clasificar cada materia en curso ---
                                filas_comparacion = []
                                score_sum = 0.0
                                peso_total = 0.0

                                for mat in _en_curso_reales:
                                    cl = mat["clave"]
                                    en_candidatas = cl in _candidatas_dict
                                    en_recomendada = cl in _rec_claves
                                    prioridad = _candidatas_dict[cl]["prioridad"] if en_candidatas else None

                                    if en_recomendada:
                                        estado_comp = "✅ En recomendada"
                                        color_estado = "#d1fae5"
                                    elif en_candidatas:
                                        estado_comp = "🟡 Candidata (no en top)"
                                        color_estado = "#fef9c3"
                                    else:
                                        estado_comp = "⚠️ Fuera del sistema"
                                        color_estado = "#fee2e2"

                                    # Puntaje: 1.0 si coincide con recomendada, 0.6 si es candidata, 0.0 si fuera
                                    if en_recomendada:
                                        pts = 1.0
                                    elif en_candidatas:
                                        pts = 0.6
                                    else:
                                        pts = 0.0

                                    # Ponderación inversa a la prioridad (prio 1 pesa más)
                                    peso = (6 - prioridad) if prioridad else 1
                                    score_sum += pts * peso
                                    peso_total += max(peso, 1)

                                    filas_comparacion.append({
                                        "Clave": cl,
                                        "Materia": mat["nombre"],
                                        "Créditos": mat["creditos"],
                                        "Estatus": mat["estatus"],
                                        "Prioridad sistema": str(prioridad) if prioridad else "—",
                                        "Resultado": estado_comp,
                                    })

                                # --- Materias recomendadas que NO está cursando ---
                                _rec_no_cursadas = [
                                    s for cl, s in _rec_claves.items() if cl not in _ec_claves
                                ] if _rec_claves else []

                                # --- Score de alineación ---
                                score_alineacion = (score_sum / peso_total) if peso_total > 0 else 0.0

                                # Cobertura: cuántas de las recomendadas sí están cursando
                                n_rec = len(_rec_claves)
                                n_coinciden = sum(1 for cl in _ec_claves if cl in _rec_claves)
                                cobertura = n_coinciden / n_rec if n_rec > 0 else 0.0

                                # Materias fuera del sistema experto
                                n_fuera = sum(1 for m in _en_curso_reales if m["clave"] not in _candidatas_dict)

                                # --- Métricas ---
                                _col_s1, _col_s2, _col_s3, _col_s4 = st.columns(4)
                                _col_s1.metric(
                                    "Alineación general",
                                    f"{score_alineacion:.0%}",
                                    help="Qué tan bien corresponde la carga real con la recomendación (ponderado por prioridad)"
                                )
                                _col_s2.metric(
                                    "Cobertura de recomendada",
                                    f"{cobertura:.0%}",
                                    help=f"Materias de la carga Recomendada que sí está cursando ({n_coinciden}/{n_rec})"
                                )
                                _col_s3.metric(
                                    "Materias en curso",
                                    len(_en_curso_reales),
                                    help="Total de materias que el alumno está cursando este semestre"
                                )
                                _col_s4.metric(
                                    "Fuera del sistema",
                                    n_fuera,
                                    delta=f"-{n_fuera}" if n_fuera > 0 else None,
                                    delta_color="inverse",
                                    help="Materias que el alumno está cursando pero el sistema experto no recomendó"
                                )

                                # Barra de interpretación
                                if score_alineacion >= 0.80:
                                    _interp = "🟢 **Excelente alineación.** La carga del estudiante corresponde muy bien con la recomendación del sistema."
                                elif score_alineacion >= 0.55:
                                    _interp = "🟡 **Alineación parcial.** El estudiante siguió parte de la recomendación pero hay diferencias importantes."
                                else:
                                    _interp = "🔴 **Baja alineación.** La carga real difiere significativamente de lo que el sistema recomendó."
                                st.info(_interp)

                                # --- Tabla de comparación ---
                                st.markdown("**Detalle de materias en curso:**")
                                import pandas as _pd_comp
                                df_comp = _pd_comp.DataFrame(filas_comparacion)
                                st.dataframe(df_comp, use_container_width=True, hide_index=True)

                                # --- Materias recomendadas que no está cursando ---
                                if _rec_no_cursadas:
                                    with st.expander(f"📋 Materias de la carga Recomendada que NO está cursando ({len(_rec_no_cursadas)})"):
                                        filas_pendientes = []
                                        for s in _rec_no_cursadas:
                                            filas_pendientes.append({
                                                "Clave": s["clave"],
                                                "Materia": s["nombre"],
                                                "Créditos": s["creditos"],
                                                "Prioridad": s["prioridad"],
                                                "Horario": ", ".join(
                                                    f"{b['dia'][:3]} {b['inicio']:02d}-{b['fin']:02d}"
                                                    for b in s["horario"]
                                                ),
                                            })
                                        st.dataframe(
                                            _pd_comp.DataFrame(filas_pendientes),
                                            use_container_width=True, hide_index=True
                                        )

        st.markdown("""
<div class="nav-cta-banner">
  <div class="nav-cta-label">🗺️ Siguiente paso</div>
  <div class="nav-cta-desc">Visualiza el avance del estudiante sobre el mapa oficial del plan IDeIO 2021.</div>
</div>""", unsafe_allow_html=True)
        st.markdown('<div class="nav-btn-attached">', unsafe_allow_html=True)
        if st.button("🗺️  Ver Mapa Curricular", key="btn_next_mapa", type="primary", use_container_width=True):
            st.switch_page(st.Page(_pg_mapa, title="Mapa Curricular", icon=":material/map:"))
        st.markdown('</div>', unsafe_allow_html=True)

    def _pg_mapa():
        st.header("📋 Mapa Curricular por Semestre")
        st.caption("Esquema oficial del plan 2021ID. Las materias de tu historial se marcan según su estatus.")

        # Construir sets de estatus del estudiante
        if not historial_filtrado.empty:
            _aprobadas_mapa = set(
                historial_filtrado[historial_filtrado["estatus"] == "APROBADA"]["clave"].str.upper()
            )
            _en_curso_mapa = set(
                historial_filtrado[historial_filtrado["estatus"].isin(["EN_CURSO", "RECURSANDO"])]["clave"].str.upper()
            )
            _reprobadas_mapa = set(
                historial_filtrado[
                    (historial_filtrado["estatus"] == "REPROBADA") &
                    (~historial_filtrado["clave"].str.upper().isin(_aprobadas_mapa))
                ]["clave"].str.upper()
            )
        else:
            _aprobadas_mapa = _en_curso_mapa = _reprobadas_mapa = set()

        def _badge_materia(clave, nombre, creditos, categoria):
            """Devuelve HTML de una tarjeta de materia con color según estatus."""
            c = str(clave).strip().upper()
            if c in _aprobadas_mapa:
                bg, border, icon = "#d1fae5", "#10b981", "✅"
            elif c in _en_curso_mapa:
                bg, border, icon = "#dbeafe", "#3b82f6", "🔵"
            elif c in _reprobadas_mapa:
                bg, border, icon = "#fee2e2", "#ef4444", "❌"
            else:
                bg, border, icon = "#f9fafb", "#d1d5db", "⬜"

            cat_colors = {
                "BASICA": "#6366f1",
                "ELECCION_LIBRE": "#f59e0b",
                "PREESPECIALIDAD": "#8b5cf6",
            }
            cat_label = {
                "BASICA": "Básica",
                "ELECCION_LIBRE": "EL",
                "PREESPECIALIDAD": "Preesp",
            }
            cat_key = str(categoria).upper()
            cat_c = cat_colors.get(cat_key, "#9ca3af")
            cat_l = cat_label.get(cat_key, categoria)

            return (
                f'<div style="background:{bg};border:2px solid {border};border-radius:8px;'
                f'padding:8px 10px;margin:4px 0;font-size:0.78rem;line-height:1.4;">'
                f'<span style="font-weight:700;color:#1f2937;">{icon} {clave}</span>'
                f'<span style="float:right;background:{cat_c};color:#fff;border-radius:4px;'
                f'padding:1px 6px;font-size:0.68rem;">{cat_l}</span><br>'
                f'<span style="color:#374151;">{nombre}</span><br>'
                f'<span style="color:#6b7280;font-size:0.7rem;">{creditos} cr.</span>'
                f'</div>'
            )

        # Leyenda
        st.markdown(
            '<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:12px;font-size:0.8rem;">'
            '<span>✅ Aprobada</span>'
            '<span>🔵 En curso</span>'
            '<span>❌ Reprobada</span>'
            '<span>⬜ Pendiente</span>'
            '<span style="background:#6366f1;color:#fff;border-radius:4px;padding:1px 8px;">Básica</span>'
            '<span style="background:#f59e0b;color:#fff;border-radius:4px;padding:1px 8px;">EL</span>'
            '<span style="background:#8b5cf6;color:#fff;border-radius:4px;padding:1px 8px;">Preesp</span>'
            '</div>',
            unsafe_allow_html=True
        )

        # Agrupar mapa por semestre
        _mapa_por_sem = {}
        for _m in mapa_curricular:
            _sem = _m.get("ciclo", 0)
            _mapa_por_sem.setdefault(_sem, []).append(_m)

        SEMESTRES = [s for s in range(1, 9) if s in _mapa_por_sem]

        # Mostrar de 2 en 2 semestres por fila
        for fila_idx in range(0, len(SEMESTRES), 2):
            par = SEMESTRES[fila_idx:fila_idx + 2]
            cols = st.columns(len(par))
            for col, sem in zip(cols, par):
                anual = (sem + 1) // 2
                with col:
                    st.markdown(
                        f'<div style="background:#e0e7ff;border-radius:8px;padding:6px 12px;'
                        f'margin-bottom:8px;font-weight:700;font-size:0.9rem;">'
                        f'Semestre {sem} <span style="font-weight:400;color:#4f46e5;">'
                        f'(Ciclo anual {anual})</span></div>',
                        unsafe_allow_html=True
                    )
                    materias_sem = sorted(
                        _mapa_por_sem.get(sem, []),
                        key=lambda x: (x.get("categoria", ""), x.get("clave", ""))
                    )
                    html_cards = "".join(
                        _badge_materia(
                            m.get("clave", ""),
                            m.get("nombre", ""),
                            m.get("creditos", 0),
                            m.get("categoria", "")
                        )
                        for m in materias_sem
                    )
                    st.markdown(html_cards, unsafe_allow_html=True)
            st.divider()

        # ---------------------------------------------------------------
        # ANÁLISIS DE AVANCE POR SEMESTRE
        # ---------------------------------------------------------------
        st.subheader("📊 Análisis de avance por semestre")
        st.caption(
            "Se calcula el porcentaje de avance de cada semestre con la misma lógica que "
            "usa el sistema experto para determinar el semestre actual. "
            "Un semestre se considera superado cuando el avance es ≥ 75%."
        )

        # Construir sets de claves por categoría
        _mapa_lista = mapa_curricular if isinstance(mapa_curricular, list) else []
        _aprobadas_anal  = _aprobadas_mapa
        _en_curso_anal   = _en_curso_mapa
        _en_contacto_anal = _aprobadas_anal | _en_curso_anal

        # Separar EL por ciclo del mapa (no por corte numérico global)
        _el_plan_early = {
            str(m.get("clave", "")).strip().upper()
            for m in _mapa_lista
            if m.get("categoria") == "ELECCION_LIBRE" and m.get("ciclo", 0) <= 4
        }
        _el_plan_late = {
            str(m.get("clave", "")).strip().upper()
            for m in _mapa_lista
            if m.get("categoria") == "ELECCION_LIBRE" and m.get("ciclo", 0) >= 5
        }
        _preesp_plan = {
            str(m.get("clave", "")).strip().upper()
            for m in _mapa_lista if m.get("categoria") == "PREESPECIALIDAD"
        }
        _el_total_early_anal = len(_el_plan_early & _en_contacto_anal)
        _el_total_late_anal  = len(_el_plan_late  & _en_contacto_anal)
        _preesp_total_anal   = len(_preesp_plan   & _en_contacto_anal)

        filas_avance = []
        for _sem in range(1, 9):
            _mats_sem = [m for m in _mapa_lista if m.get("ciclo") == _sem]
            if not _mats_sem:
                continue

            _claves_sem = {str(m.get("clave", "")).strip().upper() for m in _mats_sem}
            _tiene_contacto = bool(_claves_sem & _en_contacto_anal)

            # Básicas del semestre (sin PID)
            _basicas_sem = {
                str(m.get("clave", "")).strip().upper()
                for m in _mats_sem
                if m.get("categoria") == "BASICA"
                and not str(m.get("clave", "")).strip().upper().startswith("PID")
            }
            _cursadas_basicas = len(_basicas_sem & _en_contacto_anal)
            _total_basicas = len(_basicas_sem)

            # Crédito EL: sems 1-4 simple (1 por sem, sin carry-over),
            # sems 5-8 acumulativo usando solo el excedente (late)
            if _sem <= 4:
                _el_credit = min(_el_total_early_anal, _sem) - min(_el_total_early_anal, _sem - 1)
                _el_recom  = 1
            else:
                _el_acum_prev = EL_ACUMULADAS_CICLO.get(_sem - 1, 0)
                _el_acum_curr = EL_ACUMULADAS_CICLO.get(_sem, 0)
                _el_credit    = min(_el_total_late_anal, _el_acum_curr) - min(_el_total_late_anal, _el_acum_prev)
                _el_recom     = EL_RECOMENDADAS_POR_CICLO.get(_sem, 0)

            # Crédito PREESP acumulativo
            _preesp_acum_prev = PREESP_ACUMULADAS_CICLO.get(_sem - 1, 0)
            _preesp_acum_curr = PREESP_ACUMULADAS_CICLO.get(_sem, 0)
            _preesp_credit    = min(_preesp_total_anal, _preesp_acum_curr) - min(_preesp_total_anal, _preesp_acum_prev)
            _preesp_recom     = PREESP_RECOMENDADAS_POR_CICLO.get(_sem, 0)

            _total_esperado  = _total_basicas + _el_recom + _preesp_recom
            _total_cursado   = _cursadas_basicas + _el_credit + _preesp_credit
            _porcentaje      = (_total_cursado / _total_esperado * 100) if _total_esperado > 0 else 0

            if not _tiene_contacto:
                _estado = "⬜ No iniciado"
            elif _porcentaje >= 75:
                _estado = "✅ Superado"
            else:
                _estado = "🔄 En curso"

            filas_avance.append({
                "Semestre": _sem,
                "Básicas cursadas": f"{_cursadas_basicas} / {_total_basicas}",
                "EL (crédito / recomendadas)": f"{_el_credit} / {_el_recom}",
                "Preesp (crédito / recomendadas)": f"{_preesp_credit} / {_preesp_recom}",
                "Total (cursado / esperado)": f"{_total_cursado} / {_total_esperado}",
                "Avance": round(_porcentaje, 1),
                "Estado": _estado,
            })

        if filas_avance:
            df_avance = pd.DataFrame(filas_avance)

            def _color_avance(row):
                pct = row["Avance"]
                estado = row["Estado"]
                if estado == "⬜ No iniciado":
                    return [""] * len(row)
                elif pct >= 75:
                    return ["background-color: #d1fae5"] * len(row)
                elif pct >= 50:
                    return ["background-color: #fef3c7"] * len(row)
                else:
                    return ["background-color: #fee2e2"] * len(row)

            st.dataframe(
                df_avance.style
                    .apply(_color_avance, axis=1)
                    .format({"Avance": "{:.1f}%"}),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown(
                "**Interpretación:** "
                "🟢 Verde = semestre superado (≥ 75%) · "
                "🟡 Amarillo = en progreso (50–74%) · "
                "🔴 Rojo = por debajo del umbral (< 50%) · "
                "⬜ Gris = no iniciado."
            )
            st.info(
                "ℹ️ El avance incluye: **Básicas** del semestre + **crédito acumulativo de Elección Libre** "
                "(excedentes de semestres anteriores se transfieren) + **crédito acumulativo de Preespecialidad** "
                "(ídem). Las materias PID (Prácticas Profesionales) no se cuentan aquí."
            )

        # ---------------------------------------------------------------
        # TABLA DE VERIFICACIÓN: materias cargadas reales por semestre
        # ---------------------------------------------------------------
        st.subheader("🔍 Verificación: materias cargadas por semestre")
        st.caption(
            "Conteo real de materias que el alumno tiene en contacto (aprobadas, en curso o recursando) "
            "por semestre, sin ningún criterio acumulativo. Sirve para verificar que los datos se registran correctamente."
        )

        filas_verif = []
        _el_acum_real    = 0  # acumulado real de EL del alumno desde sem 5
        _preesp_acum_real = 0  # acumulado real de PREESP del alumno desde sem 5
        for _sem in range(1, 9):
            _mats_sem = [m for m in _mapa_lista if m.get("ciclo") == _sem]
            if not _mats_sem:
                continue

            _basicas_verif = {
                str(m.get("clave", "")).strip().upper()
                for m in _mats_sem
                if m.get("categoria") == "BASICA"
                and not str(m.get("clave", "")).strip().upper().startswith("PID")
            }
            _el_verif = {
                str(m.get("clave", "")).strip().upper()
                for m in _mats_sem
                if m.get("categoria") == "ELECCION_LIBRE"
            }
            _preesp_verif = {
                str(m.get("clave", "")).strip().upper()
                for m in _mats_sem
                if m.get("categoria") == "PREESPECIALIDAD"
            }

            _n_basicas = len(_basicas_verif & _en_contacto_anal)
            _n_el      = len(_el_verif & _en_contacto_anal)
            _n_preesp  = len(_preesp_verif & _en_contacto_anal) if _sem >= 5 else 0

            # Acumulados reales desde sem 5
            if _sem >= 5:
                _el_acum_real     += _n_el
                _preesp_acum_real += _n_preesp

            filas_verif.append({
                "Semestre":                    _sem,
                "Básicas cargadas":            _n_basicas,
                "Total básicas plan":          len(_basicas_verif),
                "EL cargadas":                 _n_el,
                "Total EL plan":               len(_el_verif),
                "EL acum. real alumno":        _el_acum_real if _sem >= 5 else "—",
                "EL_RECOMENDADAS_POR_CICLO":   EL_RECOMENDADAS_POR_CICLO.get(_sem, 0),
                "EL_ACUMULADAS_CICLO (target)": EL_ACUMULADAS_CICLO.get(_sem, 0),
                "Preesp cargadas":             _n_preesp if _sem >= 5 else "—",
                "Total preesp plan":           len(_preesp_verif) if _sem >= 5 else "—",
                "Preesp acum. real alumno":    _preesp_acum_real if _sem >= 5 else "—",
                "PREESP_ACUMULADAS_CICLO (target)": PREESP_ACUMULADAS_CICLO.get(_sem, "—"),
            })

        if filas_verif:
            st.dataframe(
                pd.DataFrame(filas_verif),
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("""
<div class="nav-cta-banner">
  <div class="nav-cta-label">🔬 Siguiente paso</div>
  <div class="nav-cta-desc">Revisa el diagnóstico de captura para validar que el sistema leyó correctamente los datos.</div>
</div>""", unsafe_allow_html=True)
        st.markdown('<div class="nav-btn-attached">', unsafe_allow_html=True)
        if st.button("🔬  Ver Diagnóstico de Datos", key="btn_next_pruebas", type="primary", use_container_width=True):
            st.switch_page(st.Page(_pg_pruebas, title="Pruebas", icon=":material/science:"))
        st.markdown('</div>', unsafe_allow_html=True)

    def _pg_pruebas():
        st.header("🔬 Diagnóstico de captura de datos")
        st.caption("Esta pestaña muestra exactamente cómo el sistema interpreta los datos del Kardex y el Historial Académico, y cómo asigna ciclos a cada materia.")

        # --- Construir tabla de diagnóstico ---
        mapa_dict = {m["clave"]: m for m in mapa_curricular} if mapa_curricular else {}

        filas_diag = []
        for _, row in historial_filtrado.iterrows():
            clave = str(row.get("clave", "")).strip().upper()
            mat_mapa = mapa_dict.get(clave, {})
            ciclo_parser = row.get("ciclo", None)
            ciclo_mapa   = mat_mapa.get("ciclo", None)
            en_mapa      = clave in mapa_dict

            filas_diag.append({
                "Clave":              clave,
                "Nombre":             row.get("nombre", "") or mat_mapa.get("nombre", ""),
                "Estatus":            row.get("estatus", ""),
                "Calificación":       row.get("calificacion", ""),
                "Periodo":            row.get("periodo", ""),
                "Ciclo (parser)": int(ciclo_parser) if pd.notna(ciclo_parser) and ciclo_parser not in ["", None] else "—",
                "Ciclo (mapa oficial)": int(ciclo_mapa) if ciclo_mapa is not None else "❌ No en mapa",
                "Ciclo anual (mapa)": int(mat_mapa["ciclo_anual"]) if mat_mapa.get("ciclo_anual") is not None else "—",
                "Categoría":          mat_mapa.get("categoria", "—"),
                "¿En mapa?": "✅" if en_mapa else "❌",
            })

        df_diag = pd.DataFrame(filas_diag)

        st.subheader("📋 Tabla: Historial procesado vs Mapa Curricular")
        st.caption("Compara el ciclo que asigna el parser con el ciclo oficial del mapa. Discrepancias aquí explican errores en el sistema experto.")

        # Colorear filas donde los ciclos no coinciden
        def highlight_mismatch(row):
            try:
                cp = int(row["Ciclo (parser)"])
                cm = int(row["Ciclo (mapa oficial)"])
                if cp != cm:
                    return ["background-color: #fff3cd"] * len(row)
            except Exception:
                pass
            if row["¿En mapa?"] == "❌":
                return ["background-color: #f8d7da"] * len(row)
            return [""] * len(row)

        st.dataframe(
            df_diag.style.apply(highlight_mismatch, axis=1),
            use_container_width=True,
            height=400,
        )

        # Leyenda
        st.caption("🟡 Amarillo = ciclo del parser difiere del ciclo oficial en el mapa  |  🔴 Rojo = materia no encontrada en el mapa curricular")

        discrepancias = 0
        no_en_mapa = 0
        for r in filas_diag:
            if r["¿En mapa?"] == "❌":
                no_en_mapa += 1
            else:
                try:
                    if int(r["Ciclo (parser)"]) != int(r["Ciclo (mapa oficial)"]):
                        discrepancias += 1
                except Exception:
                    pass

        col_d1, col_d2, col_d3 = st.columns(3)
        with col_d1:
            st.metric("Total materias procesadas", len(df_diag))
        with col_d2:
            st.metric("Discrepancias de ciclo", discrepancias, delta=None if discrepancias == 0 else f"-{discrepancias} incorrectas", delta_color="inverse")
        with col_d3:
            st.metric("No encontradas en mapa", no_en_mapa, delta_color="inverse")

        st.divider()

        # --- Tabla resumen por ciclo (perspectiva del sistema experto) ---
        st.subheader("📊 Resumen por ciclo semestral (como lo ve el Sistema Experto)")
        st.caption("El sistema experto usa los ciclos del mapa oficial (1-8 semestrales). Se avanza de ciclo cuando se aprueba ≥75% del ciclo actual.")

        aprobadas_set = set(df_diag.loc[df_diag["Estatus"] == "APROBADA", "Clave"].tolist())
        en_curso_set  = set(df_diag.loc[df_diag["Estatus"].isin(["EN_CURSO", "RECURSANDO"]), "Clave"].tolist())

        filas_ciclo = []
        for ciclo_n in range(1, 9):
            mats_c = [m for m in mapa_curricular if m.get("ciclo") == ciclo_n]
            if not mats_c:
                continue
            claves_c  = {m["clave"] for m in mats_c}
            aprobadas_c = claves_c & aprobadas_set
            en_curso_c  = claves_c & en_curso_set
            contacto_c  = claves_c & (aprobadas_set | en_curso_set)
            pendientes_c = claves_c - aprobadas_set - en_curso_set
            pct = len(aprobadas_c) / len(mats_c) * 100 if mats_c else 0
            supera_75 = pct >= 75
            tiene_contacto = len(contacto_c) > 0
            filas_ciclo.append({
                "Ciclo semestral": ciclo_n,
                "Total materias (mapa)": len(mats_c),
                "✅ Aprobadas": len(aprobadas_c),
                "📖 En curso": len(en_curso_c),
                "⏳ Pendientes": len(pendientes_c),
                "% Aprobado": f"{pct:.1f}%",
                "¿Supera 75%?": "✅ SÍ" if supera_75 else "❌ NO",
                "¿Tiene contacto?": "✅" if tiene_contacto else "❌",
            })

        df_ciclos = pd.DataFrame(filas_ciclo)

        def highlight_ciclo(row):
            if row["¿Supera 75%?"] == "✅ SÍ" and row["¿Tiene contacto?"] == "✅":
                return ["background-color: #d4edda"] * len(row)  # verde: ciclo superado
            if row["¿Tiene contacto?"] == "✅":
                return ["background-color: #cce5ff"] * len(row)  # azul: ciclo actual
            return [""] * len(row)

        st.dataframe(
            df_ciclos.style.apply(highlight_ciclo, axis=1),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("🟢 Verde = ciclo superado (≥75% aprobado)  |  🔵 Azul = ciclo actual (tiene contacto pero <75%)  |  Sin color = ciclo no iniciado")

        st.divider()

        # --- Materias del historial NO encontradas en el mapa ---
        df_no_mapa = df_diag[df_diag["¿En mapa?"] == "❌"][["Clave", "Nombre", "Estatus", "Ciclo (parser)"]]
        if not df_no_mapa.empty:
            st.subheader("⚠️ Materias del historial NO encontradas en el mapa curricular")
            st.caption("Estas materias fueron parseadas pero el sistema experto no las reconoce (pueden ser equivalencias, propedéuticos u otras claves).")
            st.dataframe(df_no_mapa, use_container_width=True, hide_index=True)
        else:
            st.success("✅ Todas las materias del historial están en el mapa curricular.")

        st.markdown("""
<div class="nav-cta-banner">
  <div class="nav-cta-label">📊 Siguiente paso</div>
  <div class="nav-cta-desc">Explora la oferta académica disponible y los horarios de las materias candidatas.</div>
</div>""", unsafe_allow_html=True)
        st.markdown('<div class="nav-btn-attached">', unsafe_allow_html=True)
        if st.button("📊  Ver Oferta & Candidatas", key="btn_next_oferta", type="primary", use_container_width=True):
            st.switch_page(st.Page(_pg_oferta, title="Oferta & Candidatas", icon=":material/insights:"))
        st.markdown('</div>', unsafe_allow_html=True)

    def _pg_oferta():
        st.header("📊 Oferta Académica y Disponibilidad")
        st.caption("Visualiza las materias del plan curricular con sus secciones y horarios disponibles en la oferta académica seleccionada.")

        from services.oferta_service import cargar_oferta_csv, parsear_horario_seccion
        _carpeta_oferta2 = Path(__file__).resolve().parent.parent / "agents" / "OfertaAcademica"

        opciones_oferta_tab = {
            "Prueba Oferta Primavera (193)": str(_carpeta_oferta2 / "IRSecciones_193.csv"),
            "Prueba Oferta Verano (194)": str(_carpeta_oferta2 / "IR_194_Limpio.csv"),
            "Prueba Oferta Otoño (195)": str(_carpeta_oferta2 / "IR_195_Limpio.csv"),
        }
        oferta_sel_tab = st.selectbox(
            "📂 Selecciona la oferta académica",
            list(opciones_oferta_tab.keys()),
            key="selector_oferta_tab",
        )
        df_oferta_tab = cargar_oferta_csv(ruta_csv=opciones_oferta_tab[oferta_sel_tab])

        def horario_a_texto(horario):
            if not horario:
                return "Sin horario"
            partes = []
            for b in horario:
                partes.append(f"{b['dia']} {b['inicio']:02d}:00–{b['fin']:02d}:00 ({b['espacio']})")
            return " | ".join(partes)

        # ── SECCIÓN 1: Todas las del mapa curricular con oferta ──────────────
        st.subheader("📋 Materias del plan curricular con oferta disponible")
        st.caption("Materias del mapa curricular IDeIO 2021 que tienen secciones en la oferta del periodo actual.")

        if df_oferta_tab.empty:
            st.error("No se pudo cargar la oferta académica.")
        elif not mapa_curricular:
            st.error("No se cargó el mapa curricular.")
        else:
            claves_mapa_dict = {m["clave"]: m for m in mapa_curricular}
            df_mapa_oferta = df_oferta_tab[df_oferta_tab["Clave"].isin(claves_mapa_dict.keys())].copy()

            filas_mapa = []
            for _, row in df_mapa_oferta.iterrows():
                clave = row["Clave"]
                info = claves_mapa_dict.get(clave, {})
                horario = parsear_horario_seccion(row)
                filas_mapa.append({
                    "Clave": clave,
                    "Materia": info.get("nombre", str(row.get("Asignatura", ""))),
                    "Semestre": info.get("ciclo", "—"),
                    "Categoría": info.get("categoria", "—"),
                    "Créditos": info.get("creditos", "—"),
                    "Sección": int(row.get("Seccion", 0) or 0),
                    "Profesor": str(row.get("Profesor", "")).strip(),
                    "Cupo": int(row.get("Cupo", 0) or 0),
                    "Inscritos": int(row.get("Inscritos", 0) or 0),
                    "Horario": horario_a_texto(horario),
                    "Modalidad": str(row.get("Modalidad Desc", "")).strip(),
                })

            df_mapa_show = pd.DataFrame(filas_mapa)
            if df_mapa_show.empty:
                st.warning("Ninguna materia del mapa curricular tiene secciones en la oferta actual.")
            else:
                st.success(f"Se encontraron **{len(df_mapa_show)} secciones** de **{df_mapa_show['Clave'].nunique()} materias** del plan curricular en la oferta.")
                semestres_disp = sorted([s for s in df_mapa_show["Semestre"].dropna().unique() if s != "—"])
                semestre_sel = st.multiselect(
                    "Filtrar por semestre:", semestres_disp, default=semestres_disp, key="oferta_sem_filter"
                )
                df_mapa_filtrada = df_mapa_show[df_mapa_show["Semestre"].isin(semestre_sel)] if semestre_sel else df_mapa_show
                st.dataframe(
                    df_mapa_filtrada.sort_values(["Semestre", "Clave", "Sección"]),
                    use_container_width=True, hide_index=True, height=420,
                )

        st.divider()

        # ── SECCIÓN 2: Candidatas del sistema experto con oferta ─────────────
        st.subheader("🧠 Materias que el alumno puede tomar (Sistema Experto)")
        st.caption("Materias recomendadas por el Sistema Experto que tienen secciones disponibles en la oferta del periodo actual, con sus días y horarios.")

        if "resultado_experto" not in st.session_state or not st.session_state.resultado_experto:
            st.info("Primero ve a la pestaña **Sistema Experto** para generar las materias candidatas.")
        elif df_oferta_tab.empty:
            st.error("No se pudo cargar la oferta académica.")
        else:
            resultado_exp2 = st.session_state.resultado_experto
            candidatas_det2 = resultado_exp2.get("candidatas_detalles", [])

            if not candidatas_det2:
                st.warning("No hay materias candidatas del Sistema Experto.")
            else:
                cand_lookup2 = {d["clave"].upper(): d for d in candidatas_det2}
                df_cand_oferta = df_oferta_tab[df_oferta_tab["Clave"].isin(cand_lookup2.keys())].copy()

                filas_cand = []
                for _, row in df_cand_oferta.iterrows():
                    clave = row["Clave"]
                    info = cand_lookup2.get(clave, {})
                    horario = parsear_horario_seccion(row)
                    if not horario:
                        continue
                    # Turno: matutino si la clase INICIA antes de las 14:00
                    # (clases de 13-15 siguen siendo matutinas porque empiezan antes de las 2 PM)
                    _inicio_min = min((b["inicio"] for b in horario), default=0)
                    _turno = "☀️ Matutino" if _inicio_min < 14 else "🌙 Vespertino"
                    filas_cand.append({
                        "Prioridad": info.get("prioridad", "—"),
                        "Nivel": info.get("nivel", "—"),
                        "Clave": clave,
                        "Materia": info.get("nombre", str(row.get("Asignatura", ""))),
                        "Semestre": info.get("ciclo", "—"),
                        "Créditos": info.get("creditos", "—"),
                        "Sección": int(row.get("Seccion", 0) or 0),
                        "Turno": _turno,
                        "Profesor": str(row.get("Profesor", "")).strip(),
                        "Cupo": int(row.get("Cupo", 0) or 0),
                        "Inscritos": int(row.get("Inscritos", 0) or 0),
                        "Lugares disponibles": max(0, int(row.get("Cupo", 0) or 0) - int(row.get("Inscritos", 0) or 0)),
                        "Horario": horario_a_texto(horario),
                    })

                df_cand_show = pd.DataFrame(filas_cand)
                if df_cand_show.empty:
                    st.warning("Ninguna materia candidata tiene secciones con horario válido en la oferta actual.")
                else:
                    n_mats = df_cand_show["Clave"].nunique()
                    n_secs = len(df_cand_show)
                    st.success(f"**{n_mats} materias** candidatas tienen secciones en la oferta. Total: **{n_secs} secciones** disponibles.")
                    df_cand_show = df_cand_show.sort_values(["Prioridad", "Semestre", "Clave", "Sección"])

                    _tab_mat, _tab_vesp = st.tabs(["☀️ Matutino", "🌙 Vespertino"])
                    with _tab_mat:
                        _df_mat = df_cand_show[df_cand_show["Turno"] == "☀️ Matutino"].drop(columns=["Turno"])
                        if _df_mat.empty:
                            st.info("No hay secciones matutinas disponibles para las materias candidatas.")
                        else:
                            st.dataframe(_df_mat, use_container_width=True, hide_index=True, height=420)
                    with _tab_vesp:
                        _df_vesp = df_cand_show[df_cand_show["Turno"] == "🌙 Vespertino"].drop(columns=["Turno"])
                        if _df_vesp.empty:
                            st.info("No hay secciones vespertinas disponibles para las materias candidatas.")
                        else:
                            st.dataframe(_df_vesp, use_container_width=True, hide_index=True, height=420)
                    st.caption("Prioridad 1 = más urgente de cursar | Matutino: clases que inician antes de las 14:00 | Solo se muestran secciones con horario registrado en la oferta.")

                    import streamlit.components.v1 as _components_v1

                    _dias_cal = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado"]
                    _hora_min = 7
                    _hora_max = 21
                    _px_h = 60          # píxeles por hora
                    _dia_w = 150        # px de ancho por día
                    _t_col = 52         # px columna de horas

                    # Asignar un color HSL único a cada clave
                    _claves_cal = sorted(df_cand_show["Clave"].unique())
                    _colores_cal = {
                        c: f"hsl({(i * 53 + 15) % 360}, 65%, 58%)"
                        for i, c in enumerate(_claves_cal)
                    }

                    # Recopilar bloques por día con datos completos
                    _bloques_dia = {d: [] for d in _dias_cal}
                    for _, _row_c in df_cand_oferta.iterrows():
                        _ck = _row_c["Clave"]
                        if _ck not in cand_lookup2:
                            continue
                        _ci = cand_lookup2[_ck]
                        _cn = _ci.get("nombre", str(_row_c.get("Asignatura", "")))
                        _cs = int(_row_c.get("Seccion", 0) or 0)
                        for _blq in parsear_horario_seccion(_row_c):
                            _d = _blq["dia"]
                            if _d not in _bloques_dia:
                                continue
                            _bloques_dia[_d].append({
                                "inicio": _blq["inicio"],
                                "fin":    _blq["fin"],
                                "clave":  _ck,
                                "nombre": _cn,
                                "seccion": _cs,
                                "espacio": _blq["espacio"],
                                "color":  _colores_cal.get(_ck, "#6c8ebf"),
                            })

                    # Algoritmo de asignación de sub-columnas para solapamientos
                    def _asignar_cols(bloques):
                        if not bloques:
                            return []
                        sb = sorted(bloques, key=lambda b: (b["inicio"], b["fin"]))
                        col_ends = []
                        assigned = []
                        for b in sb:
                            placed = False
                            for ci, ce in enumerate(col_ends):
                                if b["inicio"] >= ce:
                                    col_ends[ci] = b["fin"]
                                    assigned.append({**b, "col_idx": ci})
                                    placed = True
                                    break
                            if not placed:
                                assigned.append({**b, "col_idx": len(col_ends)})
                                col_ends.append(b["fin"])
                        # Calcular concurrentes reales para cada bloque
                        result = []
                        for i, ab in enumerate(assigned):
                            conc = sum(
                                1 for j, ob in enumerate(assigned)
                                if i != j
                                and ab["inicio"] < ob["fin"]
                                and ob["inicio"] < ab["fin"]
                            ) + 1
                            result.append({**ab, "n_conc": conc})
                        return result

                    # Leyenda de colores
                    _leg = (
                        "<div style='display:flex;flex-wrap:wrap;gap:6px;"
                        "margin-bottom:10px;font-family:sans-serif;'>"
                    )
                    for _cv, _col in _colores_cal.items():
                        _nm_leg = cand_lookup2.get(_cv, {}).get("nombre", _cv)
                        _nm_leg = (_nm_leg[:24] + "…") if len(_nm_leg) > 24 else _nm_leg
                        _leg += (
                            f"<span title='{_nm_leg}' style='background:{_col};color:#fff;"
                            f"padding:3px 10px;border-radius:12px;font-size:11px;"
                            f"text-shadow:0 1px 2px rgba(0,0,0,.45);cursor:default;'>"
                            f"{_cv}</span>"
                        )
                    _leg += "</div>"

                    # CSS del calendario
                    _total_rows = _hora_max - _hora_min
                    _cal_h = _total_rows * _px_h
                    _css = f"""<style>
.wc{{font-family:sans-serif;overflow-x:auto;min-width:600px;}}
.wc-hdr{{display:flex;background:#f0f2f6;border:1px solid #ccc;border-radius:8px 8px 0 0;border-bottom:none;}}
.wc-hdr-t{{width:{_t_col}px;flex-shrink:0;padding:7px 4px;font-size:11px;color:#999;text-align:right;}}
.wc-hdr-d{{width:{_dia_w}px;flex-shrink:0;padding:7px;font-weight:600;font-size:12px;text-align:center;border-left:1px solid #ccc;}}
.wc-grid{{display:flex;border:1px solid #ccc;border-radius:0 0 8px 8px;overflow:hidden;}}
.wc-tcol{{width:{_t_col}px;flex-shrink:0;position:relative;height:{_cal_h}px;background:#fafafa;border-right:1px solid #ccc;}}
.wc-tlab{{position:absolute;right:5px;font-size:10px;color:#aaa;transform:translateY(-6px);user-select:none;}}
.wc-dcol{{width:{_dia_w}px;flex-shrink:0;position:relative;height:{_cal_h}px;border-left:1px solid #eee;background:#fff;}}
.wc-hline{{position:absolute;left:0;right:0;border-top:1px solid #f0f0f0;pointer-events:none;}}
.wc-blk{{position:absolute;border-radius:4px;overflow:hidden;font-size:10.5px;color:#fff;
  text-shadow:0 1px 2px rgba(0,0,0,.55);padding:3px 5px;box-sizing:border-box;
  border:1px solid rgba(255,255,255,.2);cursor:default;line-height:1.35;}}
.wc-blk:hover{{filter:brightness(1.2);z-index:9999!important;
  outline:2px solid rgba(255,255,255,.8);box-shadow:0 2px 8px rgba(0,0,0,.3);}}
</style>"""

                    # Construir HTML
                    _html = [_css, "<div class='wc'>", _leg,
                             "<div class='wc-hdr'>",
                             f"<div class='wc-hdr-t'>Hora</div>"]
                    for _d in _dias_cal:
                        _html.append(f"<div class='wc-hdr-d'>{_d}</div>")
                    _html.append("</div><div class='wc-grid'>")

                    # Columna de horas
                    _html.append(f"<div class='wc-tcol'>")
                    for _h in range(_hora_min, _hora_max + 1):
                        _tp = (_h - _hora_min) * _px_h
                        _html.append(f"<div class='wc-tlab' style='top:{_tp}px;'>{_h:02d}:00</div>")
                    _html.append("</div>")

                    # Columnas por día
                    for _d in _dias_cal:
                        _bqs = _asignar_cols(_bloques_dia.get(_d, []))
                        _html.append("<div class='wc-dcol'>")
                        # Líneas de hora
                        for _hi in range(_total_rows + 1):
                            _html.append(f"<div class='wc-hline' style='top:{_hi*_px_h}px;'></div>")
                        # Bloques de materias
                        for _b in _bqs:
                            _top_b  = (_b["inicio"] - _hora_min) * _px_h + 1
                            _ht_b   = (_b["fin"] - _b["inicio"]) * _px_h - 3
                            _w_pct  = 100.0 / _b["n_conc"]
                            _lft_pct = _b["col_idx"] * _w_pct
                            _tip = (
                                f"{_b['nombre']} | {_b['clave']} "
                                f"Sec.{_b['seccion']} | "
                                f"{_b['inicio']:02d}:00\u2013{_b['fin']:02d}:00 | "
                                f"{_b['espacio']}"
                            ).replace("'", "&#39;").replace('"', "&quot;")
                            _label = _b["clave"]
                            _html.append(
                                f"<div class='wc-blk' "
                                f"style='top:{_top_b}px;height:{_ht_b}px;"
                                f"left:{_lft_pct:.2f}%;width:{_w_pct:.2f}%;"
                                f"background:{_b['color']};z-index:{_b['col_idx']+1};'"
                                f" title='{_tip}'>"
                                f"<strong>{_label}</strong>"
                                f"</div>"
                            )
                        _html.append("</div>")

                    _html.append("</div></div>")  # wc-grid + wc
                    _components_v1.html("".join(_html), height=_cal_h + 170, scrolling=True)

                    # ── SECCIÓN 3: Lista de materias por día ────────────────
                    st.divider()
                    st.subheader("📋 Materias disponibles por día")
                    st.caption("Secciones con horario válido, agrupadas por día de la semana.")

                    _dias_lista = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado"]
                    _cols_dias = st.columns(3)
                    _dia_labels = {
                        "Lunes": "🟦 Lunes", "Martes": "🟩 Martes",
                        "Miercoles": "🟨 Miércoles", "Jueves": "🟧 Jueves",
                        "Viernes": "🟥 Viernes", "Sabado": "🟪 Sábado",
                    }
                    for _di, _dia_n in enumerate(_dias_lista):
                        _bloqs_dia = _bloques_dia.get(_dia_n, [])
                        with _cols_dias[_di % 3]:
                            st.markdown(f"**{_dia_labels[_dia_n]}**")
                            if not _bloqs_dia:
                                st.caption("Sin secciones")
                            else:
                                _bloqs_sorted = sorted(_bloqs_dia, key=lambda b: (b["inicio"], b["nombre"]))
                                for _bb in _bloqs_sorted:
                                    st.markdown(
                                        f"- `{_bb['clave']}` Sec.{_bb['seccion']} &nbsp;"
                                        f"**{_bb['inicio']:02d}:00–{_bb['fin']:02d}:00**  \n"
                                        f"  _{_bb['nombre']}_  · {_bb['espacio']}"
                                    )

                    # ── SECCIÓN 4: Análisis de compatibilidad ───────────────
                    st.divider()
                    st.subheader("🔍 Análisis de compatibilidad entre materias candidatas")
                    st.caption(
                        "Detecta cuántas materias pueden coexistir en un horario sin choques. "
                        "Útil para entender por qué el optimizador no llega a 7 materias."
                    )

                    # Agrupar bloques por clave: unión de todas sus secciones
                    _horarios_por_clave = {}
                    for _, _rr in df_cand_oferta.iterrows():
                        _ck2 = _rr["Clave"]
                        if _ck2 not in cand_lookup2:
                            continue
                        for _blq2 in parsear_horario_seccion(_rr):
                            _horarios_por_clave.setdefault(_ck2, []).append({
                                "seccion": int(_rr.get("Seccion", 0) or 0),
                                **_blq2,
                            })

                    _claves_ana = sorted(_horarios_por_clave.keys())

                    # Matriz de conflicto: True si TODAS las combinaciones de secciones
                    # de dos materias chocan (nunca se pueden tomar juntas)
                    def _hay_choque_bloques(ba, bb):
                        return ba["dia"] == bb["dia"] and ba["inicio"] < bb["fin"] and bb["inicio"] < ba["fin"]

                    def _secciones_de(clave):
                        """Agrupa bloques por seccion para una clave."""
                        secs = {}
                        for bl in _horarios_por_clave.get(clave, []):
                            secs.setdefault(bl["seccion"], []).append(bl)
                        return list(secs.values())

                    def _siempre_chocan(cA, cB):
                        """True si no existe ningún par de secciones de cA y cB compatibles."""
                        for sa in _secciones_de(cA):
                            for sb in _secciones_de(cB):
                                choca = any(
                                    _hay_choque_bloques(ba, bb)
                                    for ba in sa for bb in sb
                                )
                                if not choca:
                                    return False
                        return True

                    def _a_veces_chocan(cA, cB):
                        """True si al menos algún par de secciones choca."""
                        for sa in _secciones_de(cA):
                            for sb in _secciones_de(cB):
                                if any(_hay_choque_bloques(ba, bb) for ba in sa for bb in sb):
                                    return True
                        return False

                    # Contar conflictos por materia
                    _fila_conf = []
                    _siempre_con = {c: 0 for c in _claves_ana}
                    _aveces_con = {c: 0 for c in _claves_ana}
                    for _i2, _cA in enumerate(_claves_ana):
                        for _cB in _claves_ana[_i2+1:]:
                            if _siempre_chocan(_cA, _cB):
                                _siempre_con[_cA] += 1
                                _siempre_con[_cB] += 1
                            elif _a_veces_chocan(_cA, _cB):
                                _aveces_con[_cA] += 1
                                _aveces_con[_cB] += 1

                    for _ck3 in _claves_ana:
                        _nm3 = cand_lookup2.get(_ck3, {}).get("nombre", _ck3)
                        _pr3 = cand_lookup2.get(_ck3, {}).get("prioridad", "-")
                        _ns3 = len(_secciones_de(_ck3))
                        _fila_conf.append({
                            "Clave": _ck3,
                            "Materia": _nm3,
                            "Prioridad": _pr3,
                            "Secciones": _ns3,
                            "⛔ Siempre choca con": _siempre_con[_ck3],
                            "⚠️ A veces choca con": _aveces_con[_ck3],
                            "✅ Compatibles con": len(_claves_ana) - 1 - _siempre_con[_ck3] - _aveces_con[_ck3],
                        })

                    df_conf = pd.DataFrame(_fila_conf).sort_values(["Prioridad", "⛔ Siempre choca con"], ascending=[True, False])

                    # Colorear según conflictos permanentes
                    def _color_conf(row):
                        if row["⛔ Siempre choca con"] >= len(_claves_ana) // 2:
                            return ["background-color:#f8d7da"] * len(row)
                        if row["⛔ Siempre choca con"] > 0:
                            return ["background-color:#fff3cd"] * len(row)
                        return ["background-color:#d4edda"] * len(row)

                    st.dataframe(
                        df_conf.style.apply(_color_conf, axis=1),
                        use_container_width=True, hide_index=True,
                    )
                    st.caption(
                        "🟢 Verde = sin conflictos permanentes (siempre hay al menos una sección compatible) · "
                        "🟡 Amarillo = conflicto con alguna materia en todas sus secciones · "
                        "🔴 Rojo = muchos conflictos permanentes, reduce drásticamente las combinaciones posibles"
                    )

                    # Cota superior: máximo de materias sin ningún conflicto permanente
                    _libres = [c for c in _claves_ana if _siempre_con[c] == 0]
                    _con_conflicto = [c for c in _claves_ana if _siempre_con[c] > 0]

                    with st.expander("📐 ¿Por qué el optimizador no llega a 7 materias?", expanded=True):
                        _c1, _c2, _c3 = st.columns(3)
                        _c1.metric("Materias candidatas totales", len(_claves_ana))
                        _c2.metric("Sin conflicto permanente", len(_libres))
                        _c3.metric("Con conflicto permanente", len(_con_conflicto))

                        st.markdown(
                            f"De las **{len(_claves_ana)}** materias candidatas con secciones en la oferta:\n\n"
                            f"- **{len(_libres)}** tienen al menos una sección compatible con el resto "
                            f"(son candidatas reales al horario).\n"
                            f"- **{len(_con_conflicto)}** chocan permanentemente con alguna otra materia "
                            f"(sin importar qué sección elijas, siempre habrá conflicto con al menos otra materia).\n\n"
                            f"Esto no impide tomarlas individualmente, pero **reduce el espacio de horarios válidos** "
                            f"exponencialmente. Además, para que quepan **7 materias** simultáneamente sin choque, "
                            f"se necesita que las 7 secciones elegidas no se crucen en ninguna hora/día — "
                            f"una condición muy restrictiva dado el horario concentrado de la oferta 193."
                        )

                        if _con_conflicto:
                            st.markdown("**Materias con conflicto permanente:**")
                            for _cc in sorted(_con_conflicto):
                                _nm_cc = cand_lookup2.get(_cc, {}).get("nombre", _cc)
                                st.markdown(f"- `{_cc}` — {_nm_cc} (choca permanentemente con {_siempre_con[_cc]} materia(s))")

    # ── Configurar navegación por sidebar ────────────────────────────────────
    pg = st.navigation([
        st.Page(_pg_inicio,   title="Cómo usar el sistema",            icon=":material/home:"),
        st.Page(_pg_historia, title="Situación Académica",             icon=":material/history_edu:"),
        st.Page(_pg_experto,  title="Materias Candidatas para Cargar", icon=":material/psychology:"),
        st.Page(_pg_cargas,   title="Generador de Cargas",             icon=":material/calendar_month:"),
        st.Page(_pg_mapa,     title="Mapa Curricular",                 icon=":material/map:"),
        st.Page(_pg_pruebas,  title="Pruebas",                         icon=":material/science:"),
        st.Page(_pg_oferta,   title="Oferta & Candidatas",             icon=":material/insights:"),
    ], position="sidebar")
    pg.run()

    _render_agente_chat()


if __name__ == "__main__":
    main()
