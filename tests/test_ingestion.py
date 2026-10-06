"""Tests unitaires de l'ingestion (sans base ni reseau)."""
import gzip
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingestion"))
import download_and_load as dl  # noqa: E402


def _gz(path, text):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(text)
    return path


def test_read_header(tmp_path):
    p = _gz(tmp_path / "a.csv.gz", "id_mutation,valeur_fonciere\n1,100\n")
    assert dl.read_header(p) == ["id_mutation", "valeur_fonciere"]


def test_read_header_rejects_unsafe_column_names(tmp_path):
    p = _gz(tmp_path / "a.csv.gz", 'id_mutation,"x; drop table raw.dvf"\n1,2\n')
    with pytest.raises(ValueError):
        dl.read_header(p)


def test_download_reuses_existing_file(tmp_path):
    existing = _gz(tmp_path / "dvf_93_2024.csv.gz", "id_mutation\n1\n")
    assert dl.download(2024, "93", data_dir=tmp_path) == existing


def test_download_failure_leaves_no_partial_file(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError("reseau coupe")
    monkeypatch.setattr(dl.urllib.request, "urlopen", boom)
    with pytest.raises(RuntimeError):
        dl.download(2024, "93", data_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []
