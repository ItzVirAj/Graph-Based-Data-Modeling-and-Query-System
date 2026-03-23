from __future__ import annotations

from pathlib import Path
from threading import Lock

from .data_loader import DEFAULT_DATA_DIR, DataLoader, NormalizedData
from .graph_builder import GraphBuilder
from .sql_engine import SqlEngine


class GraphStore:
    _instance: "GraphStore | None" = None
    _instance_lock = Lock()

    def __new__(cls) -> "GraphStore":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
                cls._instance._graph_builder = None
                cls._instance._sql_engine = None
                cls._instance._data = None
                cls._instance._data_dir = None
                cls._instance._lock = Lock()
        return cls._instance

    def initialize(self, data_dir: Path | str = DEFAULT_DATA_DIR, force: bool = False) -> GraphBuilder:
        resolved_dir = Path(data_dir)
        with self._lock:
            if (
                self._initialized
                and not force
                and self._graph_builder is not None
                and self._sql_engine is not None
                and self._data_dir == resolved_dir
            ):
                return self._graph_builder

            loader = DataLoader(resolved_dir)
            self._data = loader.load_all()
            self._graph_builder = GraphBuilder(self._data)
            self._sql_engine = SqlEngine(self._data)
            self._data_dir = resolved_dir
            self._initialized = True
            return self._graph_builder

    def reset(self) -> GraphBuilder:
        return self.initialize(force=True)

    @property
    def graph(self) -> GraphBuilder:
        if self._graph_builder is None:
            raise RuntimeError("Graph store has not been initialized.")
        return self._graph_builder

    @property
    def sql_engine(self) -> SqlEngine:
        if self._sql_engine is None:
            raise RuntimeError("Graph store has not been initialized.")
        return self._sql_engine

    @property
    def data(self) -> NormalizedData:
        if self._data is None:
            raise RuntimeError("Graph store has not been initialized.")
        return self._data


graph_store = GraphStore()
