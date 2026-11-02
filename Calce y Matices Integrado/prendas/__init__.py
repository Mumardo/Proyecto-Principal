"""Modelos, catálogo y fuentes de datos de prendas."""

from .catalogo import CatalogoPrendas
from .prenda import Prenda
from .repositorio_excel import RepositorioExcelPrendas
from .producto_vestua import ProductoVestua
from .repositorio_vestua import RepositorioVestua

__all__ = [
    "CatalogoPrendas",
    "Prenda",
    "ProductoVestua",
    "RepositorioExcelPrendas",
    "RepositorioVestua",
]
