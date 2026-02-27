import pdfplumber
import pandas as pd
import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class MateriaRegistro:
    """Registro de una materia del estudiante"""
    clave: str
    nombre: str
    periodo: str
    calificacion: Optional[float]
    creditos: int
    estatus: str  # APROBADA, REPROBADA, EN_CURSO, SIN_REGISTRAR
    ciclo: int = 0  # Cuatrimestre inferido del orden cronológico de periodos


@dataclass
class DatosEstudiante:
    """Datos extraídos del kardex"""
    matricula: str
    nombre: str
    plan_estudios: str
    situacion: str
    total_creditos: int
    promedio_general: float
    materias: List[MateriaRegistro]


class KardexParser:
    """Parser para extraer datos de archivos PDF de Kardex"""
    
    def __init__(self):
        self.datos_estudiante: Optional[DatosEstudiante] = None
    
    def parse_kardex(self, ruta_pdf: str) -> DatosEstudiante:
        """
        Extrae información del kardex PDF
        
        Args:
            ruta_pdf: Ruta del archivo PDF
            
        Returns:
            DatosEstudiante con toda la información extraída
        """
        with pdfplumber.open(ruta_pdf, raise_unicode_errors=False) as pdf:
            texto_completo = ""
            for page in pdf.pages:
                try:
                    texto_extraido = page.extract_text()
                except Exception:
                    texto_extraido = ""
                if texto_extraido:
                    texto_completo += texto_extraido + "\n"
            
            datos_estudiante = self._extraer_datos_encabezado(texto_completo)
            materias = self._extraer_materias_texto(texto_completo)
            totales = self._extraer_totales(texto_completo)
            
            # Asignar ciclo desde el mapa curricular oficial (no por orden cronológico)
            import json
            from pathlib import Path as _Path
            mapa_path = _Path(__file__).parent.parent / "data" / "mapa_curricular_2021ID.json"
            mapa_curricular_local = {}
            if mapa_path.exists():
                with open(mapa_path, "r", encoding="utf-8") as _f:
                    mapa_curricular_local = json.load(_f)
            for m in materias:
                m.ciclo = mapa_curricular_local.get(m.clave, {}).get("ciclo", 0)
            
            self.datos_estudiante = DatosEstudiante(
                matricula=datos_estudiante.get("matricula", ""),
                nombre=datos_estudiante.get("nombre", ""),
                plan_estudios=datos_estudiante.get("plan_estudios", ""),
                situacion=datos_estudiante.get("situacion", ""),
                total_creditos=totales.get("total_creditos", 0),
                promedio_general=totales.get("promedio_general", 0.0),
                materias=materias
            )
            
            return self.datos_estudiante
    
    def _extraer_datos_encabezado(self, texto: str) -> Dict[str, str]:
        """Extrae datos del encabezado (matrícula, nombre, plan)"""
        datos = {}
        
        match = re.search(r"Matricula:\s*(\d+)", texto)
        if match:
            datos["matricula"] = match.group(1)
        
        match = re.search(r"Nombre:\s*(.+?)(?:\n|Plan de Estudios)", texto)
        if match:
            datos["nombre"] = match.group(1).strip()
        
        match = re.search(r"Plan de Estudios:\s*(\S+)", texto)
        if match:
            datos["plan_estudios"] = match.group(1)
        
        match = re.search(r"Situaci[oó]n:\s*(\w+)", texto)
        if match:
            datos["situacion"] = match.group(1)
        
        return datos
    
    def _extraer_materias_texto(self, texto: str) -> List[MateriaRegistro]:
        """
        Extrae materias del texto plano del PDF.
        Formato: [*]CLAVE Nombre PERIODO OP# CALIFICACION CREDITOS
        También soporta: [*]CLAVE Nombre PERIODO OP# CREDITOS (sin calificación, en curso)
        """
        materias = []
        # Clave: 2-4 letras + 4 dígitos (ej: DP0001, PID0201, IT0208)
        # Calificacion es opcional (ausente cuando la materia está en curso sin nota)
        patron = re.compile(
            r'^\*?([A-Z]{2,4}\d{4})\s+(.+?)\s+(\d{6})\s+OP\d+\s+(\S+?)(?:\s+(\d+))?\s*$',
            re.MULTILINE
        )
        
        for match in patron.finditer(texto):
            clave = match.group(1).strip()
            nombre = match.group(2).strip()
            periodo = match.group(3).strip()
            campo4 = match.group(4).strip()   # calificacion, o creditos si no hay grupo5
            campo5 = match.group(5)           # creditos (puede ser None)
            
            # Determinar calificacion y creditos según campos disponibles
            if campo5 is not None:
                # Formato completo: OP# CALIFICACION CREDITOS
                calificacion_str = campo4
                creditos_str = campo5
            else:
                # Solo un campo al final: es creditos, sin calificación (en curso)
                calificacion_str = ""
                creditos_str = campo4
            
            # Procesar calificación y estatus
            calificacion = None
            if calificacion_str.upper() in ("S/A", "--", ""):
                estatus = "SIN_REGISTRAR" if calificacion_str.upper() == "S/A" else "EN_CURSO"
            else:
                try:
                    calificacion = float(calificacion_str)
                    estatus = "APROBADA" if calificacion >= 6.0 else "REPROBADA"
                except ValueError:
                    estatus = "EN_CURSO"
            
            # Materia con asterisco = reprobada (aunque tenga nota >= 6 en reposición)
            linea = match.group(0)
            if linea.lstrip().startswith("*") and calificacion is not None and calificacion < 6.0:
                estatus = "REPROBADA"
            
            try:
                creditos = int(creditos_str)
            except ValueError:
                creditos = 0
            
            materias.append(MateriaRegistro(
                clave=clave,
                nombre=nombre,
                periodo=periodo,
                calificacion=calificacion,
                creditos=creditos,
                estatus=estatus
            ))
        
        return materias
    
    def _extraer_materias(self, pdf) -> List[MateriaRegistro]:
        """Método legacy - ya no se usa, mantenido por compatibilidad"""
        return []
    
    def _procesar_fila_materia(self, fila: Tuple) -> Optional[MateriaRegistro]:
        """Método legacy - ya no se usa, mantenido por compatibilidad"""
        return None
    
    def _extraer_totales(self, texto: str) -> Dict[str, float]:
        """
        Extrae promedio general y créditos totales.
        En el PDF de la UniCaribe el formato es: '8.14 38' (promedio créditos)
        Toma el último match para evitar subtotales de página.
        """
        datos = {"total_creditos": 0, "promedio_general": 0.0}
        
        # Intentar formato etiquetado primero
        match = re.search(r"Total de Cr[eé]ditos\s*[:\s]\s*(\d+)", texto)
        if match:
            datos["total_creditos"] = int(match.group(1))
        
        match = re.search(r"Promedio General\s*[:\s]\s*([\d.]+)", texto)
        if match:
            datos["promedio_general"] = float(match.group(1))
        
        # Si no encontró etiquetas, buscar líneas con solo "float int" (totales del PDF)
        if datos["total_creditos"] == 0:
            patron_totales = re.compile(r'^\s*([\d]+\.[\d]+)\s+(\d+)\s*$', re.MULTILINE)
            todos = patron_totales.findall(texto)
            if todos:
                # Tomar el último (total final, no subtotales de página)
                ultimo = todos[-1]
                try:
                    datos["promedio_general"] = float(ultimo[0])
                    datos["total_creditos"] = int(ultimo[1])
                except (ValueError, IndexError):
                    pass
        
        return datos
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convierte los datos a un DataFrame de pandas"""
        if not self.datos_estudiante:
            return pd.DataFrame()
        
        data = []
        for materia in self.datos_estudiante.materias:
            data.append({
                "clave": materia.clave,
                "nombre": materia.nombre,
                "periodo": materia.periodo,
                "ciclo": materia.ciclo,
                "calificacion": materia.calificacion,
                "creditos": materia.creditos,
                "estatus": materia.estatus
            })
        
        return pd.DataFrame(data)
