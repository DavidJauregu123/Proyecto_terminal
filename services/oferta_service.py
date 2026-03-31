"""
Servicio de Oferta Académica
Parsea el CSV de secciones y filtra por candidatas del sistema experto.
"""

import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Set


# Mapeo de columnas del CSV a nombres internos
DIAS = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado"]

COL_INICIO = {
    "Lunes": "Lunes_I",
    "Martes": "Martes_I",
    "Miercoles": "Miercoles_I",
    "Jueves": "Jueves_I",
    "Viernes": "Viernes_I",
    "Sabado": "Sabado_I",
}

COL_FIN = {
    "Lunes": "Lunes_F",
    "Martes": "Martes_F",
    "Miercoles": "Miercoles_F",
    "Jueves": "Jueves_F",
    "Viernes": "Viernes_F",
    "Sabado": "Sabado_F",
}

COL_ESPACIO = {
    "Lunes": "Lunes_Espacio",
    "Martes": "Martes_Espacio",
    "Miercoles": "Miercoles_Espacio",
    "Jueves": "Jueves_Espacio",
    "Viernes": "Viernes_Espacio",
    "Sabado": "Sabado_Espacio",
}


def _parse_hora(valor) -> Optional[int]:
    """Convierte '07:00' o '7:00' a 7. Retorna None si es '00:00' o inválido."""
    try:
        s = str(valor).strip()
        if not s or s == "00:00" or s == "nan":
            return None
        partes = s.split(":")
        h = int(partes[0])
        if h == 0:
            return None
        return h
    except (ValueError, IndexError):
        return None


def parsear_horario_seccion(row: pd.Series) -> List[Dict]:
    """
    Extrae los bloques horarios de una fila del CSV.

    IMPORTANTE: Solo cuenta un día si tiene un espacio/salón asignado.
    El CSV tiene valores residuales en columnas de hora para días sin clase,
    así que el espacio (aula) es el indicador fiable de si hay clase ese día.

    Returns:
        Lista de bloques: [{"dia": "Lunes", "inicio": 7, "fin": 9, "espacio": "B-01"}, ...]
    """
    bloques = []
    for dia in DIAS:
        # Verificar que hay espacio/salón asignado (indica clase real ese día)
        espacio = str(row.get(COL_ESPACIO[dia], "")).strip()
        if not espacio or espacio == "nan" or espacio == "":
            continue

        inicio = _parse_hora(row.get(COL_INICIO[dia]))
        fin = _parse_hora(row.get(COL_FIN[dia]))
        if inicio is not None and fin is not None and fin > inicio:
            bloques.append({
                "dia": dia,
                "inicio": inicio,
                "fin": fin,
                "espacio": espacio,
            })
    return bloques


def cargar_oferta_csv(ruta_csv: Optional[str] = None) -> pd.DataFrame:
    """
    Carga el CSV de oferta académica.

    Args:
        ruta_csv: Ruta al CSV. Si None, busca el más reciente en agents/OfertaAcademica/

    Returns:
        DataFrame con las secciones
    """
    if ruta_csv is None:
        carpeta = Path(__file__).parent.parent / "agents" / "OfertaAcademica"
        # Preferir IRSecciones_193.csv (oferta actual)
        preferido = carpeta / "IRSecciones_193.csv"
        if preferido.exists():
            ruta_csv = str(preferido)
        else:
            csvs = sorted(carpeta.glob("IRSecciones_*.csv"), reverse=True)
            if not csvs:
                return pd.DataFrame()
            ruta_csv = str(csvs[0])

    try:
        df = pd.read_csv(ruta_csv, encoding="latin-1")
        df["Clave"] = df["Clave"].astype(str).str.strip().str.upper()
        return df
    except Exception as e:
        print(f"Error cargando oferta: {e}")
        return pd.DataFrame()


def filtrar_oferta_por_candidatas(
    df_oferta: pd.DataFrame,
    candidatas_detalles: List[Dict],
) -> List[Dict]:
    """
    Filtra la oferta académica dejando solo secciones de materias candidatas.
    Enriquece cada sección con datos del sistema experto (prioridad, nivel, razón).

    Returns:
        Lista de secciones disponibles con horarios parseados:
        [{
            "clave": str, "nombre": str, "seccion": int,
            "profesor": str, "cupo": int, "inscritos": int, "cupo_disponible": int,
            "horario": [{"dia": str, "inicio": int, "fin": int, "espacio": str}],
            "creditos": int, "ciclo": int, "categoria": str,
            "prioridad": int, "nivel": str, "razon": str,
            "modalidad": str,
        }]
    """
    if df_oferta.empty or not candidatas_detalles:
        return []

    # Crear lookup de candidatas por clave
    cand_lookup = {}
    for det in candidatas_detalles:
        cand_lookup[det["clave"].upper()] = det

    claves_candidatas = set(cand_lookup.keys())

    # Filtrar secciones que matchean con candidatas
    mask = df_oferta["Clave"].isin(claves_candidatas)
    df_filtrado = df_oferta[mask].copy()

    secciones = []
    for _, row in df_filtrado.iterrows():
        clave = row["Clave"]
        info_cand = cand_lookup.get(clave, {})

        horario = parsear_horario_seccion(row)
        if not horario:
            continue  # Sección sin horario válido, saltar

        cupo = int(row.get("Cupo", 0) or 0)
        inscritos = int(row.get("Inscritos", 0) or 0)

        secciones.append({
            "clave": clave,
            "nombre": info_cand.get("nombre", str(row.get("Asignatura", ""))),
            "seccion": int(row.get("Seccion", 0) or 0),
            "profesor": str(row.get("Profesor", "")).strip(),
            "cupo": cupo,
            "inscritos": inscritos,
            "cupo_disponible": max(0, cupo - inscritos),
            "horario": horario,
            "creditos": info_cand.get("creditos", 0),
            "ciclo": info_cand.get("ciclo", 0),
            "categoria": info_cand.get("categoria", ""),
            "prioridad": info_cand.get("prioridad", 5),
            "nivel": info_cand.get("nivel", ""),
            "razon": info_cand.get("razon", ""),
            "modalidad": str(row.get("Modalidad Desc", "")).strip(),
        })

    # Ordenar por prioridad, luego ciclo
    secciones.sort(key=lambda s: (s["prioridad"], s["ciclo"], s["clave"], s["seccion"]))
    return secciones


def verificar_choque_horario(bloques_a: List[Dict], bloques_b: List[Dict]) -> bool:
    """
    Verifica si dos conjuntos de bloques horarios chocan.

    Returns:
        True si hay choque, False si son compatibles.
    """
    for ba in bloques_a:
        for bb in bloques_b:
            if ba["dia"] == bb["dia"]:
                # Hay choque si los rangos se solapan
                if ba["inicio"] < bb["fin"] and bb["inicio"] < ba["fin"]:
                    return True
    return False


def verificar_disponibilidad(
    bloques: List[Dict],
    disponibilidad: Dict[str, List[int]]
) -> bool:
    """
    Verifica si los bloques horarios de una sección caben en la disponibilidad.

    Args:
        bloques: Horario de la sección
        disponibilidad: {"Lunes": [7,8,9,10,...], "Martes": [7,8,9], ...}
                       Horas disponibles por día.

    Returns:
        True si todos los bloques caben en la disponibilidad.
    """
    for bloque in bloques:
        dia = bloque["dia"]
        horas_disponibles = set(disponibilidad.get(dia, []))
        if not horas_disponibles:
            return False  # Día no disponible
        # Cada hora del bloque debe estar en la disponibilidad
        horas_bloque = set(range(bloque["inicio"], bloque["fin"]))
        if not horas_bloque.issubset(horas_disponibles):
            return False
    return True
