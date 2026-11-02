import re
from pathlib import Path
from typing import List, Tuple

from openpyxl import load_workbook

from .prenda import Prenda


COLUMNAS_PRENDAS = (
    "Marca",
    "Linea/Submarca",
    "Tipo Prenda",
    "Fit",
    "Tela/Elasticidad",
    "Holgura Diseño (cm)",
    "Pais Fabricacion",
    "Tolerancia Corte (cm)",
    "Pecho (cm)",
    "Cintura (cm)",
    "Cadera (cm)",
    "Largo Total (cm)",
    "Fuente",
)
COLUMNAS_VARIABLES = ("Categoria", "Variable", "Descripcion", "Impacto")
PORCENTAJE_ELASTANO = re.compile(r"(\d+(?:[.,]\d+)?)\s*%\s*elastano", re.IGNORECASE)
NUMERO = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


class RepositorioExcelPrendas:
    """Carga y valida productos y variables desde las hojas del Excel."""

    def __init__(self, ruta_archivo: Path) -> None:
        self.ruta_archivo = Path(ruta_archivo)

    def cargar_prendas(self) -> Tuple[Prenda, ...]:
        libro = self._abrir_libro()
        try:
            hoja, posiciones = self._buscar_hoja(libro, COLUMNAS_PRENDAS)
            prendas: List[Prenda] = []
            identidades = set()
            for numero_fila, fila in enumerate(
                hoja.iter_rows(min_row=2, values_only=True), start=2
            ):
                if not any(valor is not None for valor in fila):
                    continue
                try:
                    prenda = self._crear_prenda(fila, posiciones)
                except (TypeError, ValueError) as error:
                    raise ValueError(
                        f"Fila {numero_fila} inválida en "
                        f"{self.ruta_archivo.name}: {error}"
                    ) from error
                identidad = self._identidad_prenda(prenda)
                if identidad not in identidades:
                    identidades.add(identidad)
                    prendas.append(prenda)
            if not prendas:
                raise ValueError(f"La matriz no contiene prendas: {self.ruta_archivo}")
            return tuple(prendas)
        finally:
            libro.close()

    @staticmethod
    def _identidad_prenda(prenda: Prenda) -> tuple:
        return (
            prenda.marca,
            prenda.categoria,
            prenda.calce,
            prenda.tela,
            prenda.elasticidad,
            prenda.holgura_diseno,
            prenda.origen,
            prenda.tolerancia,
            prenda.busto,
            prenda.cintura,
            prenda.cadera,
            prenda.largo,
            prenda.fuente,
        )

    def cargar_variables(self) -> Tuple[tuple, ...]:
        libro = self._abrir_libro()
        try:
            hoja, posiciones = self._buscar_hoja(libro, COLUMNAS_VARIABLES)
            variables = []
            for numero_fila, fila in enumerate(
                hoja.iter_rows(min_row=2, values_only=True), start=2
            ):
                if not any(valor is not None for valor in fila):
                    continue
                valores = tuple(fila[posiciones[columna]] for columna in COLUMNAS_VARIABLES)
                if any(valor is None or not str(valor).strip() for valor in valores):
                    raise ValueError(
                        f"Fila {numero_fila} inválida en {self.ruta_archivo.name}: "
                        "faltan datos en la hoja de variables."
                    )
                variables.append(tuple(str(valor).strip() for valor in valores))
            if not variables:
                raise ValueError("La hoja de variables no contiene datos.")
            return tuple(variables)
        finally:
            libro.close()

    def _abrir_libro(self):
        if not self.ruta_archivo.is_file():
            raise FileNotFoundError(f"No se encontró la matriz Excel: {self.ruta_archivo}")
        return load_workbook(
            filename=str(self.ruta_archivo),
            read_only=True,
            data_only=True,
        )

    @staticmethod
    def _buscar_hoja(libro, columnas_requeridas: tuple):
        for hoja in libro.worksheets:
            encabezados = tuple(celda.value for celda in hoja[1])
            if all(columna in encabezados for columna in columnas_requeridas):
                posiciones = {
                    columna: encabezados.index(columna)
                    for columna in columnas_requeridas
                }
                return hoja, posiciones
        raise ValueError(
            "El Excel no contiene una hoja con estas columnas: "
            + ", ".join(columnas_requeridas)
        )

    @staticmethod
    def _crear_prenda(fila: tuple, posiciones: dict) -> Prenda:
        def texto(columna: str) -> str:
            valor = fila[posiciones[columna]]
            if valor is None or not str(valor).strip():
                raise ValueError(f"falta el valor de «{columna}»")
            return str(valor).strip()

        def numero(columna: str) -> float:
            valor = fila[posiciones[columna]]
            if valor is None:
                raise ValueError(f"falta el valor de «{columna}»")
            try:
                resultado = float(str(valor).replace(",", "."))
            except ValueError as error:
                raise ValueError(f"«{columna}» debe ser numérico") from error
            if resultado <= 0:
                raise ValueError(f"«{columna}» debe ser mayor que cero")
            return resultado

        tela = texto("Tela/Elasticidad")
        coincidencia_elastano = PORCENTAJE_ELASTANO.search(tela)
        elasticidad = (
            float(coincidencia_elastano.group(1).replace(",", "."))
            if coincidencia_elastano
            else 0.0
        )
        texto_tolerancia = texto("Tolerancia Corte (cm)")
        coincidencia_tolerancia = NUMERO.search(texto_tolerancia)
        if coincidencia_tolerancia is None:
            raise ValueError("«Tolerancia Corte (cm)» debe incluir un número")

        return Prenda(
            marca=texto("Marca"),
            linea=texto("Linea/Submarca"),
            categoria=texto("Tipo Prenda"),
            calce=texto("Fit"),
            tela=tela,
            holgura_diseno=numero("Holgura Diseño (cm)"),
            origen=texto("Pais Fabricacion"),
            tolerancia=float(coincidencia_tolerancia.group().replace(",", ".")),
            busto=numero("Pecho (cm)"),
            cintura=numero("Cintura (cm)"),
            cadera=numero("Cadera (cm)"),
            largo=numero("Largo Total (cm)"),
            elasticidad=elasticidad,
            fuente=texto("Fuente"),
        )
