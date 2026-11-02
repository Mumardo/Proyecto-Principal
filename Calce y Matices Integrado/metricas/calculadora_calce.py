from math import inf
from typing import Dict, Optional, Tuple

from medidas.perfil_medidas import PerfilMedidas
from prendas.prenda import Prenda

from .resultado_calce import (
    DiagnosticoCalce,
    MedidaComparada,
    ResultadoCalce,
)


ETIQUETAS_MEDIDAS = {
    "cintura": "Cintura",
    "cadera": "Cadera",
}
PREFERENCIAS_CALCE = {
    "adjusted": (0, 4, 2),
    "regular": (2, 8, 5),
    "loose": (6, 14, 10),
}


class CalculadoraCalce:
    """Calcula holguras, diagnóstico y orden de coincidencia de prendas."""

    def calcular(
        self,
        prenda: Prenda,
        perfil: PerfilMedidas,
        preferencia: str = "regular",
    ) -> ResultadoCalce:
        claves = ("cintura", "cadera")
        medidas_prenda = {
            "busto": prenda.busto,
            "cintura": prenda.cintura,
            "cadera": prenda.cadera,
        }
        medidas_cuerpo = perfil.como_diccionario()
        medidas = tuple(
            MedidaComparada(
                nombre=ETIQUETAS_MEDIDAS[clave],
                prenda=medidas_prenda[clave],
                cuerpo=medidas_cuerpo[clave],
                holgura=(
                    medidas_prenda[clave] - medidas_cuerpo[clave]
                    if medidas_cuerpo[clave] is not None
                    else None
                ),
            )
            for clave in claves
        )
        ingresadas = tuple(medida for medida in medidas if medida.holgura is not None)
        minimo, maximo, objetivo = PREFERENCIAS_CALCE.get(
            preferencia, PREFERENCIAS_CALCE["regular"]
        )
        minimo_efectivo = max(minimo, -1 if prenda.elasticidad >= 8 else 0)
        desviaciones = tuple(
            max(minimo_efectivo - medida.holgura, medida.holgura - maximo, 0)
            for medida in ingresadas
        )
        desviacion_media = sum(desviaciones) / len(ingresadas) if ingresadas else inf
        distancia_objetivo = (
            sum(abs(medida.holgura - objetivo) for medida in ingresadas)
            / len(ingresadas)
            if ingresadas
            else 0
        )
        puntuacion = (
            desviacion_media * 2 + distancia_objetivo * 0.2
            if ingresadas
            else inf
        )
        diagnostico = self._diagnosticar(
            ingresadas,
            len(claves),
            minimo_efectivo,
            maximo,
            prenda.tolerancia,
        )
        return ResultadoCalce(medidas, puntuacion, diagnostico, None)

    @staticmethod
    def _diagnosticar(
        medidas: Tuple[MedidaComparada, ...],
        cantidad_requerida: int,
        holgura_minima: float,
        holgura_maxima: float,
        tolerancia: float,
    ) -> DiagnosticoCalce:
        if not medidas:
            return DiagnosticoCalce("Ingresa tus medidas", "")
        if len(medidas) < cantidad_requerida:
            return DiagnosticoCalce("Revisión parcial", "partial")

        holguras = tuple(medida.holgura for medida in medidas)
        if any(valor < holgura_minima - tolerancia for valor in holguras):
            return DiagnosticoCalce("Podría quedar estrecha", "tight")
        if any(valor > holgura_maxima + tolerancia for valor in holguras):
            return DiagnosticoCalce("Podría quedar holgada", "loose")
        if any(valor < holgura_minima for valor in holguras):
            return DiagnosticoCalce("Ajuste al límite", "partial")
        if any(valor > holgura_maxima for valor in holguras):
            return DiagnosticoCalce("Holgura al límite", "partial")
        return DiagnosticoCalce("Podría quedarte bien", "good")
