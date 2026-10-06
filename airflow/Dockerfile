FROM apache/airflow:3.3.2
# dbt dans un environnement virtuel separe : evite les conflits de dependances avec Airflow
RUN python -m venv /home/airflow/dbt_venv \
    && /home/airflow/dbt_venv/bin/pip install --no-cache-dir dbt-postgres
