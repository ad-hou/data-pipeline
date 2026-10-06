{# Volume : le nombre de ventes d'un departement pour une annee ne doit pas s'effondrer
   par rapport a la mediane des autres annees du meme departement (ratio dans dbt_project.yml). #}
with par_dept_annee as (
    select code_departement, annee, count(*) as nb
    from {{ ref('fct_ventes') }}
    group by 1, 2
),
reference as (
    select code_departement,
           percentile_cont(0.5) within group (order by nb) as mediane
    from par_dept_annee
    group by 1
)
select p.code_departement, p.annee, p.nb, r.mediane
from par_dept_annee p
join reference r using (code_departement)
where p.nb < r.mediane * {{ var('volume_ratio_min') }}
