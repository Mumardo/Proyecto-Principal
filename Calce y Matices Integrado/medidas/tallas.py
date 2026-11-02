import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from openpyxl import load_workbook

from .perfil_medidas import PerfilMedidas


RANGE_PATTERN = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*[-–]\s*(\d+(?:[.,]\d+)?)\s*$")
SIZE_COLUMNS = {
    "talla": "etiqueta",
    "tallaalfa": "etiqueta",
    "tallanumericaescl": "europea",
    "tallaeu": "europea",
    "tallaeeuu": "estadounidense",
    "pechobustocm": "busto",
    "cinturacm": "cintura",
    "caderacm": "cadera",
}
BODY_MEASUREMENTS = ("busto", "cintura", "cadera")


def _normalize_header(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    without_accents = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]", "", without_accents.lower())


@dataclass(frozen=True)
class RangoTalla:
    etiqueta: str
    europea: Optional[str]
    estadounidense: Optional[str]
    busto: str
    cintura: str
    cadera: str

    def limites(self, medida: str) -> Tuple[float, float]:
        valor = getattr(self, medida)
        match = RANGE_PATTERN.fullmatch(valor)
        if match is None:
            raise ValueError(f"Rango inválido para {medida}: {valor}")
        minimo, maximo = (
            float(parte.replace(",", ".")) for parte in match.groups()
        )
        return minimo, maximo


class RepositorioTallasEstandar:
    """Carga rangos de talla de la tabla estándar adjunta."""

    def __init__(self, ruta_archivo: Path) -> None:
        self.ruta_archivo = Path(ruta_archivo)

    def cargar(self) -> Tuple[RangoTalla, ...]:
        if not self.ruta_archivo.is_file():
            raise FileNotFoundError(
                f"No se encontró la tabla estándar de tallas: {self.ruta_archivo}"
            )
        libro = load_workbook(
            filename=str(self.ruta_archivo), read_only=True, data_only=True
        )
        try:
            for hoja in libro.worksheets:
                for fila_numero, fila in enumerate(
                    hoja.iter_rows(values_only=True), start=1
                ):
                    posiciones = {
                        SIZE_COLUMNS[_normalize_header(valor)]: indice
                        for indice, valor in enumerate(fila)
                        if valor is not None
                        and _normalize_header(valor) in SIZE_COLUMNS
                    }
                    required_positions = {
                        "etiqueta",
                        "busto",
                        "cintura",
                        "cadera",
                    }
                    if required_positions.issubset(posiciones):
                        if "europea" not in posiciones and "estadounidense" not in posiciones:
                            continue
                        tallas = self._leer_tallas(hoja, fila_numero + 1, posiciones)
                        if tallas:
                            return tallas
            raise ValueError(
                "La tabla estándar no contiene encabezados y rangos de talla reconocibles."
            )
        finally:
            libro.close()

    @staticmethod
    def _leer_tallas(hoja, primera_fila: int, posiciones: Dict[str, int]):
        tallas = []
        for fila_numero, fila in enumerate(
            hoja.iter_rows(min_row=primera_fila, values_only=True),
            start=primera_fila,
        ):
            valores = {
                nombre: fila[indice] if indice < len(fila) else None
                for nombre, indice in posiciones.items()
            }
            if all(valor is None for valor in valores.values()):
                if tallas:
                    break
                continue
            if any(valor is None for valor in valores.values()):
                raise ValueError(
                    f"Fila {fila_numero} incompleta en {hoja.title}."
                )
            talla = RangoTalla(
                etiqueta=str(valores["etiqueta"]).strip(),
                europea=(
                    str(valores["europea"]).strip()
                    if valores.get("europea") is not None
                    else None
                ),
                estadounidense=(
                    str(valores["estadounidense"]).strip()
                    if valores.get("estadounidense") is not None
                    else None
                ),
                busto=str(valores["busto"]).strip(),
                cintura=str(valores["cintura"]).strip(),
                cadera=str(valores["cadera"]).strip(),
            )
            for medida in BODY_MEASUREMENTS:
                talla.limites(medida)
            tallas.append(talla)
        return tuple(tallas)


def recomendar_tallas(
    perfil: PerfilMedidas, tallas: Tuple[RangoTalla, ...]
) -> Tuple[Tuple[RangoTalla, ...], bool]:
    medidas = {
        medida: getattr(perfil, medida)
        for medida in BODY_MEASUREMENTS
        if getattr(perfil, medida) is not None
    }
    if not medidas:
        return (), False

    compatibles = tuple(
        talla
        for talla in tallas
        if all(
            talla.limites(medida)[0] <= valor <= talla.limites(medida)[1]
            for medida, valor in medidas.items()
        )
    )
    if compatibles:
        return compatibles, True

    def distancia_total(talla: RangoTalla) -> float:
        distancia = 0.0
        for medida, valor in medidas.items():
            minimo, maximo = talla.limites(medida)
            distancia += max(minimo - valor, valor - maximo, 0)
        return distancia

    distancia_minima = min(distancia_total(talla) for talla in tallas)
    mas_cercanas = tuple(
        talla
        for talla in tallas
        if abs(distancia_total(talla) - distancia_minima) < 1e-9
    )
    return mas_cercanas, False
