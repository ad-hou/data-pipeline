-- Referentiel des communes presentes dans les transactions.
select
    code_commune,
    max(nom_commune)      as nom_commune,
    max(code_departement) as code_departement
from {{ ref('stg_transactions') }}
where code_commune is not null
group by code_commune
