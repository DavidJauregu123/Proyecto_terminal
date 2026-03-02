"""
Parser para el Historial Académico de la Universidad del Caribe.
Extrae el mapa curricular: {clave: {ciclo, categoria, nombre, creditos}}
Los ciclos son: Primer Ciclo=1, Segundo Ciclo=2, Tercer Ciclo=3, Cuarto Ciclo=4
"""
import pdfplumber
import re
from typing import Dict, Optional
from dataclasses import dataclass, field


@dataclass
class InfoMateria:
    """Información de una materia según el historial académico"""
    clave: str
    nombre: str
    ciclo: int          # 1, 2, 3, 4
    categoria: str      # BASICA, ELECCION_LIBRE, PRE_ESPECIALIDAD, CO_CURRICULAR
    creditos: int
    calificacion: Optional[str] = None   # La nota que tiene el estudiante (puede ser vacía)


class HistorialParser:
    """Parser para el PDF de Historial Académico de UniCaribe"""

    # Mapeo de texto del PDF a número de ciclo
    CICLOS_TEXTO = {
        "primer ciclo": 1,
        "segundo ciclo": 2,
        "tercer ciclo": 3,
        "cuarto ciclo": 4,
        "tercer y cuarto ciclo": 3,  # materias compartidas, asignamos ciclo 3
    }

    CATEGORIAS_TEXTO = {
        "básica": "BASICA",
        "basica": "BASICA",
        "elección libre": "ELECCION_LIBRE",
        "eleccion libre": "ELECCION_LIBRE",
        "pre-especialidad": "PRE_ESPECIALIDAD",
        "co-curricular": "CO_CURRICULAR",
    }

    def __init__(self):
        self.materias: Dict[str, InfoMateria] = {}
        self.creditos_totales: int = 0
        self.creditos_acumulados: int = 0

    def parse_historial(self, ruta_pdf: str) -> Dict[str, InfoMateria]:
        """
        Parsea el historial académico y retorna un dict {clave: InfoMateria}
        """
        with pdfplumber.open(ruta_pdf) as pdf:
            texto_completo = ""
            for page in pdf.pages:
                texto = page.extract_text()
                if texto:
                    texto_completo += texto + "\n"

        self.materias = self._extraer_materias(texto_completo)
        self._extraer_creditos(texto_completo)
        return self.materias
    
    def _extraer_creditos(self, texto: str):
        """
        Extrae los créditos totales y acumulados del historial académico
        Formato: "TOTAL DE CREDITOS DE LA LICENCIATURA: 404"
                 "Total de Créditos Acumulados: 378"
        """
        # Buscar créditos totales de la licenciatura
        match = re.search(r'TOTAL DE CR[ÉE]DITOS DE LA LICENCIATURA:\s*(\d+)', texto, re.IGNORECASE)
        if match:
            self.creditos_totales = int(match.group(1))
        
        # Buscar créditos acumulados
        match = re.search(r'Total de Cr[ée]ditos Acumulados:\s*(\d+)', texto, re.IGNORECASE)
        if match:
            self.creditos_acumulados = int(match.group(1))

    def _extraer_materias(self, texto: str) -> Dict[str, InfoMateria]:
        """
        Recorre el texto línea a línea identificando:
        - Encabezados de ciclo: "Primer Ciclo", "Segundo Ciclo", etc.
        - Encabezados de categoría: "BÁSICA", "ELECCIÓN LIBRE", etc.
        - Filas de materia: SEMESTRE CLAVE Nombre CREDITOS [CALIFICACION]
          Ejemplo: '1,2 DP0001 Propedéutico de habilidades... 6 10'
        """
        materias = {}
        ciclo_actual = 0
        categoria_actual = "BASICA"

        re_ciclo = re.compile(
            r'(primer ciclo|segundo ciclo|tercer ciclo|cuarto ciclo|tercer y cuarto ciclo)',
            re.IGNORECASE
        )
        re_categoria = re.compile(
            r'^(BÁSICA|BASICA|ELECCIÓN LIBRE|ELECCION LIBRE|PRE-ESPECIALIDAD|CO-CURRICULAR)',
            re.IGNORECASE
        )
        # Formato: SEMESTRE(x,y o "x al y") CLAVE Nombre CREDITOS [CALIFICACION]
        re_materia = re.compile(
            r'^(?:\d[\d,a-z\s]*?\s+)?([A-Z]{2,4}\d{4})\s+(.+?)\s+(\d+)(?:\s+(\S+))?\s*$',
            re.IGNORECASE
        )

        for linea in texto.splitlines():
            linea_strip = linea.strip()
            if not linea_strip:
                continue

            # Detectar encabezado de ciclo
            m_ciclo = re_ciclo.search(linea_strip.lower())
            if m_ciclo:
                texto_ciclo = m_ciclo.group(1).lower()
                ciclo_actual = self.CICLOS_TEXTO.get(texto_ciclo, ciclo_actual)
                continue

            # Detectar encabezado de categoría
            m_cat = re_categoria.match(linea_strip)
            if m_cat:
                key = linea_strip.lower().split('\n')[0]
                # Normalizar acentos
                key = key.replace('á','a').replace('é','e').replace('ó','o').replace('ú','u')
                for k, v in self.CATEGORIAS_TEXTO.items():
                    if key.startswith(k):
                        categoria_actual = v
                        break
                continue

            # Saltar líneas que son encabezados de tabla o totales
            if linea_strip.startswith("SEMESTRE") or re.match(r'^\d+$', linea_strip) or linea_strip.startswith("Total"):
                continue

            # Detectar fila de materia (empieza con semestre "1,2" o "5 al 8")
            # El semestre puede ser: "1,2", "3,4", "5,6", "7,8", "1 al 8", "5 al 8"
            m_mat = re.match(
                r'^(\d[\d,]* |(?:\d+ al \d+) )([A-Z]{2,4}\d{4})\s+(.+?)\s+(\d+)(?:\s+(\S+))?\s*$',
                linea_strip
            )
            if m_mat and ciclo_actual > 0:
                clave = m_mat.group(2)
                nombre = m_mat.group(3).strip()
                creditos = int(m_mat.group(4))
                calificacion = m_mat.group(5) if m_mat.group(5) else None

                if clave not in materias:
                    materias[clave] = InfoMateria(
                        clave=clave,
                        nombre=nombre,
                        ciclo=ciclo_actual,
                        categoria=categoria_actual,
                        creditos=creditos,
                        calificacion=calificacion
                    )

        return materias

    def to_mapa_ciclos(self) -> Dict[str, int]:
        """Retorna un dict simplificado {clave: ciclo} para uso del KardexParser"""
        return {clave: info.ciclo for clave, info in self.materias.items()}

    def to_mapa_curricular(self) -> Dict[str, dict]:
        """Retorna el mapa curricular completo compatible con AcademicProcessor"""
        return {
            clave: {
                "ciclo": info.ciclo,
                "categoria": info.categoria,
                "creditos": info.creditos,
                "nombre": info.nombre
            }
            for clave, info in self.materias.items()
        }
