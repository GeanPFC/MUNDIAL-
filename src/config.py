"""Carga central de configuracion reproducible.

Lee `config.yaml` desde la raiz del proyecto y expone un objeto de acceso comodo.
Se mantiene deliberadamente simple: sin dependencias mas alla de PyYAML.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


class Config:
    """Acceso por puntos a la configuracion, con resolucion de rutas relativas."""

    def __init__(self, data: dict[str, Any], root: Path = PROJECT_ROOT) -> None:
        self._data = data
        self._root = root

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
        with open(config_path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        return cls(data, root=config_path.resolve().parent)

    def get(self, *keys: str, default: Any = None) -> Any:
        node: Any = self._data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def path(self, *keys: str) -> Path:
        """Resuelve un valor de config como ruta absoluta relativa a la raiz."""
        value = self.get(*keys)
        if value is None:
            raise KeyError(f"Config path not found for keys: {keys}")
        candidate = Path(value)
        return candidate if candidate.is_absolute() else (self._root / candidate)

    @property
    def root(self) -> Path:
        return self._root

    @property
    def raw(self) -> dict[str, Any]:
        return self._data


def load_config(path: str | Path | None = None) -> Config:
    return Config.load(path)
