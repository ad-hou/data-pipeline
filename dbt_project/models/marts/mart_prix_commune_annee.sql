-- Agregats pour le tableau de bord : prix au m2 par commune, annee et type de bien.
select
    f.code_commune || '-' || f.annee || '-' || f.type_local     as cle,
    f.code_commune,
    c.nom_commune,
    f.code_departement,
    f.annee,
    f.type_local,
    count(*)                                                    as nb_ventes,
    round((percentile_cont(0.5) within group (order by f.prix_m2))::numeric, 0)           as prix_m2_median,
    round(avg(f.prix_m2), 0)                                    as prix_m2_moyen,
    round((percentile_cont(0.5) within group (order by f.surface_reelle_bati))::numeric, 0) as surface_mediane,
    count(*) >= 10                                              as echantillon_suffisant
from {{ ref('fct_ventes') }} f
join {{ ref('dim_communes') }} c using (code_commune)
group by f.code_commune, c.nom_commune, f.code_departement, f.annee, f.type_local
