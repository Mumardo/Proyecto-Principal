from typing import Iterable, Tuple

from .prenda import Prenda


class CatalogoPrendas:
    """Consulta referencias por marca y categoría."""

    def __init__(self, prendas: Iterable[Prenda]) -> None:
        self.prendas = tuple(prendas)
        if not self.prendas:
            raise ValueError("El catálogo debe contener al menos una prenda.")

    def marcas(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys(prenda.marca for prenda in self.prendas))

    def categorias(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys(prenda.categoria for prenda in self.prendas))

    def filtrar(self, marca: str = "", categoria: str = "") -> Tuple[Prenda, ...]:
        return tuple(
            prenda
            for prenda in self.prendas
            if (not marca or prenda.marca == marca)
            and (not categoria or prenda.categoria == categoria)
        )
