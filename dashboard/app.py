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
    }
    .alerta-critica {
        background-color: #ffdddd;
        border-left: 4px solid #ff4444;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    }
    .alerta-advertencia {
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    }
    .requisito-completado {
        color: #28a745;
    }
    .requisito-pendiente {
        color: #dc3545;
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
                        mapa = generar_mapa("temp_historial.pdf")
                        if os.path.exists("temp_historial.pdf"):
                            os.remove("temp_historial.pdf")

                        # Guardar en disco y en session_state
                        mapa_path = Path(__file__).parent.parent / "data" / "mapa_curricular_2021ID.json"
                        mapa_path.parent.mkdir(exist_ok=True)
                        with open(mapa_path, "w", encoding="utf-8") as f:
                            json.dump(mapa, f, ensure_ascii=False, indent=2)
                        st.session_state.mapa_curricular = mapa

                    st.success(f"✅ Mapa actualizado: {len(mapa)} materias cargadas")
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
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Matrícula", datos.matricula)
    with col2:
        st.metric("Plan de Estudios", datos.plan_estudios)
    with col3:
        st.metric("Total Créditos", datos.total_creditos)
    with col4:
        st.metric("Promedio General", f"{datos.promedio_general:.2f}")
    
    st.markdown("---")
    
    # ========== SECCIÓN 2: ALERTAS ACADÉMICAS ==========
    st.header("⚠️ Alertas Académicas")
    
    mapa_curricular = cargar_mapa_curricular()
    processor = AcademicProcessor(mapa_curricular)
    
    try:
        alertas = processor.identificar_alertas(historial_df)
        
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
        progreso_ciclos = processor.calcular_progreso_por_ciclo(historial_df)
        
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
    
    # ========== SECCIÓN 4: REQUISITOS ADICIONALES ==========
    st.header("📋 Requisitos Adicionales")
    
    try:
        requisitos = processor.calcular_requisitos(historial_df)
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
        
        if "ciclo" in historial_df.columns:
            grupos = historial_df.sort_values(["ciclo", "clave"]).groupby("ciclo", sort=True)
        else:
            grupos = historial_df.sort_values(["periodo", "clave"]).groupby("periodo", sort=True)
        
        for grupo_key, grupo_df in grupos:
            ciclo_num = int(grupo_key) if "ciclo" in historial_df.columns else 0
            nombre_ciclo = NOMBRES_CICLO.get(ciclo_num, f"Ciclo {ciclo_num}")
            expandir = ciclo_num == 1
            
            aprobadas = (grupo_df["estatus"] == "APROBADA").sum()
            total = len(grupo_df)
            creditos = grupo_df[grupo_df["estatus"] == "APROBADA"]["creditos"].sum()
            
            with st.expander(f"📅 {nombre_ciclo}  |  {aprobadas}/{total} aprobadas  |  {creditos} créditos", expanded=expandir):
                display_df = grupo_df[["clave", "nombre", "calificacion", "creditos", "estatus"]].copy()
                display_df["estatus"] = display_df["estatus"].map(lambda e: f"{estatus_color.get(e, '')} {e}")
                display_df.columns = ["Clave", "Asignatura", "Calificación", "Créditos", "Estatus"]
                st.dataframe(display_df, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
