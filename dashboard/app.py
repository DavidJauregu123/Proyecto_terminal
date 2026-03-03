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

from parsers import KardexParser
from services import AcademicProcessor
from services.supabase_service import SupabaseService
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
    fig = go.Figure(data=[go.Pie(
        labels=["Finalizadas", "En Curso", "Reprobadas"],
        values=[
            progreso.get("finalizadas", 0),
            progreso.get("en_curso", 0),
            progreso.get("reprobadas", 0)
        ],
        marker=dict(colors=["#28a745", "#ffc107", "#dc3545"]),
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
    """
    if historial_df.empty:
        return historial_df
    
    # Asegurar que periodo existe y convertir a string para ordenar
    if "periodo" not in historial_df.columns:
        return historial_df
    
    # Ordenar por periodo descendente (más reciente primero)
    df_ordenado = historial_df.sort_values("periodo", ascending=False, na_position='last')
    
    # Quedarse con el primer registro de cada clave (el más reciente)
    df_ultimo = df_ordenado.drop_duplicates(subset=["clave"], keep="first")
    
    # Reordenar por ciclo y clave para mantener orden lógico
    if "ciclo" in df_ultimo.columns:
        df_ultimo = df_ultimo.sort_values(["ciclo", "clave"], na_position='last')
    
    return df_ultimo


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
                elif estatus == "EN_CURSO":
                    eleccion_libre[1]["en_curso"] += 1
                eleccion_libre[1]["claves"].append(clave)
                eleccion_libre[1]["nombres"].append(nombre)
            elif ciclo == 2:
                if estatus == "APROBADA":
                    eleccion_libre[2]["aprobadas"] += 1
                elif estatus == "EN_CURSO":
                    eleccion_libre[2]["en_curso"] += 1
                eleccion_libre[2]["claves"].append(clave)
                eleccion_libre[2]["nombres"].append(nombre)
            elif ciclo in (3, 4):
                if estatus == "APROBADA":
                    eleccion_libre["3_y_4"]["aprobadas"] += 1
                elif estatus == "EN_CURSO":
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
                elif estatus == "EN_CURSO":
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
        elif estatus == "EN_CURSO":
            preespecialidades[pre]["en_curso"] += 1
    
    return preespecialidades


def main():
    """Función principal de la aplicación"""
    
    st.title("📊 Reporte de Estado Académico")
    st.markdown("---")
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuración")
        
        # Subir PDF
        pdf_file = st.file_uploader(
            "Cargar Kardex (PDF)",
            type="pdf",
            help="Selecciona el archivo PDF del kardex del estudiante"
        )
        
        st.markdown("---")

        # Subir Historial Académico para enriquecer el mapa curricular
        historial_file = st.file_uploader(
            "Cargar Historial Académico (PDF)",
            type="pdf",
            key="historial_uploader",
            help="Sube el historial académico oficial para actualizar el mapa curricular (ciclos y créditos)"
        )

        if historial_file is not None:
            if st.button("🗂️ Actualizar Mapa Curricular", use_container_width=True):
                try:
                    with st.spinner("Procesando historial académico..."):
                        with open("temp_historial.pdf", "wb") as f:
                            f.write(historial_file.getvalue())
                        
                        # Generar mapa curricular
                        mapa = generar_mapa("temp_historial.pdf")
                        
                        # Extraer créditos del historial
                        from parsers.historial_parser import HistorialParser
                        historial_parser = HistorialParser()
                        historial_parser.parse_historial("temp_historial.pdf")
                        
                        if os.path.exists("temp_historial.pdf"):
                            os.remove("temp_historial.pdf")

                        # Guardar en disco y en session_state
                        mapa_path = Path(__file__).parent.parent / "data" / "mapa_curricular_2021ID.json"
                        mapa_path.parent.mkdir(exist_ok=True)
                        with open(mapa_path, "w", encoding="utf-8") as f:
                            json.dump(mapa, f, ensure_ascii=False, indent=2)
                        st.session_state.mapa_curricular = mapa
                        st.session_state.creditos_totales = historial_parser.creditos_totales
                        st.session_state.creditos_acumulados = historial_parser.creditos_acumulados

                    st.success(f"✅ Mapa actualizado: {len(mapa)} materias cargadas")
                    st.info(f"📊 Créditos: {historial_parser.creditos_acumulados}/{historial_parser.creditos_totales}")
                except Exception as e:
                    import traceback
                    st.error(f"❌ Error al procesar historial: {str(e)}")
                    st.code(traceback.format_exc())
        elif "mapa_curricular" in st.session_state:
            st.caption(f"🗂️ Mapa activo: {len(st.session_state.mapa_curricular)} materias")

        if pdf_file is not None:
            try:
                with st.spinner("Procesando kardex..."):
                    # Guardar archivo temporal
                    with open("temp_kardex.pdf", "wb") as f:
                        f.write(pdf_file.getvalue())
                    temp_path = "temp_kardex.pdf"
                    
                    # Parsear
                    parser = KardexParser()
                    datos = parser.parse_kardex(temp_path)
                    
                    # Guardar en BD local
                    db = SupabaseService()
                    db.crear_estudiante(datos.matricula, {
                        "nombre": datos.nombre,
                        "plan_estudios": datos.plan_estudios,
                        "situacion": datos.situacion,
                        "total_creditos": datos.total_creditos,
                        "promedio_general": datos.promedio_general
                    })
                    
                    # Guardar historial
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
                    
                    st.session_state.datos_estudiante = datos
                    st.session_state.historial_df = parser.to_dataframe()
                    
                    # Limpiar archivo temporal
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    
                    st.success("✅ Kardex procesado y guardado correctamente")
                    st.info(f"📚 {len(datos.materias)} materias registradas en la BD local")
            except Exception as e:
                import traceback
                st.error(f"❌ Error al procesar PDF: {str(e)}")
                st.code(traceback.format_exc())
    
    # Verificar si hay datos
    if "datos_estudiante" not in st.session_state:
        st.info("👆 Carga un archivo PDF de kardex para comenzar")
        return
    
    datos = st.session_state.datos_estudiante
    historial_df = st.session_state.historial_df
    
    # ========== SECCIÓN 1: DATOS DEL ESTUDIANTE ==========
    st.header(f"👤 {datos.nombre}")
    
    # Alerta si el estatus NO es Regular
    if datos.situacion.upper() != "REGULAR":
        st.markdown(f"""
        <div class='alerta-estatus'>
            ⚠️ ATENCIÓN: ESTATUS ACADÉMICO - {datos.situacion.upper()} ⚠️
        </div>
        """, unsafe_allow_html=True)
    
    # Usar créditos del historial académico si están disponibles
    creditos_totales = st.session_state.get("creditos_totales", 404)  # Default 404
    creditos_acumulados = st.session_state.get("creditos_acumulados", datos.total_creditos)
    creditos_faltantes = max(0, creditos_totales - creditos_acumulados)
    
    # Mostrar métricas principales en una sola fila
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Matrícula", datos.matricula)
    with col2:
        st.metric("Plan de Estudios", datos.plan_estudios)
    with col3:
        st.metric("Créditos", f"{creditos_acumulados}/{creditos_totales}",
                 delta=f"-{creditos_faltantes} para graduarse" if creditos_faltantes > 0 else "Completado",
                 delta_color="inverse")
    with col4:
        st.metric("Promedio General", f"{datos.promedio_general:.2f}")
    with col5:
        st.metric("Situación", datos.situacion)
    
    # ========== INDICADOR DE PROGRESO ==========
    st.markdown("---")
    st.subheader("📊 Progreso de la Carrera")
    
    # Calcular porcentaje de créditos
    porcentaje_creditos = (creditos_acumulados / creditos_totales * 100) if creditos_totales > 0 else 0
    
    # Obtener ciclos cursados del historial
    ciclos_cursados = sorted(set(historial_df['ciclo'].dropna().astype(int))) if 'ciclo' in historial_df.columns else []
    ciclos_unicos = len(ciclos_cursados)
    
    # Calcular años desde agosto del año de entrada (extraído de la matrícula)
    años_aprox = 0
    try:
        # Extraer año de entrada de los primeros 2 dígitos de la matrícula
        # Ej: 220300709 → 22 → 2022
        matricula_str = datos.matricula.strip()
        if len(matricula_str) >= 2:
            año_dos_digitos = int(matricula_str[:2])
            # Convertir a año completo (20YY)
            año_entrada = 2000 + año_dos_digitos
            
            # Calcular años desde agosto del año de entrada hasta hoy
            from datetime import datetime
            fecha_inicio = datetime(año_entrada, 8, 1)
            fecha_hoy = datetime.now()
            días_transcurridos = (fecha_hoy - fecha_inicio).days
            años_aprox = round(días_transcurridos / 365.25, 1)
            años_aprox = max(0, años_aprox)  # No permitir valores negativos
    except Exception as e:
        años_aprox = ciclos_unicos  # Fallback si hay error
    
    # Mostrar progreso visual
    col_prog1, col_prog2 = st.columns([3, 1])
    
    with col_prog1:
        st.progress(porcentaje_creditos / 100, text=f"{porcentaje_creditos:.1f}% de créditos completados")
        st.caption(f"Créditos: {creditos_acumulados} de {creditos_totales} | Faltan: {creditos_faltantes}")
    
    with col_prog2:
        st.metric("Años cursados", f"{años_aprox}", 
                 f"Ciclos: {ciclos_unicos}",
                 delta_color="off")
    
    st.markdown("---")
    
    # ========== SECCIÓN 2: ALERTAS ACADÉMICAS ==========
    st.header("⚠️ Alertas Académicas")
    
    mapa_curricular = cargar_mapa_curricular()
    processor = AcademicProcessor(mapa_curricular)
    
    # Filtrar historial para quedarse solo con el último estatus de cada materia
    historial_filtrado = filtrar_ultimo_estatus(historial_df)
    
    try:
        alertas = processor.identificar_alertas(historial_filtrado, datos.situacion)
        
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
    
    st.markdown("---")
    
    # ========== SECCIÓN 3: PROGRESO POR CICLO ==========
    st.header("📈 Progreso por Ciclo")
    
    try:
        # Usar historial filtrado para mostrar solo el estado actual de cada materia
        progreso_ciclos = processor.calcular_progreso_por_ciclo(historial_filtrado)
        
        # Mostrar solo ciclos 1-4 (excluir co-curricular ciclo=0)
        ciclos_validos = sorted(c for c in progreso_ciclos.keys() if 1 <= c <= 4)
        
        if ciclos_validos:
            # Asegurar que siempre se muestren 4 columnas (ciclos 1-4)
            cols = st.columns(4)
            for ciclo in range(1, 5):
                with cols[ciclo - 1]:
                    if ciclo in progreso_ciclos:
                        progreso = progreso_ciclos[ciclo]
                        fig = crear_grafica_progreso_ciclo(ciclo, {
                            "finalizadas": progreso.finalizadas,
                            "en_curso": progreso.en_curso,
                            "reprobadas": progreso.reprobadas
                        })
                        st.plotly_chart(fig, use_container_width=True)
                        st.markdown(f"""
                        <div class='metric-box'>
                            <strong>{progreso.porcentaje:.1f}% Completado</strong><br>
                            ✅ Finalizadas: {progreso.finalizadas}/{progreso.total}<br>
                            ⏳ En Curso: {progreso.en_curso}/{progreso.total}<br>
                            ❌ Reprobadas: {progreso.reprobadas}/{progreso.total}
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.info(f"Ciclo {ciclo}: Sin datos")
        else:
            st.info("No hay datos de progreso por ciclo.")
    except Exception as e:
        st.warning(f"Error al calcular progreso: {str(e)}")
    
    st.markdown("---")
    
    # ========== SECCIÓN 3.2: MATERIAS DE ELECCIÓN LIBRE ==========
    st.header("📚 Materias de Elección Libre")
    st.caption("Ciclo 1 y 2: 2 materias cada uno | Ciclos 3 y 4 combinados: 8 materias (incluye materias de pre-especialidad no usada)")
    
    try:
        mapa_curricular = cargar_mapa_curricular()
        eleccion_libre, pre_titulacion, pre_especialidades_count = calcular_eleccion_libre(historial_filtrado, mapa_curricular)
        
        # Mostrar en 3 columnas: Ciclo 1, Ciclo 2, Ciclos 3 y 4
        col_el1, col_el2, col_el3 = st.columns(3)
        
        with col_el1:
            st.subheader("📘 Ciclo 1")
            el1 = eleccion_libre[1]
            progreso_el1 = (el1["aprobadas"] / el1["requeridas"] * 100) if el1["requeridas"] > 0 else 0
            # Limitar progreso entre 0 y 100% para la barra visual
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
            # Limitar progreso entre 0 y 100% para la barra visual
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
            # Limitar progreso entre 0 y 100% para la barra visual
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
        
        # Información adicional sobre materias potenciales de pre-especialidad
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
                
                # Calcular cuántas más se necesitan de elección libre vs cuántas se podrían obtener de pre-especialidad
                faltan_el = max(0, el34["requeridas"] - el34["aprobadas"])
                pre_no_usada = "IoN" if pre_titulacion == "ITIC" else "ITIC"
                materias_pre_no_usada = 5 - pre_especialidades_count[pre_no_usada]
                if faltan_el > 0 and materias_pre_no_usada > 0:
                    st.info(f"📊 Te faltan {faltan_el} materias de elección libre en Ciclos 3y4. Puedes tomar hasta {materias_pre_no_usada} materias de {pre_no_usada} que contarán como elección libre.")
                    
    except Exception as e:
        st.warning(f"Error al calcular elección libre: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
    
    st.markdown("---")
    
    # ========== SECCIÓN 3.5: PROGRESO DE PRE-ESPECIALIDADES ==========
    st.header("🎓 Progreso en Pre-Especialidades")
    st.caption("Cada pre-especialidad requiere 5 materias para completarse. La pre-especialidad con más materias aprobadas será tu titulación.")
    
    try:
        mapa_curricular = cargar_mapa_curricular()
        # Usar historial filtrado para evitar contar múltiples intentos
        preespecialidades = calcular_progreso_preespecialidades(historial_filtrado, mapa_curricular)
        
        if preespecialidades:
            cols_pre = st.columns(len(preespecialidades))
            for idx, (nombre, datos) in enumerate(preespecialidades.items()):
                with cols_pre[idx]:
                    aprobadas = datos["aprobadas"]
                    en_curso = datos["en_curso"]
                    total_requerido = 5  # Cada pre-especialidad requiere 5 materias
                    porcentaje = (aprobadas / total_requerido * 100) if total_requerido > 0 else 0
                    
                    # Determinar color según progreso
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
    
    st.markdown("---")
    
    # ========== SECCIÓN 4: REQUISITOS ADICIONALES ==========
    st.header("📋 Requisitos Adicionales")
    
    try:
        # Usar historial filtrado para verificar estado actual
        requisitos = processor.calcular_requisitos(historial_filtrado)
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
    
    st.markdown("---")
    
    # ========== SECCIÓN 5: TABLA DE MATERIAS POR CICLO ==========
    st.header("📚 Historial Académico por Ciclo")
    
    if historial_df.empty or "periodo" not in historial_df.columns:
        st.warning("⚠️ No se encontraron materias en el PDF. Verifica que el formato del kardex sea compatible.")
    else:
        estatus_color = {
            "APROBADA": "🟢",
            "REPROBADA": "🔴",
            "EN_CURSO": "🟡",
            "SIN_REGISTRAR": "⚪"
        }
        
        # Detectar materias duplicadas (múltiples intentos)
        conteo_materias = historial_df.groupby("clave").size().to_dict()
        
        # Para cada materia duplicada, obtener último registro
        historial_limpio = historial_df.copy()
        historial_limpio["intentos"] = historial_limpio["clave"].map(conteo_materias)
        
        # Ordenar por periodo DESC para obtener el último intento
        historial_limpio = historial_limpio.sort_values(["periodo"], ascending=False)
        
        # Crear columna de badge para múltiples intentos
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
            
            # Mostrar solo el último intento de cada materia
            grupo_df_unico = grupo_df.drop_duplicates(subset=["clave"], keep="first")
            
            aprobadas = (grupo_df_unico["estatus"] == "APROBADA").sum()
            total = len(grupo_df_unico)
            creditos = grupo_df_unico[grupo_df_unico["estatus"] == "APROBADA"]["creditos"].sum()
            
            with st.expander(f"📅 {nombre_ciclo}  |  {aprobadas}/{total} aprobadas  |  {creditos} créditos", expanded=expandir):
                display_df = grupo_df_unico[["clave", "nombre", "calificacion", "creditos", "estatus", "badge_intento"]].copy()
                
                # Formatear calificación (manejar None)
                display_df["calificacion"] = display_df["calificacion"].apply(
                    lambda x: f"{x:.1f}" if x is not None and isinstance(x, (int, float)) else "S/A" if x is None else str(x)
                )
                
                # Agregar badge a nombre si hay múltiples intentos
                display_df["nombre"] = display_df["nombre"] + display_df["badge_intento"]
                
                display_df["estatus"] = display_df["estatus"].map(lambda e: f"{estatus_color.get(e, '')} {e}")
                display_df = display_df[["clave", "nombre", "calificacion", "creditos", "estatus"]]
                display_df.columns = ["Clave", "Asignatura", "Calificación", "Créditos", "Estatus"]
                st.dataframe(display_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
