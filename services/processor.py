from typing import Dict, List, Tuple
from dataclasses import dataclass
import pandas as pd


@dataclass
class ProgresoCiclo:
    """Progreso académico por ciclo"""
    ciclo: int
    finalizadas: int
    en_curso: int
    reprobadas: int
    total: int
    porcentaje: float


class AcademicProcessor:
    """Procesa datos académicos para generar reportes y análisis"""
    
    def __init__(self, mapa_curricular: Dict[str, Dict]):
        """
        Inicializa el procesador
        
        Args:
            mapa_curricular: Diccionario con estructura del mapa curricular
                            {clave_materia: {ciclo, categoria, creditos, ...}}
        """
        self.mapa_curricular = mapa_curricular
    
    def calcular_progreso_por_ciclo(self, historial_df: pd.DataFrame) -> Dict[int, ProgresoCiclo]:
        """
        Calcula el progreso académico por ciclo.
        Usa la columna 'ciclo' del DataFrame si existe,
        con fallback al mapa_curricular.
        """
        progreso_por_ciclo = {}
        
        tiene_ciclo = "ciclo" in historial_df.columns
        
        for _, row in historial_df.iterrows():
            clave = row["clave"]
            
            if tiene_ciclo and row.get("ciclo", 0) > 0:
                ciclo = int(row["ciclo"])
            elif clave in self.mapa_curricular:
                ciclo = self.mapa_curricular[clave].get("ciclo", 0)
            else:
                continue
            
            if ciclo not in progreso_por_ciclo:
                progreso_por_ciclo[ciclo] = {"finalizadas": 0, "en_curso": 0, "reprobadas": 0, "total": 0}
            
            progreso_por_ciclo[ciclo]["total"] += 1
            estatus = row["estatus"]
            if estatus == "APROBADA":
                progreso_por_ciclo[ciclo]["finalizadas"] += 1
            elif estatus == "EN_CURSO":
                progreso_por_ciclo[ciclo]["en_curso"] += 1
            elif estatus == "REPROBADA":
                progreso_por_ciclo[ciclo]["reprobadas"] += 1
        
        resultado = {}
        for ciclo, datos in progreso_por_ciclo.items():
            porcentaje = (datos["finalizadas"] / datos["total"] * 100) if datos["total"] > 0 else 0
            resultado[ciclo] = ProgresoCiclo(
                ciclo=ciclo,
                finalizadas=datos["finalizadas"],
                en_curso=datos["en_curso"],
                reprobadas=datos["reprobadas"],
                total=datos["total"],
                porcentaje=round(porcentaje, 2)
            )
        
        return resultado
    
    def calcular_requisitos(self, historial_df: pd.DataFrame) -> Dict[str, bool]:
        """
        Detecta si el estudiante cumple los requisitos adicionales basándose
        en las claves de materias del kardex.
        
        - Inglés: materias con prefijo LI (ej: LI1102, LI0109) con S/A=aprobada o calificacion
        - Actividad Deportiva: materias con prefijo AD
        - Actividad Cultural: materias con prefijo TA o AC
        """
        requisitos = {"Inglés": False, "Actividad Deportiva": False, "Actividad Cultural": False}
        
        for _, row in historial_df.iterrows():
            clave = str(row.get("clave", ""))
            estatus = row.get("estatus", "")
            
            # Inglés: LI#### con calificación o estatus SIN_REGISTRAR (S/A = aprobado en UdC)
            if clave.startswith("LI") and estatus in ("APROBADA", "SIN_REGISTRAR"):
                requisitos["Inglés"] = True
            
            # Deportiva: AD####
            if clave.startswith("AD") and estatus in ("APROBADA", "SIN_REGISTRAR"):
                requisitos["Actividad Deportiva"] = True
            
            # Cultural: TA#### o AC####
            if (clave.startswith("TA") or clave.startswith("AC")) and estatus in ("APROBADA", "SIN_REGISTRAR"):
                requisitos["Actividad Cultural"] = True
        
        return requisitos
    
    def identificar_alertas(self, historial_df: pd.DataFrame, situacion: str = "REGULAR") -> List[Dict]:
        """
        Identifica alertas académicas según las reglas
        
        Args:
            historial_df: DataFrame con historial
            situacion: Situación académica del estudiante (REGULAR, IRREGULAR, etc.)
            
        Returns:
            Lista de alertas
        """
        alertas = []
        
        # Contar intentos por materia (solo contar registros con calificación o reprobadas)
        intentos_por_materia = {}
        reprobadas_por_materia = {}
        materias_actualmente_reprobadas = set()  # Materias que siguen reprobadas
        
        for _, row in historial_df.iterrows():
            clave = row["clave"]
            estatus = row["estatus"]
            
            # Solo contar intentos reales (no EN_CURSO sin calificación)
            if estatus in ("APROBADA", "REPROBADA"):
                intentos_por_materia[clave] = intentos_por_materia.get(clave, 0) + 1
            
            # Contar solo reprobadas
            if estatus == "REPROBADA":
                reprobadas_por_materia[clave] = reprobadas_por_materia.get(clave, 0) + 1
        
        # Identificar materias que siguen reprobadas (no fueron re-cursadas y aprobadas)
        for clave, count_reprobadas in reprobadas_por_materia.items():
            # Verificar si la materia fue aprobada después o está siendo cursada actualmente
            aprobada = ((historial_df["clave"] == clave) & (historial_df["estatus"] == "APROBADA")).any()
            en_curso = ((historial_df["clave"] == clave) & (historial_df["estatus"] == "EN_CURSO")).any()
            if not aprobada and not en_curso:
                materias_actualmente_reprobadas.add(clave)
        
        # Regla 1: Tercera Oportunidad (2 o más reprobaciones = en tercera oportunidad)
        for clave in materias_actualmente_reprobadas:
            count = reprobadas_por_materia.get(clave, 0)
            if count >= 3:
                alertas.append({
                    "tipo": "BAJA_AUTOMÁTICA",
                    "materia_clave": clave,
                    "descripcion": f"⚠️ CRÍTICO: La materia {clave} ha sido reprobada {count} veces. Contacte con coordinación académica URGENTEMENTE.",
                    "severidad": "CRITICA"
                })
            elif count >= 2:
                alertas.append({
                    "tipo": "TERCERA_OPORTUNIDAD",
                    "materia_clave": clave,
                    "descripcion": f"⚠️ La materia {clave} está en tercera oportunidad (reprobada {count} veces). Una reprobación más resulta en baja automática.",
                    "severidad": "CRITICA"
                })
        
        # Regla 2: Solo mostrar alertas de materias reprobadas si hay reprobadas SIN recuperar
        total_reprobadas_activas = len(materias_actualmente_reprobadas)
        
        # Si el estudiante es REGULAR, no debería tener materias reprobadas activas
        if situacion.upper() == "REGULAR" and total_reprobadas_activas > 0:
            # Caso excepcional: estudiante marcado como regular pero tiene reprobadas
            # Probablemente son materias en proceso de regularización
            pass
        elif total_reprobadas_activas >= 3:
            alertas.append({
                "tipo": "ALUMNO_IRREGULAR",
                "descripcion": f"El estudiante presenta irregularidad académica con {total_reprobadas_activas} materias reprobadas sin regularizar",
                "severidad": "ADVERTENCIA"
            })
        elif total_reprobadas_activas >= 1 and situacion.upper() != "REGULAR":
            alertas.append({
                "tipo": "MATERIAS_REPROBADAS",
                "descripcion": f"El estudiante tiene {total_reprobadas_activas} materia(s) reprobada(s) pendiente(s) de regularizar",
                "severidad": "ADVERTENCIA"
            })
        
        return alertas
    
    def calcular_requisitos_adicionales(self) -> Dict[str, bool]:
        """
        Calcula el estado de requisitos adicionales
        
        Returns:
            Dictionary con estado de cada requisito
        """
        # Este método será completado cuando se integre con BD
        return {
            "actividad_deportiva": False,
            "actividad_cultural": False,
            "ingles": False
        }
    
    def validar_seriacion(self, clave_materia: str, historial_df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Valida si una materia está desbloqueada según requisitos
        
        Args:
            clave_materia: Clave de la materia a validar
            historial_df: Historial del estudiante
            
        Returns:
            (puede_tomar, lista_de_requisitos_faltantes)
        """
        if clave_materia not in self.mapa_curricular:
            return True, []
        
        info_materia = self.mapa_curricular[clave_materia]
        requisitos = info_materia.get("requisitos", [])
        
        requisitos_faltantes = []
        for requisito_clave in requisitos:
            # Buscar si ya está aprobada
            aprobada = (
                (historial_df["clave"] == requisito_clave) & 
                (historial_df["estatus"] == "APROBADA")
            ).any()
            
            if not aprobada:
                requisitos_faltantes.append(requisito_clave)
        
        puede_tomar = len(requisitos_faltantes) == 0
        return puede_tomar, requisitos_faltantes
