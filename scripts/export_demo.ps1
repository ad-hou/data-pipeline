# Exporte les donnees lues par le dashboard vers des fichiers legers (mode demo en ligne).
# Usage (depuis la racine du projet, pipeline lance) :
#   powershell -ExecutionPolicy Bypass -File scripts\export_demo.ps1
# Resultat : dashboard\demo_data\mart.csv.gz, ventes.csv.gz, meta.csv.gz

$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$out = Join-Path $root "dashboard\demo_data"
New-Item -ItemType Directory -Force -Path $out | Out-Null

$exports = [ordered]@{
  "mart"   = "select * from marts.mart_prix_commune_annee"
  "ventes" = "select annee, type_local, code_departement, round(longitude::numeric, 5) as longitude, round(latitude::numeric, 5) as latitude, round(prix_m2::numeric, 1) as prix_m2, surface_reelle_bati as surface, date_mutation from marts.fct_ventes where longitude is not null and latitude is not null"
  "meta"   = "select (select max(_loaded_at) from raw.dvf) as loaded_at, (select count(*) from raw.dvf) as brut, (select count(*) from staging.stg_transactions) as propre, (select count(*) from marts.fct_ventes) as ventes"
}

foreach ($name in $exports.Keys) {
  $sql = $exports[$name]
  Write-Host "Export $name ..."
  $cmd = "\copy ($sql) to program 'gzip > /tmp/$name.csv.gz' csv header"
  docker compose exec -T warehouse psql -U dvf -d dvf -c $cmd
  if ($LASTEXITCODE -ne 0) { Write-Host "Echec de l'export $name"; exit 1 }
  docker compose cp "warehouse:/tmp/$name.csv.gz" (Join-Path $out "$name.csv.gz")
  if ($LASTEXITCODE -ne 0) { Write-Host "Echec de la copie $name"; exit 1 }
}

Get-ChildItem $out | ForEach-Object { "{0,-14} {1,10:N0} octets" -f $_.Name, $_.Length }
Write-Host "Termine. Ajoute dashboard\demo_data au depot : git add dashboard\demo_data"
