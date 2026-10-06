{#
  Une ligne par vente de logement comparable.
  Regles (chacune documentee dans le README) :
  - nature_mutation = 'Vente' (hors VEFA, echanges, adjudications, expropriations)
  - prix > 0
  - exactement un logement (Maison ou Appartement) dans la mutation, aucun local commercial :
    sinon le prix total ne peut pas etre rapporte a une surface
  - surface batie > 0
  - prix au m2 dans la plage plausible (variables prix_m2_min / prix_m2_max)
  La valeur fonciere est repetee sur chaque ligne d'une mutation : on ne la somme jamais.
#}
with ventes as (
    select * from {{ ref('stg_transactions') }}
    where nature_mutation = 'Vente'
      and valeur_fonciere > 0
),

par_mutation as (
    select
        id_mutation,
        count(*) filter (where type_local in ('Maison', 'Appartement'))             as n_logements,
        count(*) filter (where type_local like 'Local industriel%')                 as n_commerces
    from ventes
    group by id_mutation
),

candidats as (
    select
        v.id_mutation,
        v.date_mutation,
        extract(year from v.date_mutation)::int   as annee,
        extract(month from v.date_mutation)::int  as mois,
        v.code_departement,
        v.code_commune,
        v.type_local,
        v.surface_reelle_bati,
        v.nombre_pieces_principales,
        v.valeur_fonciere,
        round(v.valeur_fonciere / v.surface_reelle_bati, 2) as prix_m2,
        v.longitude,
        v.latitude
    from ventes v
    join par_mutation m using (id_mutation)
    where v.type_local in ('Maison', 'Appartement')
      and v.surface_reelle_bati > 0
      and m.n_logements = 1
      and m.n_commerces = 0
)

select *
from candidats
where prix_m2 between {{ var('prix_m2_min') }} and {{ var('prix_m2_max') }}
