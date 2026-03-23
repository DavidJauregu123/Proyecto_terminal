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
    recursando: int = 0
    pendientes: int = 0
    total: int = 0
    porcentaje: float = 0.0


class AcademicProcessor:
    """Procesa datos académicos para generar reportes y análisis"""
    
    def __init__(self, mapa_curricular):
        """
        Inicializa el procesador.

        Args:
            mapa_curricular: dict {clave: {ciclo, ...}} o list [{clave, ciclo, ...}]
        """
        if isinstance(mapa_curricular, list):
            self.mapa_curricular = {
                m.get("clave", ""): m
                for m in mapa_curricular
                if isinstance(m, dict) and m.get("clave")
            }
        elif isinstance(mapa_curricular, dict):
            self.mapa_curricular = mapa_curricular
        else:
            self.mapa_curricular = {}
    
    def calcular_progreso_por_ciclo(self, historial_df: pd.DataFrame) -> Dict[int, ProgresoCiclo]:
        """
        Calcula el progreso académico por ciclo incluyendo materias pendientes.
        Usa la columna 'ciclo' del DataFrame si existe,
        con fallback al mapa_curricular.
        """
        progreso_por_ciclo = {}
        
        # Obtener materias cursadas por el estudiante
        materias_cursadas = set(historial_df["clave"].unique()) if "clave" in historial_df.columns else set()
        
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
                progreso_por_ciclo[ciclo] = {"finalizadas": 0, "en_curso": 0, "reprobadas": 0, "recursando": 0, "pendientes": 0, "total": 0}

            progreso_por_ciclo[ciclo]["total"] += 1
            estatus = row["estatus"]
            if estatus == "APROBADA":
                progreso_por_ciclo[ciclo]["finalizadas"] += 1
            elif estatus == "RECURSANDO":
                progreso_por_ciclo[ciclo]["recursando"] += 1
            elif estatus == "EN_CURSO":
                progreso_por_ciclo[ciclo]["en_curso"] += 1
            elif estatus == "REPROBADA":
                progreso_por_ciclo[ciclo]["reprobadas"] += 1
        
        # Contar materias pendientes por ciclo (del mapa curricular)
        # Solo se cuentan BÁSICAS (no PID) como pendientes obligatorias.
        # Las EL y PREESPECIALIDAD no son obligatorias de forma individual
        # (el alumno elige cuáles tomar), por lo que no inflan el conteo.
        ciclos_en_mapa = sorted(set(
            info.get("ciclo", 0)
            for info in self.mapa_curricular.values()
            if info.get("ciclo", 0) > 0
        ))
        for ciclo in ciclos_en_mapa:
            if ciclo not in progreso_por_ciclo:
                progreso_por_ciclo[ciclo] = {"finalizadas": 0, "en_curso": 0, "reprobadas": 0, "recursando": 0, "pendientes": 0, "total": 0}

            # Solo BÁSICAS no-PID cuentan como materias obligatorias pendientes
            materias_del_ciclo = [
                m for m, info in self.mapa_curricular.items()
                if info.get("ciclo") == ciclo
                and info.get("categoria") == "BASICA"
                and not str(m).strip().upper().startswith("PID")
            ]
            materias_no_cursadas = [m for m in materias_del_ciclo if m not in materias_cursadas]
            progreso_por_ciclo[ciclo]["pendientes"] = len(materias_no_cursadas)
            progreso_por_ciclo[ciclo]["total"] += len(materias_no_cursadas)
        
        resultado = {}
        for ciclo, datos in progreso_por_ciclo.items():
            porcentaje = (datos["finalizadas"] / (datos["total"] - datos["pendientes"]) * 100) if (datos["total"] - datos["pendientes"]) > 0 else 0
            resultado[ciclo] = ProgresoCiclo(
                ciclo=ciclo,
                finalizadas=datos["finalizadas"],
                en_curso=datos["en_curso"],
                reprobadas=datos["reprobadas"],
                recursando=datos["recursando"],
                pendientes=datos["pendientes"],
                total=datos["total"],
                porcentaje=round(porcentaje, 2)
            )
        
        return resultado
    
    def calcular_requisitos(self, historial_df: pd.DataFrame, ingles_completo: bool = False) -> Dict[str, bool]:
        """
        Detecta si el estudiante cumple los requisitos adicionales.

        - Inglés: Solo se marca como cumplido si el historial académico indica
          "Tópicos 2" aprobado (ingles_completo=True).
        - Actividad Deportiva: materias con prefijo AD aprobadas
        - Actividad Cultural: materias con prefijo TA o AC aprobadas
        """
        requisitos = {"Inglés": ingles_completo, "Actividad Deportiva": False, "Actividad Cultural": False}

        for _, row in historial_df.iterrows():
            clave = str(row.get("clave", ""))
            estatus = row.get("estatus", "")

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
        
        # Construir diccionario de nombres {clave: nombre}
        nombres_materias = {}
        for _, row in historial_df.iterrows():
            clave = row["clave"]
            nombre = row.get("nombre", "")
            if clave and nombre:
                nombres_materias[clave] = nombre

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
            en_curso = ((historial_df["clave"] == clave) & (historial_df["estatus"].isin(["EN_CURSO", "RECURSANDO"]))).any()
            if not aprobada and not en_curso:
                materias_actualmente_reprobadas.add(clave)

        # Regla 1: Tercera Oportunidad (2 o más reprobaciones = en tercera oportunidad)
        for clave in materias_actualmente_reprobadas:
            count = reprobadas_por_materia.get(clave, 0)
            nombre = nombres_materias.get(clave, clave)
            if count >= 3:
                alertas.append({
                    "tipo": "BAJA_AUTOMÁTICA",
                    "materia_clave": clave,
                    "descripcion": f"⚠️ CRÍTICO: La materia {clave} - {nombre} ha sido reprobada {count} veces. Contacte con coordinación académica URGENTEMENTE.",
                    "severidad": "CRITICA"
                })
            elif count >= 2:
                alertas.append({
                    "tipo": "TERCERA_OPORTUNIDAD",
                    "materia_clave": clave,
                    "descripcion": f"⚠️ La materia {clave} - {nombre} está en tercera oportunidad (reprobada {count} veces). Una reprobación más resulta en baja automática.",
                    "severidad": "CRITICA"
                })

        # Regla 2: Solo mostrar alertas de materias reprobadas si hay reprobadas SIN recuperar
        total_reprobadas_activas = len(materias_actualmente_reprobadas)

        # Listar materias reprobadas activas con nombre
        lista_reprobadas = [f"{c} - {nombres_materias.get(c, c)}" for c in sorted(materias_actualmente_reprobadas)]
        detalle_reprobadas = "; ".join(lista_reprobadas) if lista_reprobadas else ""

        # Si el estudiante es REGULAR, no debería tener materias reprobadas activas
        if situacion.upper() == "REGULAR" and total_reprobadas_activas > 0:
            pass
        elif total_reprobadas_activas >= 3:
            alertas.append({
                "tipo": "ALUMNO_IRREGULAR",
                "descripcion": f"El estudiante presenta irregularidad académica con {total_reprobadas_activas} materias reprobadas sin regularizar: {detalle_reprobadas}",
                "severidad": "ADVERTENCIA"
            })
        elif total_reprobadas_activas >= 1 and situacion.upper() != "REGULAR":
            alertas.append({
                "tipo": "MATERIAS_REPROBADAS",
                "descripcion": f"El estudiante tiene {total_reprobadas_activas} materia(s) reprobada(s) pendiente(s) de regularizar: {detalle_reprobadas}",
                "severidad": "ADVERTENCIA"
            })

        # Regla 3: Atraso en Prácticas Profesionales
        # Determinar semestre actual basado en el historial
        aprobadas_set = set(
            str(row["clave"]).strip().upper()
            for _, row in historial_df.iterrows()
            if row.get("estatus", "").upper() == "APROBADA"
        )
        en_curso_set = set(
            str(row["clave"]).strip().upper()
            for _, row in historial_df.iterrows()
            if row.get("estatus", "").upper() in ["EN_CURSO", "RECURSANDO"]
        )
        cursadas_set = aprobadas_set | en_curso_set

        # Estimar ciclo_anual actual mirando qué ciclos anuales tiene el estudiante activos
        # Usamos el mapa curricular para obtener el ciclo_anual de las materias cursadas
        ciclo_anual_actual = 1
        for _, row in historial_df.iterrows():
            clave = str(row.get("clave", "")).strip().upper()
            if clave.startswith("PID"):
                continue
            if row.get("estatus", "").upper() in ("APROBADA", "EN_CURSO", "RECURSANDO"):
                info = self.mapa_curricular.get(clave, {})
                ca = info.get("ciclo_anual", 0)
                if isinstance(ca, int) and ca > ciclo_anual_actual:
                    ciclo_anual_actual = ca

        pid0201_ok = "PID0201" in cursadas_set
        pid0302_ok = "PID0302" in cursadas_set

        # PID0201 debía completarse en ciclo_anual 2 (sems 3-4)
        if not pid0201_ok:
            if ciclo_anual_actual >= 4:
                alertas.append({
                    "tipo": "ATRASO_PRÁCTICAS_I",
                    "descripcion": "El estudiante va en el ciclo anual 4 (semestres 7-8) y aún no ha cursado Prácticas Profesionales I (PID0201), que debió completarse en el ciclo anual 2. Atraso de 2 o más años.",
                    "severidad": "CRITICA"
                })
            elif ciclo_anual_actual >= 3:
                alertas.append({
                    "tipo": "ATRASO_PRÁCTICAS_I",
                    "descripcion": "El estudiante va en el ciclo anual 3 (semestres 5-6) y aún no ha cursado Prácticas Profesionales I (PID0201), que debió completarse en el ciclo anual 2. Atraso de 1 año.",
                    "severidad": "ADVERTENCIA"
                })

        # PID0302 debía completarse en ciclo_anual 3 (sems 5-6)
        if not pid0302_ok:
            if ciclo_anual_actual >= 4:
                alertas.append({
                    "tipo": "ATRASO_PRÁCTICAS_II",
                    "descripcion": "El estudiante va en el ciclo anual 4 (semestres 7-8) y aún no ha cursado Prácticas Profesionales II (PID0302), que debió completarse en el ciclo anual 3. Atraso de 1 año.",
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
