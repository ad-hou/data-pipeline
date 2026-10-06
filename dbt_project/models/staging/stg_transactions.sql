{{ config(indexes=[{'columns': ['id_mutation']}]) }}

{#
  Couche staging : typage, renommage, suppression des lignes inutilisables.
  - lignes sans id_mutation ou sans date : rejetees
  - doublons exacts (toutes les colonnes brutes identiques, metadonnees de chargement exclues) :
    supprimes ; deux lignes qui different par une colonne, meme non conservee ici, restent distinctes
  Aucune regle metier ici : le choix des ventes comparables se fait dans fct_ventes.
#}
with src as (
    select * from {{ source('raw', 'dvf') }}
),

dedupliquees as (
    select distinct on (row_key) *
    from (
        select *,
               md5((to_jsonb(src) - '_loaded_at' - '_source_file')::text) as row_key
        from src
    ) k
    order by row_key, _source_file
),

typed as (
    select
        id_mutation,
        nullif(date_mutation, '')::date                     as date_mutation,
        nullif(numero_disposition, '')                      as numero_disposition,
        nullif(nature_mutation, '')                         as nature_mutation,
        nullif(valeur_fonciere, '')::numeric(14, 2)         as valeur_fonciere,
        nullif(adresse_numero, '')                          as adresse_numero,
        nullif(adresse_nom_voie, '')                        as adresse_nom_voie,
        nullif(code_postal, '')                             as code_postal,
        nullif(code_commune, '')                            as code_commune,
        nullif(nom_commune, '')                             as nom_commune,
        nullif(code_departement, '')                        as code_departement,
        nullif(id_parcelle, '')                             as id_parcelle,
        nullif(lot1_numero, '')                             as lot1_numero,
        nullif(nombre_lots, '')::int                        as nombre_lots,
        nullif(type_local, '')                              as type_local,
        nullif(surface_reelle_bati, '')::numeric(12, 2)     as surface_reelle_bati,
        nullif(nombre_pieces_principales, '')::int          as nombre_pieces_principales,
        nullif(nature_culture, '')                          as nature_culture,
        nullif(surface_terrain, '')::numeric(14, 2)         as surface_terrain,
        nullif(longitude, '')::double precision             as longitude,
        nullif(latitude, '')::double precision              as latitude,
        _source_file
    from dedupliquees
)

select *
from typed
where id_mutation is not null
  and date_mutation is not null
