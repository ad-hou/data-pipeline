"""Ingestion DVF : telechargement (csv.gz data.gouv.fr) puis chargement brut dans raw.dvf.

Principes :
- raw = donnees telles que publiees : toutes les colonnes en texte, aucune transformation
  (le typage et le nettoyage se font dans dbt, couche staging) ;
- idempotent : relancer un fichier remplace ses lignes (colonne _source_file), pas de doublons ;
- l'en-tete du fichier fait foi : si son schema change, le chargement echoue au lieu de deformer.

Usage (dans le conteneur Airflow) :
  python /opt/airflow/ingestion/download_and_load.py --years 2024 --deps 93
"""
import argparse
import gzip
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

import psycopg2
from psycopg2 import sql

URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/{year}/departements/{dep}.csv.gz"
DATA_DIR = Path(os.environ.get("DVF_DATA_DIR", "/opt/airflow/data"))
IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def connect():
    return psycopg2.connect(host=os.environ["WH_HOST"], port=os.environ["WH_PORT"],
                            dbname=os.environ["WH_DB"], user=os.environ["WH_USER"],
                            password=os.environ["WH_PASSWORD"], client_encoding="utf8")


def download(year: int, dep: str, data_dir: Path = DATA_DIR) -> Path:
    """Telecharge dvf_<dep>_<annee>.csv.gz s'il n'est pas deja present. -> chemin local."""
    data_dir.mkdir(parents=True, exist_ok=True)
    dest = data_dir / f"dvf_{dep}_{year}.csv.gz"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    url = URL.format(year=year, dep=dep)
    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(url, headers={"User-Agent": "dvf-pipeline/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Telechargement impossible : {url} ({e})") from e
    tmp.rename(dest)
    return dest


def read_header(path: Path) -> list[str]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        cols = f.readline().strip().split(",")
    bad = [c for c in cols if not IDENT.match(c)]
    if bad:
        raise ValueError(f"Noms de colonnes inattendus dans {path.name} : {bad}")
    return cols


def ensure_table(cur, cols: list[str]) -> None:
    """Cree raw.dvf (colonnes du fichier en texte + metadonnees) ; echoue si le schema differe."""
    cur.execute("create schema if not exists raw")
    cur.execute("select column_name from information_schema.columns "
                "where table_schema='raw' and table_name='dvf' order by ordinal_position")
    existing = [r[0] for r in cur.fetchall()]
    if not existing:
        defs = [sql.SQL("{} text").format(sql.Identifier(c)) for c in cols]
        defs += [sql.SQL("_source_file text not null"),
                 sql.SQL("_loaded_at timestamptz not null default now()")]
        cur.execute(sql.SQL("create table raw.dvf ({})").format(sql.SQL(", ").join(defs)))
        cur.execute("create index on raw.dvf (_source_file)")
        return
    expected = existing[:-2]
    if expected != cols:
        raise ValueError("Le schema du fichier differe de raw.dvf : "
                         f"manquantes={sorted(set(expected) - set(cols))} "
                         f"nouvelles={sorted(set(cols) - set(expected))}")


def load_file(conn, path: Path) -> int:
    """Remplace les lignes de ce fichier dans raw.dvf. -> nombre de lignes chargees."""
    cols = read_header(path)
    with conn, conn.cursor() as cur:
        ensure_table(cur, cols)
        col_list = sql.SQL(", ").join(sql.Identifier(c) for c in cols)
        defs = sql.SQL(", ").join(sql.SQL("{} text").format(sql.Identifier(c)) for c in cols)
        cur.execute(sql.SQL("create temp table _stage ({}) on commit drop").format(defs))
        with gzip.open(path, "rt", encoding="utf-8") as f:
            cur.copy_expert(sql.SQL("copy _stage ({}) from stdin with (format csv, header true)")
                            .format(col_list).as_string(cur), f)
        cur.execute("delete from raw.dvf where _source_file = %s", (path.name,))
        cur.execute(sql.SQL("insert into raw.dvf ({}, _source_file) select {}, %s from _stage")
                    .format(col_list, col_list), (path.name,))
        return cur.rowcount


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="+", type=int, default=[2022, 2023, 2024, 2025])
    ap.add_argument("--deps", nargs="+", default=["60", "75", "93"])
    a = ap.parse_args(argv)

    t0, total = time.perf_counter(), 0
    conn = connect()
    try:
        for dep in a.deps:
            for year in a.years:
                t1 = time.perf_counter()
                path = download(year, dep)
                n = load_file(conn, path)
                total += n
                print(f"{path.name}: {n} lignes ({time.perf_counter() - t1:.1f} s)", flush=True)
    finally:
        conn.close()
    print(f"Total : {total} lignes en {time.perf_counter() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
