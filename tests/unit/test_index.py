from pathlib import Path
import numpy as np
import pytest
from rag.index import VectorIndex


# turbovec requires dim to be a multiple of 8; we use dim=8 throughout.
DIM = 8


def _v(*values) -> np.ndarray:
    """Pad a short tuple to DIM dimensions and return a unit-normalised float32 row."""
    arr = np.zeros(DIM, dtype=np.float32)
    arr[: len(values)] = values
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr /= norm
    return arr


def test_add_and_search_roundtrip(tmp_path: Path):
    idx = VectorIndex(dim=DIM, path=tmp_path / "index.tvim")
    ids = ["localfs:default:a:00000", "localfs:default:a:00001", "localfs:default:b:00000"]
    vecs = np.stack([_v(1, 0), _v(0, 1), _v(1, 1)])  # unit-normalised
    idx.add_batch(ids, vecs)
    results = idx.search(_v(1, 0), k=2)
    assert len(results) == 2
    assert results[0][0] == "localfs:default:a:00000"  # closest to query


def test_delete_by_doc_id(tmp_path: Path):
    idx = VectorIndex(dim=DIM, path=tmp_path / "index.tvim")
    ids = ["localfs:default:a:00000", "localfs:default:a:00001", "localfs:default:b:00000"]
    vecs = np.stack([_v(1, 0), _v(0, 1), _v(0, 0, 1)])
    idx.add_batch(ids, vecs)
    idx.delete_by_doc_id("localfs", "default", "a")
    results = idx.search(_v(1, 0), k=5)
    returned_ids = [r[0] for r in results]
    assert "localfs:default:a:00000" not in returned_ids
    assert "localfs:default:a:00001" not in returned_ids
    assert "localfs:default:b:00000" in returned_ids


def test_persist_and_reload(tmp_path: Path):
    p = tmp_path / "index.tvim"
    idx = VectorIndex(dim=DIM, path=p)
    idx.add_batch(["localfs:default:a:00000"], np.stack([_v(1, 0)]))
    idx.save()
    idx2 = VectorIndex.load(dim=DIM, path=p)
    results = idx2.search(_v(1, 0), k=1)
    assert results[0][0] == "localfs:default:a:00000"
