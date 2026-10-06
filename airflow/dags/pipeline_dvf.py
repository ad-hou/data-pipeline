"""Pipeline DVF : ingestion -> fraicheur -> dbt build (modeles + tests) -> documentation.

- ingest : telecharge les csv.gz et les charge dans raw.dvf (idempotent, voir ingestion/)
- dbt_freshness : la source raw.dvf a-t-elle ete chargee recemment ?
- dbt_build : staging, marts ET tests dans l'ordre des dependances ; un test qui echoue fait
  echouer la tache et saute les modeles en aval (les marts ne sont pas mis a jour avec des
  donnees douteuses)
- dbt_docs : genere la documentation et le graphe de dependances
Parametres (Trigger DAG w/ config) : years, deps.
"""
from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Param

DBT = "cd /opt/airflow/dbt_project && /home/airflow/dbt_venv/bin/dbt"
DBT_ENV = {"DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}

with DAG(
    dag_id="pipeline_dvf",
    description="DVF : ingestion, dbt (staging, marts, tests), documentation",
    schedule="0 6 * * 1",              # chaque lundi a 6 h (UTC)
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=1)},
    params={
        "years": Param("2022 2023 2024 2025", type="string",
                       description="Annees a charger, separees par des espaces"),
        "deps": Param("60 75 93", type="string",
                      description="Departements a charger, separes par des espaces"),
    },
    tags=["dvf", "dbt"],
) as dag:
    ingest = BashOperator(
        task_id="ingest",
        bash_command=("python /opt/airflow/ingestion/download_and_load.py "
                      "--years {{ params.years }} --deps {{ params.deps }}"),
    )
    dbt_freshness = BashOperator(
        task_id="dbt_freshness", bash_command=f"{DBT} source freshness --profiles-dir .",
        env=DBT_ENV, append_env=True)
    dbt_build = BashOperator(
        task_id="dbt_build", bash_command=f"{DBT} build --profiles-dir .",
        env=DBT_ENV, append_env=True, retries=0)   # un test casse n'est pas un incident reseau
    dbt_docs = BashOperator(
        task_id="dbt_docs", bash_command=f"{DBT} docs generate --profiles-dir .",
        env=DBT_ENV, append_env=True)

    ingest >> dbt_freshness >> dbt_build >> dbt_docs
