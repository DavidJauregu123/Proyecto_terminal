"""
Parser para el Historial Académico de la Universidad del Caribe.
Extrae el mapa curricular: {clave: {ciclo, categoria, nombre, creditos}}
Los ciclos son: Primer Ciclo=1, Segundo Ciclo=2, Tercer Ciclo=3, Cuarto Ciclo=4

También extrae el estatus de cada materia:
- Si tiene calificación numérica o "S" → APROBADA
- Si no tiene calificación → PENDIENTE (no cursada o sin aprobar aún)
"""
import pdfplumber
import pandas as pd
import re
from typing import Dict, List, Optional
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
    estatus: str = "PENDIENTE"  # APROBADA si tiene calificación, PENDIENTE si no


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

    # Cadena de inglés ordenada de menor a mayor nivel
    # Mapea tanto códigos del plan 2021ID como códigos legacy (LI)
    # Nivel máximo requerido para cumplir requisito de inglés
    NIVEL_INGLES_REQUERIDO = 6  # Tópicos 2 (ID0606)

    CADENA_INGLES = [
        {"nivel": 1, "nombres": ["nivel 1"], "codigos": ["ID0107", "LI1101"]},
        {"nivel": 2, "nombres": ["nivel 2"], "codigos": ["ID0207", "LI1102"]},
        {"nivel": 3, "nombres": ["nivel 3"], "codigos": ["ID0307", "LI1103"]},
        {"nivel": 4, "nombres": ["nivel 4"], "codigos": ["ID0406"]},
        {"nivel": 5, "nombres": ["tópicos 1", "topicos 1", "tópicos selectos de inglés i", "topicos selectos de ingles i"], "codigos": ["ID0507"]},
        {"nivel": 6, "nombres": ["tópicos 2", "topicos 2", "tópicos selectos de inglés ii", "topicos selectos de ingles ii"], "codigos": ["ID0606"]},
    ]

    def __init__(self):
        self.materias: Dict[str, InfoMateria] = {}
        self.creditos_totales: int = 0
        self.creditos_acumulados: int = 0
        self.nivel_ingles_aprobado: int = 0  # 0=ninguno, 1=Nivel 1, 2=Nivel 2, etc.
        self.nivel_ingles_texto: str = ""     # Texto original del PDF
        self.codigos_ingles_aprobados: set = set()  # Códigos auto-aprobados por inglés
        self.ingles_completo: bool = False    # True solo si llegó a Tópicos 2

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
        self._extraer_nivel_ingles(texto_completo)
        return self.materias

    def _extraer_nivel_ingles(self, texto: str):
        """
        Extrae el último nivel de inglés aprobado del historial.
        Formato: "Último nivel de Inglés aprobado: Nivel 2 Inglés"
        o: "Último nivel de Inglés aprobado: Tópicos 2"
        """
        match = re.search(
            r'[UÚ]ltimo\s+nivel\s+de\s+[Ii]ngl[eé]s\s+aprobado:\s*(.+?)(?:\n|$)',
            texto, re.IGNORECASE
        )
        if not match:
            return

        texto_nivel = match.group(1).strip().lower()
        # Quitar "inglés" o "ingles" del final para normalizar
        texto_nivel_norm = re.sub(r'\s*ingl[eé]s\s*$', '', texto_nivel).strip()
        self.nivel_ingles_texto = match.group(1).strip()

        # Buscar el nivel en la cadena
        nivel_encontrado = 0
        for entry in self.CADENA_INGLES:
            for nombre in entry["nombres"]:
                if nombre in texto_nivel_norm or texto_nivel_norm in nombre:
                    nivel_encontrado = max(nivel_encontrado, entry["nivel"])

        self.nivel_ingles_aprobado = nivel_encontrado
        self.ingles_completo = (nivel_encontrado >= self.NIVEL_INGLES_REQUERIDO)

        # Generar conjunto de códigos auto-aprobados (todos los niveles ≤ al aprobado)
        self.codigos_ingles_aprobados = set()
        for entry in self.CADENA_INGLES:
            if entry["nivel"] <= nivel_encontrado:
                for codigo in entry["codigos"]:
                    self.codigos_ingles_aprobados.add(codigo)
    
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

                # Determinar estatus basado en calificación
                estatus = "PENDIENTE"
                if calificacion is not None:
                    cal_str = str(calificacion).strip().upper()
                    if cal_str in ("S", "S/A"):
                        estatus = "APROBADA"
                    else:
                        try:
                            cal_num = float(cal_str)
                            if cal_num >= 7.0:
                                estatus = "APROBADA"
                            elif cal_num > 0:
                                # Tiene calificación pero < 7 (raro en historial, pero posible)
                                estatus = "APROBADA"  # Si aparece en historial con nota, está aprobada
                            # cal_num == 0 → sin calificar
                        except ValueError:
                            # No es número ni S/A, tratar como pendiente
                            pass

                if clave not in materias:
                    materias[clave] = InfoMateria(
                        clave=clave,
                        nombre=nombre,
                        ciclo=ciclo_actual,
                        categoria=categoria_actual,
                        creditos=creditos,
                        calificacion=calificacion,
                        estatus=estatus
                    )

        return materias

    def obtener_aprobadas(self) -> set:
        """
        Retorna el conjunto de claves de materias aprobadas según el historial.
        Incluye materias de inglés auto-aprobadas por nivel.
        """
        aprobadas = {clave for clave, info in self.materias.items() if info.estatus == "APROBADA"}
        # Agregar códigos de inglés auto-aprobados por nivel
        aprobadas |= self.codigos_ingles_aprobados
        return aprobadas

    def to_dataframe(self) -> pd.DataFrame:
        """
        Genera un DataFrame con todas las materias del historial académico.
        Columnas: clave, nombre, ciclo, categoria, creditos, calificacion, estatus
        """
        data = []
        for clave, info in self.materias.items():
            cal = None
            if info.calificacion is not None:
                cal_str = str(info.calificacion).strip().upper()
                if cal_str in ("S", "S/A"):
                    cal = None  # Sin nota numérica pero aprobada
                else:
                    try:
                        cal = float(cal_str)
                    except ValueError:
                        cal = None

            data.append({
                "clave": info.clave,
                "nombre": info.nombre,
                "ciclo": info.ciclo,
                "categoria": info.categoria,
                "creditos": info.creditos,
                "calificacion": cal,
                "estatus": info.estatus,
                "periodo": "",  # El historial no tiene periodo específico
            })
        return pd.DataFrame(data)

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
