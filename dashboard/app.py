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
from services.local_database import DatabaseService
from agents.sistema_experto_seriacion import ejecutar_sistema_experto
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
    """Carga el mapa curricular: session_state > JSON > vacío"""
    # Si ya fue cargado en esta sesión (via uploader), usarlo directamente
    if "mapa_curricular" in st.session_state and st.session_state.mapa_curricular:
        return st.session_state.mapa_curricular

    # Fallback a JSON guardado en disco
    try:
        mapa_path = Path(__file__).parent.parent / "data" / "mapa_curricular_2021ID.json"
        if mapa_path.exists():
            with open(mapa_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error cargando JSON: {e}")

    return {}


NOMBRES_CICLO = {
    0: "Co-curricular",
    1: "Primer Ciclo",
    2: "Segundo Ciclo",
    3: "Tercer Ciclo",
    4: "Cuarto Ciclo",
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
        hole=0.4
    )])
    
    fig.update_layout(
        title=nombre_ciclo,
        showlegend=True,
        height=400
    )
    
    return fig


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


def calcular_eleccion_libre(historial_df: pd.DataFrame, mapa_curricular: dict) -> dict:
    """
    Calcula el progreso de materias de elección libre por ciclo.
    Usa el historial académico como fuente de verdad para identificar materias de elección libre.
    Reglas:
    - Ciclo 1: 2 materias de elección libre requeridas
    - Ciclo 2: 2 materias de elección libre requeridas
    - Ciclos 3 y 4 combinados: 8 materias totales (incluyendo materias de pre-especialidad NO usada)
    """
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
        
        if clave in mapa_curricular:
            categoria = mapa_curricular[clave].get("categoria", "")
            if categoria in ("PRE_ESPECIALIDAD", "PRE-ESPECIALIDAD") and estatus == "APROBADA":
                # CORRECCIÓN: Identificación basada en el nombre de la materia desde el historial
                if "inteligencia" in nombre.lower() and ("negocios" in nombre.lower() or "organizacional" in nombre.lower()):
                    pre_especialidades["IoN"] += 1
                elif "innovaci" in nombre.lower() and "tic" in nombre.lower():
                    pre_especialidades["ITIC"] += 1
                # Fallback por código si no hay nombre claro
                # ID3420-ID3424 = Inteligencia Organizacional y de Negocios
                # ID3415-ID3419 = Innovación en TIC
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
        
        if clave not in mapa_curricular:
            continue
            
        ciclo = mapa_curricular[clave].get("ciclo", 0)
        categoria = mapa_curricular[clave].get("categoria", "")
        
        # Caso 1: Materias explícitamente de elección libre según el historial académico
        if "ELECCI" in categoria.upper() and "LIBRE" in categoria.upper():
            if ciclo == 1:
                if estatus == "APROBADA":
                    eleccion_libre[1]["aprobadas"] += 1
                elif estatus in ("EN_CURSO", "RECURSANDO"):
                    eleccion_libre[1]["en_curso"] += 1
                eleccion_libre[1]["claves"].append(clave)
                eleccion_libre[1]["nombres"].append(nombre)
            elif ciclo == 2:
                if estatus == "APROBADA":
                    eleccion_libre[2]["aprobadas"] += 1
                elif estatus in ("EN_CURSO", "RECURSANDO"):
                    eleccion_libre[2]["en_curso"] += 1
                eleccion_libre[2]["claves"].append(clave)
                eleccion_libre[2]["nombres"].append(nombre)
            elif ciclo in (3, 4):
                if estatus == "APROBADA":
                    eleccion_libre["3_y_4"]["aprobadas"] += 1
                elif estatus in ("EN_CURSO", "RECURSANDO"):
                    eleccion_libre["3_y_4"]["en_curso"] += 1
                eleccion_libre["3_y_4"]["claves"].append(clave)
                eleccion_libre["3_y_4"]["nombres"].append(nombre)

        # Caso 2: Materias de la pre-especialidad NO usada para titular cuentan como elección libre en ciclos 3 y 4
        elif categoria in ("PRE_ESPECIALIDAD", "PRE-ESPECIALIDAD") and ciclo in (3, 4):
            # Determinar a qué pre-especialidad pertenece
            if "inteligencia" in nombre.lower() and ("negocios" in nombre.lower() or "organizacional" in nombre.lower()):
                pre_materia = "IoN"
            elif "innovaci" in nombre.lower() and "tic" in nombre.lower():
                pre_materia = "ITIC"
            # Fallback por código
            # ID3420-ID3424 = Inteligencia Organizacional y de Negocios
            # ID3415-ID3419 = Innovación en TIC
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


def calcular_progreso_preespecialidades(historial_df: pd.DataFrame, mapa_curricular: dict) -> dict:
    """
    Calcula el progreso en cada pre-especialidad.
    Cada pre-especialidad necesita 5 materias para completarse.
    CORRECCIÓN: Usar nombres de materias del historial como fuente de verdad.
    """
    # Identificar materias de pre-especialidad desde el historial
    preespecialidades = {}
    materias_procesadas = {}  # {clave: estatus_mas_reciente}
    
    # Buscar en el historial las materias de pre-especialidad
    # Primero, obtener el estatus más reciente de cada materia
    for _, row in historial_df.iterrows():
        clave = row.get("clave", "")
        nombre = row.get("nombre", "")
        estatus = row.get("estatus", "")
        periodo = row.get("periodo", "")
        
        # Verificar si está en el mapa como PRE-ESPECIALIDAD
        if clave in mapa_curricular:
            categoria = mapa_curricular[clave].get("categoria", "")
            if categoria in ("PRE_ESPECIALIDAD", "PRE-ESPECIALIDAD"):
                # CORRECCIÓN: Determinar a qué pre-especialidad pertenece por el nombre desde el historial
                if "inteligencia" in nombre.lower() and ("negocios" in nombre.lower() or "organizacional" in nombre.lower()):
                    pre_esp = "Inteligencia Organizacional y de Negocios"
                elif "innovaci" in nombre.lower() and "tic" in nombre.lower():
                    pre_esp = "Innovación en TIC"
                else:
                    # Si no podemos determinar por nombre, intentar por código
                    # ID3420-ID3424 = Inteligencia Organizacional y de Negocios
                    # ID3415-ID3419 = Innovación en TIC
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
            if st.button("🗂️ Procesar Historial Académico", use_container_width=True):
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

                        # Guardar mapa en disco y session_state
                        mapa_path = Path(__file__).parent.parent / "data" / "mapa_curricular_2021ID.json"
                        mapa_path.parent.mkdir(exist_ok=True)
                        with open(mapa_path, "w", encoding="utf-8") as f:
                            json.dump(mapa, f, ensure_ascii=False, indent=2)

                        st.session_state.mapa_curricular = mapa
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
                        st.session_state.ingles_completo = historial_parser.ingles_completo

                        n_aprobadas = len(aprobadas)
                        n_total = len(historial_parser.materias)

                    st.success(f"✅ Historial procesado: {n_total} materias, {n_aprobadas} aprobadas")
                    st.info(f"📊 Créditos: {historial_parser.creditos_acumulados}/{historial_parser.creditos_totales}")
                    if historial_parser.nivel_ingles_texto:
                        st.info(f"📖 Inglés aprobado: {historial_parser.nivel_ingles_texto} ({len(historial_parser.codigos_ingles_aprobados)} niveles auto-aprobados)")
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
    processor = AcademicProcessor(mapa_curricular)
    historial_df = normalizar_ultima_carga(historial_df)
    historial_filtrado = filtrar_ultimo_estatus(historial_df)
    historial_filtrado = marcar_recursando(historial_filtrado, historial_df)

    creditos_totales = st.session_state.get("creditos_totales", 404)
    creditos_acumulados = st.session_state.get("creditos_acumulados", datos.total_creditos)
    creditos_faltantes = max(0, creditos_totales - creditos_acumulados)

    # ========== PESTAÑAS PRINCIPALES ==========
    tab_historia_main, tab_experto_main = st.tabs([
        "🗂️ Historia Académica",
        "🧠 Sistema Experto",
    ])

    with tab_historia_main:
        st.caption("Usa las pestañas inferiores para navegar el historial académico y su progreso.")
        tab1, tab2, tab3, tab4 = st.tabs([
            "📋 Resumen General",
            "📈 Progreso por Ciclo",
            "📚 Elección Libre y Adicionales",
            "🎓 Pre-Especialidades",
        ])

    with tab_experto_main:
        subtab_candidatas, = st.tabs(["📌 Materias candidatas"])

        with subtab_candidatas:
            st.subheader("🧠 Sistema Experto de Seriación")
            st.caption("Muestra materias candidatas y recomendadas para el periodo de oferta seleccionado.")

            plan_estudios = str(getattr(datos, "plan_estudios", "2021ID") or "2021ID").strip()
            periodos = obtener_periodos_oferta(plan_estudios)

            col_cfg1, col_cfg2 = st.columns([2, 1])
            with col_cfg1:
                if periodos:
                    periodos_fmt = {p: formatear_periodo(p) for p in periodos}
                    periodo_sel = st.selectbox(
                        "Periodo de oferta académica",
                        options=periodos,
                        index=len(periodos) - 1,
                        format_func=lambda p: periodos_fmt.get(str(p), str(p)),
                        help="Formato: YYYYPP (01 Primavera, 02 Verano, 03 Otoño, 04 Invierno)"
                    )
                else:
                    periodo_sel = None
                    st.warning("No se detectaron periodos de oferta. Se ejecutará sin filtro de oferta.")
            with col_cfg2:
                usar_oferta = st.checkbox(
                    "Filtrar por oferta",
                    value=True,
                    help="Si se desactiva, muestra candidatas sin filtrar por periodo"
                )

            # Preparar historial APROBADO para el sistema experto
            historial_aprobado = []
            if not historial_filtrado.empty:
                for _, row in historial_filtrado.iterrows():
                    if str(row.get("estatus", "")).upper() != "APROBADA":
                        continue
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
                        "clave_materia": str(row.get("clave", "")).strip(),
                        "calificacion": cal,
                        "creditos_obtenidos": cred,
                    })

            materias_en_curso = []
            if not historial_filtrado.empty:
                mask_curso = historial_filtrado["estatus"].isin(["EN_CURSO", "RECURSANDO"])
                materias_en_curso = historial_filtrado.loc[mask_curso, "clave"].astype(str).str.strip().tolist()

            claves_con_reprobacion = set()
            intentos_por_clave = {}
            if not historial_df.empty:
                for _, row in historial_df.iterrows():
                    clave = str(row.get("clave", "")).strip()
                    if not clave:
                        continue
                    intentos_por_clave[clave] = intentos_por_clave.get(clave, 0) + 1
                    if str(row.get("estatus", "")).upper() == "REPROBADA":
                        claves_con_reprobacion.add(clave)

            ejecutar = st.button("⚡ Ejecutar Sistema Experto", use_container_width=True)

            if ejecutar:
                try:
                    resultado_experto = ejecutar_sistema_experto(
                        datos_estudiante={
                            "id": getattr(datos, "matricula", ""),
                            "nombre": getattr(datos, "nombre", ""),
                            "promedio": float(getattr(datos, "promedio_general", 0.0) or 0.0),
                            "total_creditos": int(getattr(datos, "total_creditos", 0) or 0),
                        },
                        historial_academico=historial_aprobado,
                        materias_en_curso=materias_en_curso,
                        usar_oferta_academica=usar_oferta,
                        periodo_oferta=periodo_sel,
                        plan_estudios=plan_estudios,
                    )

                    col_m1, col_m2, col_m3 = st.columns(3)
                    with col_m1:
                        st.metric("Ciclo recomendado", resultado_experto.get("ciclo_recomendado", "-"))
                    with col_m2:
                        st.metric("Materias candidatas", resultado_experto.get("total_materias_recomendadas", 0))
                    with col_m3:
                        periodo_resultado = resultado_experto.get("periodo_oferta")
                        if periodo_resultado:
                            st.metric("Periodo oferta", formatear_periodo(periodo_resultado))
                        else:
                            st.metric("Periodo oferta", "N/A")

                    materias = resultado_experto.get("materias_recomendadas", [])
                    if materias:
                        df_mat = pd.DataFrame(materias)
                        df_mat["condicion"] = df_mat["clave"].apply(
                            lambda clave: "RECURSE" if str(clave).strip() in claves_con_reprobacion else "NUEVA"
                        )
                        df_mat["intentos_previos"] = df_mat["clave"].apply(
                            lambda clave: max(0, intentos_por_clave.get(str(clave).strip(), 0))
                        )
                        columnas = [c for c in ["clave", "nombre", "ciclo", "categoria", "creditos"] if c in df_mat.columns]
                        columnas = ["condicion"] + columnas + ["intentos_previos"]

                        total_recurse = int((df_mat["condicion"] == "RECURSE").sum())
                        total_nuevas = int((df_mat["condicion"] == "NUEVA").sum())
                        st.caption(
                            f"Materias nuevas: {total_nuevas} | "
                            f"Materias para recursar: {total_recurse}"
                        )
                        st.dataframe(df_mat[columnas], use_container_width=True, hide_index=True)
                    else:
                        st.info("No se encontraron materias candidatas para los filtros seleccionados.")

                    alertas = resultado_experto.get("alertas", [])
                    if alertas:
                        with st.expander("Ver alertas del sistema experto"):
                            st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
                except Exception as e:
                    st.error(f"Error ejecutando sistema experto: {str(e)}")

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

        # ── Barra de progreso general ──
        st.markdown("---")
        st.subheader("📊 Progreso de la Carrera")

        porcentaje_creditos = (creditos_acumulados / creditos_totales * 100) if creditos_totales > 0 else 0

        ciclos_cursados = sorted(set(historial_df['ciclo'].dropna().astype(int))) if 'ciclo' in historial_df.columns else []
        ciclos_unicos = len(ciclos_cursados)

        from datetime import datetime as _dt
        años_aprox = 0
        semestre_actual = 1
        try:
            matricula_str = datos.matricula.strip()
            if len(matricula_str) >= 2:
                año_entrada = 2000 + int(matricula_str[:2])
                _inicio = _dt(año_entrada, 8, 1)
                _hoy = _dt.now()
                _meses = (_hoy.year - _inicio.year) * 12 + (_hoy.month - _inicio.month)
                _meses = max(0, _meses)
                semestre_actual = max(1, (_meses // 6) + 1)
                años_aprox = round(_meses / 12, 1)
        except Exception:
            semestre_actual = max(1, ciclos_unicos * 2)

        _ritmo = creditos_acumulados / semestre_actual if semestre_actual > 0 else 0
        _sem_proyectados = (creditos_totales / _ritmo) if _ritmo > 0 else 999

        if semestre_actual >= 16 and creditos_acumulados < creditos_totales:
            _color_ritmo = "#7b0000"
            _etiqueta_ritmo = "&#x26A0; CR&Iacute;TICO TOTAL &mdash; l&iacute;mite de 16 semestres alcanzado"
        elif _sem_proyectados <= 9:
            _color_ritmo = "#27ae60"
            _etiqueta_ritmo = "En tiempo (&le;4.5 a&ntilde;os)"
        elif _sem_proyectados <= 11:
            _color_ritmo = "#a8e063"
            _etiqueta_ritmo = "Leve retraso (4.5-5.5 a&ntilde;os)"
        elif _sem_proyectados <= 13:
            _color_ritmo = "#fdcb6e"
            _etiqueta_ritmo = "Retraso moderado (5.5-6.5 a&ntilde;os)"
        elif _sem_proyectados < 16:
            _color_ritmo = "#e17055"
            _etiqueta_ritmo = "Retraso grave (6.5-8 a&ntilde;os)"
        else:
            _color_ritmo = "#d63031"
            _etiqueta_ritmo = "CR&Iacute;TICO &mdash; proyecci&oacute;n supera el l&iacute;mite de 16 semestres"

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
        _barra_html = (
            '<div style="background:#f7f7f7;border:1.5px solid #d0d0d0;border-radius:10px;'
            'padding:12px 14px;margin-bottom:8px;">'
            '<div style="font-size:13px;color:#555;margin-bottom:8px;font-weight:600;">'
            f'Progreso general'
            f' &nbsp;|&nbsp; {creditos_acumulados}/{creditos_totales} cr\u00e9ditos'
            f' &nbsp;|&nbsp; Semestre {semestre_actual} ({años_aprox} a\u00f1os)'
            f' &nbsp;|&nbsp; Ritmo: {_ritmo_fmt} cr/sem &nbsp;&bull;&nbsp; Proyecci\u00f3n: {_sem_proy_fmt} semestres'
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
            '<span style="color:#d63031;font-weight:bold;">&#9632;</span> &ge;16 sem &nbsp;'
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
        st.header("📈 Progreso por Ciclo")

        try:
            progreso_ciclos = processor.calcular_progreso_por_ciclo(historial_filtrado)
            ciclos_validos = sorted(c for c in progreso_ciclos.keys() if 1 <= c <= 4)

            if ciclos_validos:
                cols = st.columns(4)
                for ciclo in range(1, 5):
                    with cols[ciclo - 1]:
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
                            contenido = "<br>".join(lineas)
                            st.markdown(f"<div class='metric-box'>{contenido}</div>", unsafe_allow_html=True)
                        else:
                            st.info(f"Ciclo {ciclo}: Sin datos")
            else:
                st.info("No hay datos de progreso por ciclo.")
        except Exception as e:
            st.warning(f"Error al calcular progreso: {str(e)}")

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
        nivel_num = 0
        # Obtener nivel numérico del historial
        from parsers.historial_parser import HistorialParser as _HP
        for entry in _HP.CADENA_INGLES:
            for nombre_n in entry["nombres"]:
                if nivel_historial and nombre_n in nivel_historial.lower().replace("inglés", "").replace("ingles", "").strip():
                    nivel_num = max(nivel_num, entry["nivel"])

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
            else:
                st.info("No se detectaron materias de pre-especialidad en el historial.")
        except Exception as e:
            st.warning(f"Error al calcular pre-especialidades: {str(e)}")


if __name__ == "__main__":
    main()
