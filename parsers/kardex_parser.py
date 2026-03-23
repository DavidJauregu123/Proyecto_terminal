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
        with pdfplumber.open(ruta_pdf) as pdf:
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
            
            # Asignar ciclo desde el mapa curricular oficial (semestres 1-8)
            import json
            from pathlib import Path as _Path
            mapa_path = _Path(__file__).parent.parent / "data" / "mapa_curricular_2021ID_real_completo.json"
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
        
        # Extraer nombre completo (formato: APELLIDO / NOMBRE)
        match = re.search(r"Nombre:\s*([A-ZÁÉÍÓÚÑ\s/]+?)\s*(\d{6,}|Plan de Estudios|Situaci)", texto, re.IGNORECASE)
        if match:
            nombre_completo = match.group(1).strip()
            # Convertir "APELLIDO / NOMBRE" a "Nombre Apellido"
            if "/" in nombre_completo:
                partes = nombre_completo.split("/")
                apellido = partes[0].strip().title()
                nombre = partes[1].strip().title() if len(partes) > 1 else ""
                datos["nombre"] = f"{nombre} {apellido}".strip()
            else:
                datos["nombre"] = nombre_completo.title()
        
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

        Regla importante del kardex actual:
        - En la carga más reciente, valores N/A, N o NP con 0 créditos suelen
            indicar materia inscrita sin cierre final del periodo.
        - Si además hubo reprobación previa, después el dashboard la reclasifica
            como RECURSANDO.
        
        Reglas de estatus:
        - ÚLTIMO PERIODO + creditos=0 → SIEMPRE EN_CURSO (periodo aún no cierra)
        - PERIODOS ANTERIORES:
          - Asterisco (*) → REPROBADA (asignatura reprobada)
          - N/A → REPROBADA (no aprobada)
          - S/A → APROBADA (sí aprobada)
          - Calificación >= 7 → APROBADA
          - Calificación 1-6 → REPROBADA
          - Calificación 0 con creditos=0 → REPROBADA si tiene asterisco, sino EN_CURSO
          - Sin calificación / S/G / -- → EN_CURSO

        Simbología del kardex:
        - S/G = Sin grupo registrado
        - *   = Asignatura Reprobada
        - N/A = Asignatura NO aprobada
        - S/A = Asignatura SÍ aprobada
        - BTT = Baja Temporal a Tiempo
        """
        materias = []
        # NOTA: Usar [ \t] en las partes opcionales finales para NO consumir \n
        # Si se usa \s+ ahí, el regex come el newline y se traga la siguiente línea
        patron = re.compile(
            r'^(?:BTT\s+)?\*?([A-Z]{2,4}\d{4})\s+(.+?)\s+(\d{6})\s+OP\d+\s+(\S+?)(?:[ \t]+(\d+))?(?:[ \t]+.*)?$',
            re.MULTILINE
        )
        # Detectar líneas BTT para marcarlas como BAJA_TEMPORAL
        patron_btt = re.compile(
            r'^BTT\s+\*?[A-Z]{2,4}\d{4}\s+.+?\s+(\d{6})\s+OP\d+',
            re.MULTILINE
        )
        periodos_btt = set(m.group(1) for m in patron_btt.finditer(texto))

        # Encontrar el ÚLTIMO PERÍODO
        periodo_patron = re.compile(r'\d{6}')
        periodos_encontrados = sorted(set(p for p in periodo_patron.findall(texto)))
        ultimo_periodo = periodos_encontrados[-1] if periodos_encontrados else None

        for match in patron.finditer(texto):
            clave = match.group(1).strip()
            nombre = match.group(2).strip()
            periodo = match.group(3).strip()
            campo4 = match.group(4).strip()
            campo5 = match.group(5)
            linea = match.group(0)
            es_btt = linea.lstrip().upper().startswith("BTT")
            tiene_asterisco = linea.lstrip().startswith("*") or (
                es_btt and "*" in linea.split(clave)[0]
            )
            es_ultimo_periodo = (periodo == ultimo_periodo)

            # BTT = Baja Temporal a Tiempo: el estudiante se dio de baja
            # de este periodo. No cuenta como cursada ni como reprobada.
            if es_btt:
                calificacion = None
                creditos_val = 0
                materias.append(MateriaKardex(
                    clave=clave, nombre=nombre, periodo=periodo,
                    ciclo=0, calificacion=calificacion,
                    creditos=creditos_val, estatus="BAJA_TEMPORAL"
                ))
                continue

            # Determinar si campo4 es calificación o créditos
            campo4_es_numero = False
            try:
                int(campo4)
                campo4_es_numero = True
            except ValueError:
                pass

            # Separar calificación y créditos
            if campo5 is not None:
                calificacion_str = campo4
                creditos_str = campo5
            elif campo4_es_numero:
                calificacion_str = ""
                creditos_str = campo4
            else:
                calificacion_str = campo4
                creditos_str = "0"

            try:
                creditos = int(creditos_str)
            except ValueError:
                creditos = 0

            cal_upper = calificacion_str.upper().strip()

            # ═══════════════════════════════════════════════════
            # ÚLTIMO PERIODO: Todo es EN_CURSO (periodo no ha cerrado)
            # El asterisco en el último periodo NO significa reprobada,
            # solo indica que la materia fue reprobada antes.
            # ═══════════════════════════════════════════════════
            if es_ultimo_periodo and creditos == 0:
                estatus = "EN_CURSO"
                calificacion = None

            # ═══════════════════════════════════════════════════
            # PERIODOS ANTERIORES con creditos=0:
            # Aquí sí importa el asterisco y N/A
            # ═══════════════════════════════════════════════════
            elif not es_ultimo_periodo and creditos == 0:
                calificacion = None
                if tiene_asterisco:
                    # Asterisco en periodo anterior = REPROBADA
                    estatus = "REPROBADA"
                elif cal_upper in ("N/A", "N", "NP"):
                    # N/A en periodo anterior = REPROBADA
                    estatus = "REPROBADA"
                elif cal_upper == "S/A":
                    estatus = "APROBADA"
                else:
                    # Sin marca clara, tratar como EN_CURSO (baja o incompleta)
                    estatus = "EN_CURSO"

            # ═══════════════════════════════════════════════════
            # CUALQUIER PERIODO con creditos > 0: procesar calificación
            # ═══════════════════════════════════════════════════
            else:
                calificacion = None

                if cal_upper == "S/A":
                    estatus = "APROBADA"
                elif cal_upper in ("N/A", "N", "NP"):
                    estatus = "REPROBADA"
                    calificacion = 0.0
                elif cal_upper in ("", "--", "S/G"):
                    estatus = "EN_CURSO"
                else:
                    try:
                        calificacion = float(calificacion_str)
                        if calificacion == 0.0:
                            # Calificación 0 con créditos > 0 en último periodo = EN_CURSO
                            # En periodos anteriores con asterisco = REPROBADA
                            if es_ultimo_periodo:
                                estatus = "EN_CURSO"
                                calificacion = None
                            elif tiene_asterisco:
                                estatus = "REPROBADA"
                            else:
                                estatus = "EN_CURSO"
                                calificacion = None
                        elif calificacion >= 7.0:
                            estatus = "APROBADA"
                        else:
                            estatus = "REPROBADA"
                    except ValueError:
                        estatus = "EN_CURSO"
                        calificacion = None

                # Asterisco con calificación < 7 y créditos > 0 = REPROBADA
                if tiene_asterisco and calificacion is not None and calificacion < 7.0 and creditos > 0:
                    estatus = "REPROBADA"

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
