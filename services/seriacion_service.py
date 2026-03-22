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
    planes semestrales recomendados.
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
        if self.db_service and hasattr(self.db_service, 'get_student'):
            try:
                estudiante = self.db_service.get_student(estudiante_id)
                return {
                    "id": estudiante_id,
                    "nombre": estudiante.get("nombre", ""),
                    "promedio": float(estudiante.get("promedio_general", 0.0)),
                    "total_creditos": int(estudiante.get("total_creditos", 0))
                }
            except Exception:
                pass

        return {
            "id": estudiante_id,
            "nombre": "",
            "promedio": 0.0,
            "total_creditos": 0
        }

    def obtener_historial_academico(self, estudiante_id: str) -> List[Dict]:
        """
        Obtiene el historial de materias del estudiante desde la BD.
        Retorna en el formato que espera ejecutar_sistema_experto:
        [{clave, estatus, calificacion, creditos}, ...]
        """
        if self.db_service and hasattr(self.db_service, 'get_academic_history'):
            try:
                historial = self.db_service.get_academic_history(estudiante_id)
                return [
                    {
                        "clave": h.get("materia_clave", ""),
                        "estatus": h.get("estatus", "PENDIENTE"),
                        "calificacion": float(h.get("calificacion", 0.0)),
                        "creditos": int(h.get("creditos_obtenidos", 0))
                    }
                    for h in historial
                ]
            except Exception:
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
            except Exception:
                pass

        return []

    def _mapa_como_lista(self) -> List[Dict]:
        """Convierte el mapa curricular de dict a lista para el sistema experto."""
        if isinstance(self.mapa_curricular, list):
            return self.mapa_curricular
        resultado = []
        for clave, info in self.mapa_curricular.items():
            if isinstance(info, dict):
                entrada = dict(info)
                entrada["clave"] = str(clave).strip().upper()
                resultado.append(entrada)
        return resultado

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
                "progreso": {ciclo: porcentaje},
                "candidatas_detalles": [...],
                "candidatas_count": int,
                "especialidad_detectada": str | None,
                "resumen": {...}
            }
        """
        datos_est = self.obtener_datos_estudiante(estudiante_id)
        historial = self.obtener_historial_academico(estudiante_id)

        # Ejecutar sistema experto con la firma correcta
        mapa_lista = self._mapa_como_lista()
        resultado = ejecutar_sistema_experto(
            historial_academico=historial,
            mapa_curricular=mapa_lista if mapa_lista else None
        )

        # Calcular progreso por ciclo
        historial_creditos = [
            {
                "clave_materia": h.get("clave", ""),
                "creditos_obtenidos": h.get("creditos", 0)
            }
            for h in historial
            if h.get("estatus", "").upper() == "APROBADA"
        ]
        progreso = self._calcular_progreso_por_ciclo(historial_creditos)
        ciclo_actual = resultado.get("ciclo_actual", 1)

        resumen = self._generar_resumen(
            ciclo_actual,
            resultado,
            progreso,
            datos_est
        )

        return {
            "estudiante": datos_est,
            "ciclo_actual": ciclo_actual,
            "progreso_por_ciclo": progreso,
            "candidatas_detalles": resultado.get("candidatas_detalles", []),
            "candidatas_count": resultado.get("candidatas_count", 0),
            "especialidad_detectada": resultado.get("especialidad_detectada"),
            "debug": resultado.get("debug", {}),
            "resumen": resumen
        }

    def _calcular_progreso_por_ciclo(self, historial: List[Dict]) -> Dict[int, Dict]:
        """
        Calcula porcentaje de créditos completados por ciclo.

        Args:
            historial: Lista de {clave_materia, creditos_obtenidos}

        Returns:
            {
                1: {"creditos_obtenidos": 50, "creditos_totales": 54, "porcentaje": 92.6},
                2: {...},
                ...
            }
        """
        progreso = {}

        creditos_por_ciclo = {}
        for clave, datos in self.mapa_curricular.items():
            ciclo = datos.get("ciclo", 0)
            creditos = datos.get("creditos", 0)

            if ciclo not in creditos_por_ciclo:
                creditos_por_ciclo[ciclo] = {"total": 0, "obtenidos": 0}

            creditos_por_ciclo[ciclo]["total"] += creditos

            for h in historial:
                if h["clave_materia"] == clave:
                    creditos_por_ciclo[ciclo]["obtenidos"] += h["creditos_obtenidos"]
                    break

        for ciclo in sorted(creditos_por_ciclo.keys()):
            datos = creditos_por_ciclo[ciclo]
            porcentaje = (datos["obtenidos"] / datos["total"] * 100) if datos["total"] > 0 else 0

            progreso[ciclo] = {
                "creditos_obtenidos": datos["obtenidos"],
                "creditos_totales": datos["total"],
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
        """Genera un resumen ejecutivo del análisis."""
        ciclo_progress = progreso.get(ciclo_actual, {})

        return {
            "ciclo_actual": ciclo_actual,
            "porcentaje_ciclo_actual": ciclo_progress.get("porcentaje", 0),
            "creditos_obtenidos_ciclo": ciclo_progress.get("creditos_obtenidos", 0),
            "creditos_totales_ciclo": ciclo_progress.get("creditos_totales", 0),
            "promedio_general": datos_est.get("promedio", 0.0),
            "candidatas_count": resultado.get("candidatas_count", 0),
            "creditos_recomendados": sum(
                m.get("creditos", 0) for m in resultado.get("candidatas_detalles", [])
            ),
        }

    def generar_plan_semestral(
        self,
        estudiante_id: str,
        semestres_futuro: int = 2
    ) -> Dict:
        """
        Genera un plan de semestres futuros considerando carga académica
        y recomendaciones del sistema experto.
        """
        analisis = self.analizar_estudiante_completo(estudiante_id)

        ciclo_actual = analisis["ciclo_actual"]
        candidatas = analisis["candidatas_detalles"]

        plan = []
        materias_asignadas = set()

        for sem in range(semestres_futuro):
            ciclo_objetivo = ciclo_actual + sem

            materias_ciclo = [
                m for m in candidatas
                if m.get("ciclo") == ciclo_objetivo
                and m.get("clave") not in materias_asignadas
            ]

            creditos_semestre = 0
            materias_sem = []

            for mat in materias_ciclo:
                if creditos_semestre + mat.get("creditos", 0) <= 48:
                    materias_sem.append(mat)
                    creditos_semestre += mat.get("creditos", 0)
                    materias_asignadas.add(mat["clave"])

            plan.append({
                "semestre": sem + 1,
                "ciclo": ciclo_objetivo,
                "materias": materias_sem,
                "creditos_totales": creditos_semestre,
                "materias_count": len(materias_sem),
                "carga_recomendada": creditos_semestre >= 24
            })

        return {
            "semestre_actual": ciclo_actual,
            "plan": plan,
            "materias_totales_plan": len(materias_asignadas)
        }


def ejemplo_uso():
    """Ejemplo de uso sin BD (para prueba)"""
    import json

    ruta_mapa = Path("data/mapa_curricular_2021ID_real_completo.json")
    with open(ruta_mapa, 'r', encoding='utf-8') as f:
        mapa = json.load(f)

    # Historial en el formato que espera ejecutar_sistema_experto
    historial = [
        {"clave": "ID0001", "estatus": "APROBADA", "calificacion": 9.0, "creditos": 6},
        {"clave": "ID0101", "estatus": "APROBADA", "calificacion": 8.5, "creditos": 8},
        {"clave": "ID0102", "estatus": "APROBADA", "calificacion": 9.0, "creditos": 8},
        {"clave": "ID0103", "estatus": "APROBADA", "calificacion": 8.0, "creditos": 8},
        {"clave": "ID0104", "estatus": "APROBADA", "calificacion": 8.5, "creditos": 8},
        {"clave": "ID0105", "estatus": "APROBADA", "calificacion": 7.5, "creditos": 8},
        {"clave": "ID0106", "estatus": "APROBADA", "calificacion": 9.0, "creditos": 6},
        {"clave": "ID0107", "estatus": "APROBADA", "calificacion": 8.5, "creditos": 3},
    ]

    resultado = ejecutar_sistema_experto(historial)

    print("\n" + "=" * 70)
    print(f"Ciclo actual: {resultado['ciclo_actual']}")
    print(f"Materias candidatas: {resultado['candidatas_count']}")
    print("=" * 70)

    for mat in resultado["candidatas_detalles"][:5]:
        print(f"  {mat['clave']} - {mat['nombre']}")


if __name__ == "__main__":
    ejemplo_uso()
