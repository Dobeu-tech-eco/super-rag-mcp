"""TurboVec IdMapIndex wrapper with stable string IDs and per-doc deletes.

Public surface (unchanged regardless of turbovec internals):
  VectorIndex(dim, path)
  VectorIndex.load(dim, path) -> VectorIndex
  .add_batch(ids: list[str], vectors: np.ndarray) -> None
  .delete_by_doc_id(source, account, doc_id) -> None
  .search(query: np.ndarray, k: int) -> list[tuple[str, float]]
  .save() -> None

Adaptation notes (turbovec's real API vs plan assumptions):
  - add_with_ids(vectors, ids)  instead of add(ids, vectors)
    ids must be uint64 ndarray (not strings); we maintain our own
    str <-> uint64 mapping in _str_to_int / _int_to_str.
  - search(queries, k) returns (scores, ids) as 2D arrays (not ids, scores).
    queries must be a 2-D C-contiguous float32 array.
  - remove(uint64_id)           instead of batch remove(ids=[...])
  - write(path)                 instead of save(path)
  - prepare() must be called after every add_with_ids / remove before search.
  - dim must be a multiple of 8 (turbovec requirement; enforced here).
  - The string id map is persisted as a JSON sidecar at <path>.idmap.json
    so that save/load round-trips preserve str IDs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import turbovec

if TYPE_CHECKING:
    pass


class VectorIndex:
    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, dim: int, path: Path) -> None:
        if dim % 8 != 0:
            raise ValueError(f"dim must be a multiple of 8, got {dim}")
        self.dim = dim
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self._idx = turbovec.IdMapIndex(dim=dim)
        # str <-> uint64 maps; counter increments monotonically (never reused)
        self._str_to_int: dict[str, int] = {}   # str id -> uint64 int key
        self._int_to_str: dict[int, str] = {}   # uint64 int key -> str id
        self._counter: int = 0
        self._dirty: bool = False  # tracks whether prepare() is needed

    # ------------------------------------------------------------------
    # Alternative constructor
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, dim: int, path: Path) -> "VectorIndex":
        """Load a previously saved VectorIndex from *path* (.tvim + sidecar)."""
        inst = cls(dim, path)
        tvim_path = inst.path
        sidecar = inst._sidecar_path()
        if tvim_path.exists() and sidecar.exists():
            inst._idx = turbovec.IdMapIndex.load(str(tvim_path))
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            inst._str_to_int = data["str_to_int"]
            inst._int_to_str = {int(k): v for k, v in data["int_to_str"].items()}
            inst._counter = data["counter"]
            inst._dirty = False
        return inst

    # ------------------------------------------------------------------
    # Public mutators
    # ------------------------------------------------------------------

    def add_batch(self, ids: list[str], vectors: np.ndarray) -> None:
        """Add *vectors* (shape [n, dim]) under the given string *ids*."""
        if vectors.ndim != 2 or vectors.shape[1] != self.dim:
            raise ValueError(
                f"Expected vectors shape (n, {self.dim}), got {vectors.shape}"
            )
        if vectors.dtype != np.float32:
            vectors = vectors.astype(np.float32)
        vectors = np.ascontiguousarray(vectors)

        # Assign a unique uint64 key to each new string id
        uint_keys: list[int] = []
        for sid in ids:
            if sid in self._str_to_int:
                raise ValueError(f"ID already present in index: {sid!r}")
            key = self._counter
            self._counter += 1
            self._str_to_int[sid] = key
            self._int_to_str[key] = sid
            uint_keys.append(key)

        uint_ids = np.array(uint_keys, dtype=np.uint64)
        self._idx.add_with_ids(vectors=vectors, ids=uint_ids)
        self._idx.prepare()
        self._dirty = False

    def delete_by_doc_id(self, source: str, account: str, doc_id: str) -> None:
        """Remove every chunk whose string id starts with ``source:account:doc_id:``."""
        prefix = f"{source}:{account}:{doc_id}:"
        to_delete = [sid for sid in self._str_to_int if sid.startswith(prefix)]
        if not to_delete:
            return
        for sid in to_delete:
            key = self._str_to_int.pop(sid)
            del self._int_to_str[key]
            self._idx.remove(np.uint64(key))
        self._idx.prepare()
        self._dirty = False

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def search(self, query: np.ndarray, k: int = 10) -> list[tuple[str, float]]:
        """Return up to *k* ``(str_id, score)`` pairs, highest score first."""
        if query.dtype != np.float32:
            query = query.astype(np.float32)
        # turbovec.search expects a 2-D array of shape (nq, dim)
        if query.ndim == 1:
            query = query[np.newaxis, :]
        query = np.ascontiguousarray(query)

        if len(self._str_to_int) == 0:
            return []

        effective_k = min(k, len(self._str_to_int))
        scores, uint_ids = self._idx.search(queries=query, k=effective_k)
        # scores and uint_ids are 2-D (nq, effective_k); take first query row
        row_scores: np.ndarray = scores[0]
        row_ids: np.ndarray = uint_ids[0]
        return [
            (self._int_to_str[int(uid)], float(sc))
            for uid, sc in zip(row_ids, row_scores)
            if int(uid) in self._int_to_str
        ]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist the turbovec index (.tvim) and the string id sidecar (.tvim.idmap.json)."""
        self._idx.write(str(self.path))
        sidecar_data = {
            "str_to_int": self._str_to_int,
            "int_to_str": {str(k): v for k, v in self._int_to_str.items()},
            "counter": self._counter,
        }
        self._sidecar_path().write_text(
            json.dumps(sidecar_data, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sidecar_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".idmap.json")
