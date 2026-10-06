"""DAG de test : verifie qu'Airflow joint l'entrepot Postgres."""
import os
from datetime import datetime

import psycopg2
from airflow.sdk import dag, task


@dag(schedule=None, start_date=datetime(2026, 1, 1), catchup=False, tags=["test"])
def hello_warehouse():
    @task
    def ping():
        conn = psycopg2.connect(host=os.environ["WH_HOST"], port=os.environ["WH_PORT"],
                                dbname=os.environ["WH_DB"], user=os.environ["WH_USER"],
                                password=os.environ["WH_PASSWORD"])
        with conn, conn.cursor() as cur:
            cur.execute("select version()")
            print(cur.fetchone()[0])
        conn.close()

    ping()


hello_warehouse()
