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
    tiempo_max_años = 8.0 + min(cantidad, max_permitidos) * 0.5
    semestres_max = 16 + min(cantidad, max_permitidos)

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
                elif clave in ["ID3415", "ID3416", "ID3417", "ID3418", "ID3419"]:
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
            elif clave in ["ID3415", "ID3416", "ID3417", "ID3418", "ID3419"]:
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
                    elif clave in ["ID3415", "ID3416", "ID3417", "ID3418", "ID3419"]:
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


def main():
    """Función principal de la aplicación"""

    st.title("📊 Reporte de Estado Académico")
    st.markdown("---")

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuración")

        # ── PASO 1: Subir Historial Académico (PRIMERO) ──
        st.subheader("📄 Paso 1: Historial Académico")
        st.caption("Sube primero el historial académico. Es la fuente de verdad para materias aprobadas.")
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

                        # Marcar este archivo como ya procesado
                        st.session_state._historial_file_id = historial_file.file_id

                        n_aprobadas = len(aprobadas)
                        n_total = len(historial_parser.materias)

                    st.success(f"✅ Historial procesado: {n_total} materias, {n_aprobadas} aprobadas")
                    st.info(f"📊 Créditos: {historial_parser.creditos_acumulados}/{historial_parser.creditos_totales}")
                    if historial_parser.nivel_ingles_texto:
                        st.info(f"🇬🇧 Inglés aprobado: {historial_parser.nivel_ingles_texto} ({len(historial_parser.codigos_ingles_aprobados)} niveles auto-aprobados)")
                except Exception as e:
                    import traceback
                    st.error(f"❌ Error al procesar historial: {str(e)}")
                    st.code(traceback.format_exc())

        # Mostrar estado del historial
        if "aprobadas_historial" in st.session_state:
            n_apr = len(st.session_state.aprobadas_historial)
            st.caption(f"✅ Historial cargado: {n_apr} materias aprobadas")
        else:
            st.warning("⚠️ Sube el historial académico primero")

        st.markdown("---")

        # ── PASO 2: Subir Kardex (DESPUÉS) ──
        st.subheader("📄 Paso 2: Kardex")
        st.caption("El kardex agrega detalle de periodos, intentos y materias en curso.")

        pdf_file = st.file_uploader(
            "Cargar Kardex (PDF)",
            type="pdf",
            help="Selecciona el archivo PDF del kardex del estudiante"
        )

        if pdf_file is not None:
            if "aprobadas_historial" not in st.session_state:
                st.warning("⚠️ Se recomienda subir el historial académico antes del kardex para mejores resultados.")

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

                    # Limpiar archivo temporal
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

                    n_aprobadas_final = (historial_combinado["estatus"] == "APROBADA").sum()
                    st.success("✅ Kardex procesado y combinado con historial")
                    st.info(f"📚 {len(historial_combinado)} registros | {n_aprobadas_final} materias aprobadas")
            except Exception as e:
                import traceback
                st.error(f"❌ Error al procesar PDF: {str(e)}")
                st.code(traceback.format_exc())

    # Verificar si hay datos
    if "datos_estudiante" not in st.session_state:
        st.info("👆 Carga primero el **Historial Académico** y luego el **Kardex** en el panel lateral para comenzar")
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

    # Sobrescribir ciclos usando el mapa oficial (semestres 1-8) para todos los DataFrames.
    # Así se garantiza que historial_df y historial_filtrado usen semestres aunque
    # el kardex o historial parser hayan asignado ciclos anuales.
    _mapa_ciclos = {m.get("clave", ""): m.get("ciclo", None) for m in mapa_curricular}

    def _ciclo_oficial(clave):
        c = _mapa_ciclos.get(str(clave).strip().upper())
        return int(c) if c is not None else None

    for _df in (historial_df, historial_filtrado):
        _override = _df["clave"].apply(_ciclo_oficial)
        _df["ciclo"] = _override.combine_first(_df["ciclo"].astype("float64")).astype("Int64")

    info_sabaticos = detectar_sabaticos(historial_df)

    creditos_totales = st.session_state.get("creditos_totales", 404)
    creditos_acumulados = st.session_state.get("creditos_acumulados", datos.total_creditos)
    creditos_faltantes = max(0, creditos_totales - creditos_acumulados)

    # ========== PESTAÑAS PRINCIPALES ==========
    tab_historia_main, tab_experto_main, tab_mapa_main, tab_pruebas_main = st.tabs([
        "🗂️ Historia Académica",
        "🧠 Sistema Experto",
        "📋 Mapa Curricular",
        "🔬 Pruebas",
    ])

    with tab_historia_main:
        st.caption("Usa las pestañas inferiores para navegar el historial académico y su progreso.")
        tab1, tab2, tab2b, tab3, tab4 = st.tabs([
            "📋 Resumen General",
            "📈 Progreso por Ciclo",
            "📅 Progreso por Semestre",
            "📚 Elección Libre y Adicionales",
            "🎓 Pre-Especialidades",
        ])

    with tab_experto_main:
        subtab_candidatas, = st.tabs(["📌 Materias candidatas"])

        with subtab_candidatas:
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
                resultado = ejecutar_sistema_experto(
                    historial_academico=historial_aprobado,
                    mapa_curricular=mapa_curricular,
                    plan_estudios=plan_estudios
                )

                debug_info = resultado.get("debug", {})
                ciclo_act  = resultado.get("ciclo_actual", 0)
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
                    st.metric("Semestre actual", ciclo_act)
                with col_met2:
                    st.metric("Materias candidatas", resultado.get("candidatas_count", 0))
                with col_met3:
                    st.metric("Analizadas inicialmente", ini_count)

                # ── Tabla de candidatas ──
                candidatas_detalles = resultado.get("candidatas_detalles", [])
                if candidatas_detalles:
                    st.subheader("✅ Materias que puedes cursar")

                    df_candidatas = pd.DataFrame(candidatas_detalles)

                    if "prerequisitos" in df_candidatas.columns:
                        df_candidatas["prerequisitos"] = df_candidatas["prerequisitos"].apply(
                            lambda x: ", ".join(x) if isinstance(x, list) and x else "—"
                        )

                    cols_mostrar = ["clave", "nombre", "ciclo", "creditos", "categoria", "prerequisitos"]
                    cols_existentes = [c for c in cols_mostrar if c in df_candidatas.columns]
                    df_mostrar = df_candidatas[cols_existentes].rename(columns={
                        "clave": "Clave",
                        "nombre": "Nombre",
                        "ciclo": "Ciclo",
                        "creditos": "Créditos",
                        "categoria": "Categoría",
                        "prerequisitos": "Prerequisitos",
                    })

                    st.dataframe(
                        df_mostrar,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Clave": st.column_config.TextColumn(width="small"),
                            "Nombre": st.column_config.TextColumn(width="medium"),
                            "Ciclo": st.column_config.NumberColumn(width="small"),
                            "Créditos": st.column_config.NumberColumn(width="small"),
                            "Categoría": st.column_config.TextColumn(width="small"),
                            "Prerequisitos": st.column_config.TextColumn(width="medium"),
                        }
                    )

                    st.divider()
                    col_est1, col_est2, col_est3 = st.columns(3)
                    with col_est1:
                        st.metric("Créditos totales", int(df_candidatas["creditos"].sum()))
                    with col_est2:
                        st.metric("Materias básicas", len(df_candidatas[df_candidatas["categoria"] == "BASICA"]))
                    with col_est3:
                        st.metric("Materias optativas", len(df_candidatas[df_candidatas["categoria"] != "BASICA"]))
                else:
                    st.info("No se encontraron materias candidatas disponibles en este momento.")

                # ── Explicación de la lógica (debajo de la tabla) ──
                st.divider()
                with st.expander("¿Cómo se eligieron estas materias?", expanded=False):

                    lineas = []

                    # 1. Semestre y punto de partida
                    lineas.append(
                        f"**Semestre detectado: {ciclo_act}**  \
\nEl sistema revisaó tu avance semestre por semestre. Para avanzar de semestre "
                        f"se requiere haber cubierto al menos el 75\xa0% de las materias básicas de ese semestre. "
                        f"Cumpliste ese umbral en todos los semestres anteriores al {ciclo_act}, por lo que te ubica en ese punto."
                    )

                    lineas.append(
                        f"**Punto de partida: {ini_count} materias**  \
\nSe tomaron como candidatas iniciales todas las materias del semestre {ciclo_act} "
                        f"y del semestre {ciclo_act + 1} que aún no tienes aprobadas ni en curso."
                    ) if ciclo_act < 8 else lineas.append(
                        f"**Punto de partida: {ini_count} materias**  \
\nSe tomaron como candidatas iniciales todas las materias del semestre {ciclo_act} "
                        f"que aún no tienes aprobadas ni en curso."
                    )

                    # 2. Filtros que realmente eliminaron materias
                    if elim_a > 0:
                        lineas.append(
                            f"**Prerequisitos no cumplidos: se eliminaron {elim_a} materia(s)**  \
\n"
                            f"Cada una de esas materias requiere que apruebes primero otra u otras que aún tienes pendientes."
                        )
                    if elim_b > 0:
                        lineas.append(
                            f"**Cadenas de seriación: se eliminaron {elim_b} materia(s)**  \
\n"
                            f"Algunas materias forman secuencias (por ejemplo, Cálculo I → II → III). "
                            f"Si el eslabón previo no está aprobado, la materia más avanzada se descarta."
                        )
                    if elim_c > 0:
                        lineas.append(
                            f"**Cuota de Elección Libre: se ajustaron {elim_c} materia(s)**  \
\n"
                            f"El plan de estudios tiene un número recomendado de materias de Elección Libre por ciclo anual. "
                            f"Ya alcanzaste esa cuota en uno o más ciclos, por lo que las optativas sobrantes se retiraron."
                        )

                    # 3. Pre-especialidades
                    if esp:
                        if elim_d > 0:
                            lineas.append(
                                f"**Pre-especialidad: se eliminaron {elim_d} materia(s) de la otra línea**  \
\n"
                                f"Dado que todas tus materias de pre-especialidad aprobadas pertenecen a **{esp}**, "
                                f"el sistema descartó las materias de la otra especialidad para no desviar tu trayectoria."
                            )
                        else:
                            lineas.append(
                                f"**Pre-especialidad detectada: {esp}**  \
\n"
                                f"El sistema identificó que te has enfocado en esta línea, pero no fue necesario eliminar "
                                f"ninguna materia candidata adicional."
                            )
                    else:
                        # Verificar si hay avance en ambas o en ninguna
                        if elim_d == 0 and ini_count > 0:
                            lineas.append(
                                "**Pre-especialidades: se muestran materias de ambas líneas**  \n"
                                "Aún no tienes materias aprobadas exclusivamente en una sola especialidad, "
                                "por lo que el sistema incluye candidatas de ambas pre-especialidades. "
                                "Cuando te concentres en una, la otra dejará de aparecer en futuras recomendaciones."
                            )

                    if elim_e > 0:
                        lineas.append(
                            f"**Prácticas de pre-especialidad: se eliminaron {elim_e} practica(s)**  \
\n"
                            f"Las prácticas de pre-especialidad requieren que hayas aprobado al menos 3 materias "
                            f"de esa línea. Aún no se alcanzan esos requisitos."
                        )

                    # 4. Resultado
                    final_count = resultado.get("candidatas_count", 0)
                    lineas.append(
                        f"**Resultado: {final_count} materia(s) recomendadas**  \
\n"
                        f"Las materias de la tabla son las que puedes inscribir ahora mismo según tu historial "
                        f"y las reglas de seriación de tu plan de estudios."
                    )

                    for linea in lineas:
                        st.markdown(linea)
                        st.markdown("")


    # ===================================================================
    # PESTAÑA 1: RESUMEN GENERAL
    # ===================================================================
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
        _mat_reprobadas = (historial_filtrado["estatus"] == "REPROBADA").sum()
        _mat_cursadas = historial_filtrado["estatus"].isin(["APROBADA", "REPROBADA"]).sum()
        _indice_reprobacion = (_mat_reprobadas / _mat_cursadas * 100) if _mat_cursadas > 0 else 0.0

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Plan de Estudios", datos.plan_estudios)
        with col2:
            st.metric("Créditos", f"{creditos_acumulados}/{creditos_totales}",
                     delta=f"-{creditos_faltantes} para graduarse" if creditos_faltantes > 0 else "Completado",
                     delta_color="inverse")
        with col3:
            st.metric("Promedio General", f"{datos.promedio_general:.2f}")
        with col4:
            st.metric("Situación", datos.situacion)
        with col5:
            st.metric("Índice de Reprobación", f"{_indice_reprobacion:.1f}%",
                     help=f"{_mat_reprobadas} reprobadas / {_mat_cursadas} cursadas")

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
        _sem_proy_fmt = f"{_sem_proyectados:.0f}" if _sem_proyectados < 999 else "N/A"
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
            if alertas:
                for alerta in alertas:
                    if alerta.get("severidad") == "CRITICA":
                        st.markdown(f"""
                        <div class='alerta-critica'>
                            <strong>🔴 {alerta.get('tipo', 'ALERTA')}</strong><br>
                            {alerta.get('descripcion', '')}
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class='alerta-advertencia'>
                            <strong>🟠 {alerta.get('tipo', 'ADVERTENCIA')}</strong><br>
                            {alerta.get('descripcion', '')}
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.success("✅ No hay alertas académicas activas")
        except Exception as e:
            st.warning(f"Error al calcular alertas: {str(e)}")

    # ===================================================================
    # PESTAÑA 2: PROGRESO POR CICLO
    # ===================================================================
    with tab2:
        st.header("📈 Progreso por Ciclo Anual")
        st.caption("Resumen agregado por ciclo anual (cada ciclo anual agrupa 2 semestres). Los ciclos 3 y 4 se muestran juntos.")

        try:
            progreso_ciclos = processor.calcular_progreso_por_ciclo(historial_filtrado)
            materias_por_estatus = obtener_materias_por_estatus_ciclo(historial_filtrado, mapa_curricular)

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
                pct = (fin / (tot - pend) * 100) if (tot - pend) > 0 else 0
                return {"finalizadas": fin, "en_curso": en_c, "recursando": rec,
                        "reprobadas": rep, "pendientes": pend, "total": tot, "porcentaje": pct}

            grupos_anuales = [
                ("Ciclo Anual 1\n(Sems 1–2)", [1, 2]),
                ("Ciclo Anual 2\n(Sems 3–4)", [3, 4]),
                ("Ciclos Anuales 3 y 4\n(Sems 5–8)", [5, 6, 7, 8]),
            ]

            cols_ca = st.columns(3)
            for col, (nombre_ca, sems_ca) in zip(cols_ca, grupos_anuales):
                datos_ca = _agrupar_ciclos_anuales(progreso_ciclos, sems_ca)
                with col:
                    st.subheader(nombre_ca.replace("\n", " "))
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
                    cursadas_ca = datos_ca["total"] - datos_ca["pendientes"]
                    lineas_ca = [f"<strong>{datos_ca['porcentaje']:.1f}% Completado</strong>",
                                 f"✅ Finalizadas: {datos_ca['finalizadas']}/{cursadas_ca}",
                                 f"⏳ En Curso: {datos_ca['en_curso']}/{cursadas_ca}"]
                    if datos_ca["recursando"] > 0:
                        lineas_ca.append(f"🟠 Recursando: {datos_ca['recursando']}/{cursadas_ca}")
                    lineas_ca.append(f"❌ Reprobadas: {datos_ca['reprobadas']}/{cursadas_ca}")
                    lineas_ca.append(f"⚪ Pendientes: {datos_ca['pendientes']}")
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
            historial_limpio = historial_filtrado.copy()
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
                        lambda x: f"{x:.1f}" if x is not None and isinstance(x, (int, float)) else "S/A" if x is None else str(x)
                    )
                    display_df["nombre"] = display_df["nombre"] + display_df["badge_intento"]
                    display_df["estatus"] = display_df["estatus"].map(lambda e: f"{estatus_color.get(e, '')} {e}")
                    display_df = display_df[["clave", "nombre", "calificacion", "creditos", "estatus"]]
                    display_df.columns = ["Clave", "Asignatura", "Calificación", "Créditos", "Estatus"]
                    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # ===================================================================
    # PESTAÑA 2B: PROGRESO POR SEMESTRE
    # ===================================================================
    with tab2b:
        st.header("📅 Progreso por Semestre")
        st.caption("Progreso individual de cada semestre (1-8) del plan de estudios.")

        try:
            progreso_ciclos = processor.calcular_progreso_por_ciclo(historial_filtrado)
            materias_por_estatus = obtener_materias_por_estatus_ciclo(historial_filtrado, mapa_curricular)
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
                            cursadas = progreso.total - progreso.pendientes
                            lineas = [
                                f"<strong>{progreso.porcentaje:.1f}% Completado</strong>",
                                f"✅ Finalizadas: {progreso.finalizadas}/{cursadas}",
                                f"⏳ En Curso: {progreso.en_curso}/{cursadas}",
                            ]
                            if progreso.recursando > 0:
                                lineas.append(f"🟠 Recursando: {progreso.recursando}/{cursadas}")
                            lineas.append(f"❌ Reprobadas: {progreso.reprobadas}/{cursadas}")
                            lineas.append(f"⚪ Pendientes: {progreso.pendientes}")
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
                            cursadas = progreso.total - progreso.pendientes
                            lineas = [
                                f"<strong>{progreso.porcentaje:.1f}% Completado</strong>",
                                f"✅ Finalizadas: {progreso.finalizadas}/{cursadas}",
                                f"⏳ En Curso: {progreso.en_curso}/{cursadas}",
                            ]
                            if progreso.recursando > 0:
                                lineas.append(f"🟠 Recursando: {progreso.recursando}/{cursadas}")
                            lineas.append(f"❌ Reprobadas: {progreso.reprobadas}/{cursadas}")
                            lineas.append(f"⚪ Pendientes: {progreso.pendientes}")
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

    # ===================================================================
    # PESTAÑA 3: ELECCIÓN LIBRE Y ADICIONALES
    # ===================================================================
    with tab3:
        st.header("📚 Materias de Elección Libre")
        st.caption("Ciclo 1 y 2: 2 materias cada uno | Ciclos 3 y 4 combinados: 8 materias (incluye materias de pre-especialidad no usada)")

        try:
            eleccion_libre, pre_titulacion, pre_especialidades_count = calcular_eleccion_libre(historial_filtrado, mapa_curricular)

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
            requisitos = processor.calcular_requisitos(historial_filtrado, ingles_completo=ingles_ok)
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
        st.subheader("🇬🇧 Progreso de Inglés")

        # Cadena completa de inglés para mostrar progreso
        cadena_ingles_display = [
            {"nivel": 1, "nombre": "Nivel 1 Inglés", "codigos": ["ID0107", "LI1101"]},
            {"nivel": 2, "nombre": "Nivel 2 Inglés", "codigos": ["ID0207", "LI1102"]},
            {"nivel": 3, "nombre": "Nivel 3 Inglés", "codigos": ["ID0307", "LI1103"]},
            {"nivel": 4, "nombre": "Nivel 4 Inglés", "codigos": ["ID0406"]},
            {"nivel": 5, "nombre": "Tópicos Selectos I", "codigos": ["ID0507"]},
            {"nivel": 6, "nombre": "Tópicos Selectos II", "codigos": ["ID0606"]},
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
                mask = historial_filtrado["clave"] == codigo
                if mask.any():
                    row = historial_filtrado[mask].iloc[0]
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
            preespecialidades = calcular_progreso_preespecialidades(historial_filtrado, mapa_curricular)

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
                            for _, _r in historial_filtrado.iterrows():
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


    # ===================================================================
    # PESTAÑA MAPA CURRICULAR: Esquema por semestre
    # ===================================================================
    with tab_mapa_main:
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

    # ===================================================================
    # PESTAÑA PRUEBAS: Diagnóstico de captura de datos
    # ===================================================================
    with tab_pruebas_main:
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


if __name__ == "__main__":
    main()
