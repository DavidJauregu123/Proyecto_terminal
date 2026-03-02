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
from services.local_database import LocalDatabaseService
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
    
    # Ordenar por periodo descendente (más reciente primero)
    df_ordenado = historial_df.sort_values("periodo", ascending=False)
    
    # Quedarse con el primer registro de cada clave (el más reciente)
    df_ultimo = df_ordenado.drop_duplicates(subset=["clave"], keep="first")
    
    # Reordenar por ciclo y clave para mantener orden lógico
    df_ultimo = df_ultimo.sort_values(["ciclo", "clave"])
    
    return df_ultimo


def calcular_progreso_preespecialidades(historial_df: pd.DataFrame, mapa_curricular: dict) -> dict:
    """
    Calcula el progreso en cada pre-especialidad.
    Cada pre-especialidad necesita 5 materias para completarse.
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
                # Determinar a qué pre-especialidad pertenece por el nombre
                if "inteligencia" in nombre.lower() and ("negocios" in nombre.lower() or "organizacional" in nombre.lower()):
                    pre_esp = "Inteligencia Organizacional y de Negocios"
                elif "innovación" in nombre.lower() or "innovacion" in nombre.lower() or "tic" in nombre.lower():
                    pre_esp = "Innovación en TIC"
                else:
                    # Si no podemos determinar por nombre, intentar por código
                    # ID3416-ID3419, ID3469 = IoN
                    if clave in ["ID3416", "ID3417", "ID3418", "ID3419", "ID3469"]:
                        pre_esp = "Inteligencia Organizacional y de Negocios"
                    else:
                        pre_esp = "Innovación en TIC"
                
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
                    db = LocalDatabaseService()
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
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Matrícula", datos.matricula)
    with col2:
        st.metric("Plan de Estudios", datos.plan_estudios)
    with col3:
        st.metric("Créditos Acumulados", f"{creditos_acumulados}/{creditos_totales}")
    with col4:
        st.metric("Promedio General", f"{datos.promedio_general:.2f}")
    
    # Mostrar créditos faltantes en métrica destacada
    col_cred1, col_cred2, col_cred3 = st.columns(3)
    with col_cred2:
        st.metric("⏳ Créditos Faltantes", creditos_faltantes, 
                 delta=f"-{creditos_faltantes} para graduarse" if creditos_faltantes > 0 else "✅ Completado",
                 delta_color="inverse")
    
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
            cols = st.columns(len(ciclos_validos))
            for j, ciclo in enumerate(ciclos_validos):
                progreso = progreso_ciclos[ciclo]
                
                with cols[j]:
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
            st.info("No hay datos de progreso por ciclo.")
    except Exception as e:
        st.warning(f"Error al calcular progreso: {str(e)}")
    
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
