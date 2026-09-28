"""Persistent cosine HNSW index for personal references only."""

# hnswlib publishes no typing stubs; its dynamic boundary stays in this adapter.
# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportCallIssue=false

import os
import tempfile
from hashlib import sha256
from pathlib import Path

import hnswlib
import numpy as np

from hermes_edu.domain.errors import ValidationError


class HNSWReferenceIndex:
    """Store vectors in native HNSW files, separate from SQLite business metadata."""

    def __init__(
        self,
        root: Path,
        *,
        collection: str = "references",
        m: int = 16,
        ef_construct: int = 200,
        ef_search: int = 64,
    ) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._collection = collection
        self._m = m
        self._ef_construct = ef_construct
        self._ef_search = ef_search

    def _path(self, model: str, dimension: int, index_version: str) -> Path:
        digest = sha256(
            f"{self._collection}\x1f{model}\x1f{dimension}\x1f{index_version}".encode()
        ).hexdigest()[:24]
        return self._root / f"{self._collection}-{digest}.hnsw"

    def _load(self, path: Path, dimension: int, *, additional: int = 0) -> hnswlib.Index:
        index = hnswlib.Index(space="cosine", dim=dimension)
        if path.exists():
            index.load_index(str(path), max_elements=0, allow_replace_deleted=True)
            if index.get_current_count() + additional > index.max_elements:
                index.resize_index(
                    max(index.max_elements * 2, index.get_current_count() + additional + 16)
                )
        else:
            index.init_index(
                max_elements=max(32, additional + 16),
                ef_construction=self._ef_construct,
                M=self._m,
                allow_replace_deleted=True,
            )
        index.set_ef(self._ef_search)
        return index

    @staticmethod
    def _save(index: hnswlib.Index, path: Path) -> None:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
        try:
            index.save_index(str(temporary))
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def contains(self, model: str, dimension: int, index_version: str, label: int) -> bool:
        path = self._path(model, dimension, index_version)
        if not path.exists():
            return False
        index = self._load(path, dimension)
        try:
            index.get_items([label])
        except RuntimeError:
            return False
        return True

    def contains_many(
        self, model: str, dimension: int, index_version: str, labels: tuple[int, ...]
    ) -> bool:
        if not labels:
            return True
        path = self._path(model, dimension, index_version)
        if not path.exists():
            return False
        index = self._load(path, dimension)
        return all(self._contains_loaded(index, label) for label in labels)

    def add(
        self,
        model: str,
        dimension: int,
        index_version: str,
        vectors: tuple[tuple[int, tuple[float, ...]], ...],
        *,
        replace_existing: bool = False,
    ) -> None:
        if not vectors:
            return
        if any(len(vector) != dimension for _, vector in vectors):
            raise ValidationError("Embedding dimension does not match the HNSW collection")
        path = self._path(model, dimension, index_version)
        index = self._load(path, dimension, additional=len(vectors))
        missing = [
            (label, vector)
            for label, vector in vectors
            if replace_existing or not self._contains_loaded(index, label)
        ]
        if missing:
            index.add_items(
                np.asarray([vector for _, vector in missing], dtype=np.float32),
                np.asarray([label for label, _ in missing], dtype=np.int64),
            )
            self._save(index, path)

    @staticmethod
    def _contains_loaded(index: hnswlib.Index, label: int) -> bool:
        try:
            index.get_items([label])
        except RuntimeError:
            return False
        return True

    def search(
        self,
        model: str,
        dimension: int,
        index_version: str,
        query: tuple[float, ...],
        allowed_labels: tuple[int, ...],
        top_k: int,
    ) -> tuple[tuple[int, float], ...]:
        if not allowed_labels:
            return ()
        if len(query) != dimension or top_k < 1:
            raise ValidationError("Invalid HNSW query dimension or top_k")
        path = self._path(model, dimension, index_version)
        if not path.exists():
            return ()
        index = self._load(path, dimension)
        allowed = set(allowed_labels)
        count = min(top_k, len(allowed))
        index.set_ef(max(self._ef_search, count))
        while count:
            try:
                labels, distances = index.knn_query(
                    np.asarray([query], dtype=np.float32),
                    k=count,
                    num_threads=1,
                    filter=lambda label: label in allowed,
                )
                return tuple(
                    (int(label), 1.0 - float(distance))
                    for label, distance in zip(labels[0], distances[0], strict=True)
                )
            except RuntimeError:
                count -= 1
        return ()

    def remove(
        self, model: str, dimension: int, index_version: str, labels: tuple[int, ...]
    ) -> None:
        path = self._path(model, dimension, index_version)
        if not labels or not path.exists():
            return
        index = self._load(path, dimension)
        changed = False
        for label in labels:
            if self._contains_loaded(index, label):
                index.mark_deleted(label)
                changed = True
        if changed:
            self._save(index, path)
