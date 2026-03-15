"""
Integración del Sistema Experto de Seriación con el Processor Académico

Proporciona funciones para ejecutar el sistema experto usando datos 
de la base de datos PostgreSQL.
"""

import sys
from pathlib import Path
from typing import List, Dict, Tuple
import pandas as pd

# Importar el sistema experto
from agents.sistema_experto_seriacion import ejecutar_sistema_experto


class ProcessadorSeriacionExacerbado:
    """
    Integra el sistema experto con datos de PostgreSQL y genera
    planes semestres recomendados más allá de si las reglas eran.
    """
    
    def __init__(self, db_service=None, mapa_curricular: Dict = None):
        """
        Args:
            db_service: Servicio de base de datos con métodos para obtener datos
            mapa_curricular: Dict con estructura {clave: {ciclo, nombre, requisitos...}}
        """
        self.db_service = db_service
        self.mapa_curricular = mapa_curricular or {}
    
    def obtener_datos_estudiante(self, estudiante_id: str) -> Dict:
        """
        Obtiene datos del estudiante desde la BD o estructura base.
        
        Returns:
            {id, nombre, promedio, total_creditos}
        """
        # Si hay BD, usar datos reales, si no retornar estructura base
        if self.db_service and hasattr(self.db_service, 'get_student'):
            try:
                estudiante = self.db_service.get_student(estudiante_id)
                return {
                    "id": estudiante_id,
                    "nombre": estudiante.get("nombre", ""),
                    "promedio": float(estudiante.get("promedio_general", 0.0)),
                    "total_creditos": int(estudiante.get("total_creditos", 0))
                }
            except:
                pass
        
        # Fallback - estructura base
        return {
            "id": estudiante_id,
            "nombre": "",
            "promedio": 0.0,
            "total_creditos": 0
        }
    
    def obtener_historial_academico(self, estudiante_id: str) -> List[Dict]:
        """
        Obtiene el historial de materias aprobadas del estudiante.
        
        Returns:
            [
                {
                    "clave_materia": "ID0101",
                    "calificacion": 8.5,
                    "creditos_obtenidos": 8
                },
                ...
            ]
        """
        if self.db_service and hasattr(self.db_service, 'get_academic_history'):
            try:
                historial = self.db_service.get_academic_history(estudiante_id)
                return [
                    {
                        "clave_materia": h.get("materia_clave", ""),
                        "calificacion": float(h.get("calificacion", 0.0)),
                        "creditos_obtenidos": int(h.get("creditos_obtenidos", 0))
                    }
                    for h in historial
                    if h.get("estatus") == "APROBADA"
                ]
            except:
                pass
        
        return []
    
    def obtener_materias_en_curso(self, estudiante_id: str) -> List[str]:
        """
        Obtiene materias que el estudiante está cursando actualmente.
        
        Returns:
            ["ID0201", "ID0202", ...]
        """
        if self.db_service and hasattr(self.db_service, 'get_current_courses'):
            try:
                materias = self.db_service.get_current_courses(estudiante_id)
                return [m.get("materia_clave", "") for m in materias]
            except:
                pass
        
        return []
    
    def analizar_estudiante_completo(self, estudiante_id: str) -> Dict:
        """
        Ejecuta análisis completo del estudiante:
        1. Obtiene datos de la BD
        2. Ejecuta sistema experto
        3. Genera reportes
        
        Returns:
            {
                "estudiante": {...},
                "ciclo_actual": int,
                "ciclo_recomendado": int,
                "progreso": {ciclo: porcentaje},
                "materias_recomendadas": [...],
                "alertas": [...],
                "resumen": {...}
            }
        """
        # Obtener datos
        datos_est = self.obtener_datos_estudiante(estudiante_id)
        historial = self.obtener_historial_academico(estudiante_id)
        materias_curso = self.obtener_materias_en_curso(estudiante_id)
        
        # Ejecutar sistema experto
        resultado = ejecutar_sistema_experto(
            datos_est,
            historial,
            materias_curso
        )
        
        # Calcular progreso por ciclo
        progreso = self._calcular_progreso_por_ciclo(historial)
        ciclo_actual = self._detectar_ciclo_actual(progreso)
        
        # Generar resumen
        resumen = self._generar_resumen(
            ciclo_actual,
            resultado,
            progreso,
            datos_est
        )
        
        return {
            "estudiante": datos_est,
            "ciclo_actual": ciclo_actual,
            "ciclo_recomendado": resultado["ciclo_recomendado"],
            "progreso_por_ciclo": progreso,
            "materias_recomendadas": resultado["materias_recomendadas"],
            "alertas": resultado["alertas"],
            "resumen": resumen
        }
    
    def _calcular_progreso_por_ciclo(self, historial: List[Dict]) -> Dict[int, Dict]:
        """
        Calcula porcentaje de créditos completados por ciclo.
        
        Returns:
            {
                1: {"créditos_obtenidos": 50, "créditos_totales": 54, "porcentaje": 92.6},
                2: {...},
                ...
            }
        """
        progreso = {}
        
        # Totales por ciclo
        creditos_por_ciclo = {}
        for clave, datos in self.mapa_curricular.items():
            ciclo = datos["ciclo"]
            creditos = datos["creditos"]
            
            if ciclo not in creditos_por_ciclo:
                creditos_por_ciclo[ciclo] = {"total": 0, "obtenidos": 0}
            
            creditos_por_ciclo[ciclo]["total"] += creditos
            
            # Verificar si está aprobada
            for h in historial:
                if h["clave_materia"] == clave:
                    creditos_por_ciclo[ciclo]["obtenidos"] += h["creditos_obtenidos"]
                    break
        
        # Calcular porcentaje
        for ciclo in sorted(creditos_por_ciclo.keys()):
            datos = creditos_por_ciclo[ciclo]
            porcentaje = (datos["obtenidos"] / datos["total"] * 100) if datos["total"] > 0 else 0
            
            progreso[ciclo] = {
                "créditos_obtenidos": datos["obtenidos"],
                "créditos_totales": datos["total"],
                "porcentaje": round(porcentaje, 1),
                "completado": porcentaje >= 75
            }
        
        return progreso
    
    def _detectar_ciclo_actual(self, progreso: Dict[int, Dict]) -> int:
        """
        Detecta el ciclo actual basándose en el progreso (>75% = completado).
        """
        ciclo_actual = 1
        for ciclo in sorted(progreso.keys()):
            if progreso[ciclo]["completado"]:
                ciclo_actual = ciclo + 1
            else:
                break
        return ciclo_actual
    
    def _generar_resumen(
        self,
        ciclo_actual: int,
        resultado: Dict,
        progreso: Dict,
        datos_est: Dict
    ) -> Dict:
        """
        Genera un resumen ejecutivo del análisis.
        """
        ciclo_progress = progreso.get(ciclo_actual, {})
        
        return {
            "ciclo_actual": ciclo_actual,
            "porcentaje_ciclo_actual": ciclo_progress.get("porcentaje", 0),
            "creditos_obtenidos_ciclo": ciclo_progress.get("créditos_obtenidos", 0),
            "creditos_totales_ciclo": ciclo_progress.get("créditos_totales", 0),
            "promedio_general": datos_est.get("promedio", 0.0),
            "materias_recomendadas": len(resultado["materias_recomendadas"]),
            "créditos_recomendados": sum(m["creditos"] for m in resultado["materias_recomendadas"]),
            "alertas_criticas": len([a for a in resultado["alertas"] if a["tipo"] == "BLOQUEO"]),
            "alertas_ligadura": len([a for a in resultado["alertas"] if a["tipo"] == "LIGADURA"])
        }
    
    def generar_plan_semestral(
        self,
        estudiante_id: str,
        semestres_futuro: int = 2
    ) -> Dict:
        """
        Genera un plan de semestres futuros considerando carga académica
        y recomendaciones del sistema experto.
        
        Args:
            estudiante_id: ID del estudiante
            semestres_futuro: Cuántos semestres futuros proyectar
        
        Returns:
            {
                "semestre_actual": int,
                "plan": [
                    {
                        "semestre": 1,
                        "materias": [...],
                        "créditos_totales": int,
                        "carga_recomendada": bool
                    },
                    ...
                ]
            }
        """
        # Análisis completo
        analisis = self.analizar_estudiante_completo(estudiante_id)
        
        ciclo_recomendado = analisis["ciclo_recomendado"]
        materias_recomendadas = analisis["materias_recomendadas"]
        
        # Agrupar materias por ciclo futuro
        plan = []
        materias_asignadas = set()
        
        for sem in range(semestres_futuro):
            ciclo_objetivo = ciclo_recomendado + sem
            
            # Materias disponibles para este ciclo
            materias_ciclo = [
                m for m in materias_recomendadas
                if m["ciclo"] == ciclo_objetivo and m["clave"] not in materias_asignadas
            ]
            
            # Limitar carga (máximo 6 materias o 48 créditos aprox)
            creditos_semestre = 0
            materias_sem = []
            
            for mat in materias_ciclo:
                if creditos_semestre + mat["creditos"] <= 48:
                    materias_sem.append(mat)
                    creditos_semestre += mat["creditos"]
                    materias_asignadas.add(mat["clave"])
            
            plan.append({
                "semestre": sem + 1,
                "ciclo": ciclo_objetivo,
                "materias": materias_sem,
                "créditos_totales": creditos_semestre,
                "materias_count": len(materias_sem),
                "carga_recomendada": creditos_semestre >= 24  # Mínimo académico
            })
        
        return {
            "semestre_actual": analisis["ciclo_actual"],
            "ciclo_recomendado": ciclo_recomendado,
            "plan": plan,
            "materias_totales_plan": len(materias_asignadas)
        }


def ejemplo_uso():
    """Ejemplo de uso sin BD (para prueba)"""
    import json
    
    # Cargar mapa curricular
    ruta_mapa = Path("data/mapa_curricular_2021ID_real_completo.json")
    with open(ruta_mapa, 'r', encoding='utf-8') as f:
        mapa = json.load(f)
    
    # Crear procesador
    procesador = ProcessadorSeriacionExacerbado(mapa_curricular=mapa)
    
    # Datos de prueba
    datos_est = {
        "id": "EST001",
        "nombre": "Juan Pérez",
        "promedio": 8.5,
        "total_creditos": 54
    }
    
    historial = [
        {"clave_materia": "ID0001", "calificacion": 9.0, "creditos_obtenidos": 6},
        {"clave_materia": "ID0101", "calificacion": 8.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0102", "calificacion": 9.0, "creditos_obtenidos": 8},
        {"clave_materia": "ID0103", "calificacion": 8.0, "creditos_obtenidos": 8},
        {"clave_materia": "ID0104", "calificacion": 8.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0105", "calificacion": 7.5, "creditos_obtenidos": 8},
        {"clave_materia": "ID0106", "calificacion": 9.0, "creditos_obtenidos": 6},
        {"clave_materia": "ID0107", "calificacion": 8.5, "creditos_obtenidos": 3},
    ]
    
    # Ejecutar
    resultado = ejecutar_sistema_experto(datos_est, historial)
    
    print("\n" + "=" * 70)
    print(f"Estudiante: {datos_est['nombre']}")
    print(f"Ciclo Recomendado: {resultado['ciclo_recomendado']}")
    print(f"Materias Recomendadas: {resultado['total_materias_recomendadas']}")
    print("=" * 70)
    
    for mat in resultado["materias_recomendadas"][:5]:
        print(f"  {mat['clave']} - {mat['nombre']}")


if __name__ == "__main__":
    ejemplo_uso()
