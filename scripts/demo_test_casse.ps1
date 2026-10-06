# Demonstration : un test dbt casse fait echouer le pipeline et protege le mart.
# Usage (depuis la racine du projet) :
#   powershell -ExecutionPolicy Bypass -File scripts\demo_test_casse.ps1
# Resultat enregistre dans docs\demo_test_casse.log

$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
New-Item -ItemType Directory -Force -Path docs | Out-Null
$log = Join-Path $root "docs\demo_test_casse.log"
"" | Out-File -Encoding ascii $log

function Say($t) { Write-Host $t; $t | Out-File -Encoding ascii -Append $log }
function Sql($q) { (docker compose exec -T warehouse psql -U dvf -d dvf -t -A -c $q | Out-String).Trim() }
$dbt = "cd /opt/airflow/dbt_project && /home/airflow/dbt_venv/bin/dbt --no-use-colors build --profiles-dir ."
$qMart = "select coalesce(sum(nb_ventes),0) from marts.mart_prix_commune_annee where code_departement='93' and annee=2025"
$qFct  = "select count(*) from marts.fct_ventes where code_departement='93' and annee=2025"
$qRaw  = "select count(*) from raw.dvf where _source_file='dvf_93_2025.csv.gz'"

Say "=== Demonstration du test casse ($(Get-Date -Format 'yyyy-MM-dd HH:mm')) ==="
Say ""
Say "[0/5] Remise a zero : rechargement de dvf_93_2025 puis dbt build (base de depart saine)"
docker compose exec -T airflow-scheduler python /opt/airflow/ingestion/download_and_load.py --years 2025 --deps 93 2>&1 | ForEach-Object { Say ("  " + $_) }
$base = docker compose exec -T airflow-scheduler bash -c $dbt 2>&1 | Out-String
$base -split "`n" | Where-Object { $_ -match "Done\." } | ForEach-Object { Say ("  " + $_.Trim()) }
if ($base -notmatch "ERROR=0") { Say "  La base de depart n'est pas saine : arret."; exit 1 }

Say ""
Say "[1/5] Etat avant"
$rawAvant = Sql $qRaw; $fctAvant = Sql $qFct; $martAvant = Sql $qMart
Say "  raw.dvf (93, 2025)        : $rawAvant lignes"
Say "  fct_ventes (93, 2025)     : $fctAvant ventes"
Say "  mart (93, 2025) nb_ventes : $martAvant"

Say ""
Say "[2/5] Simulation d'un fichier tronque : suppression de 80 % des lignes de dvf_93_2025"
Sql "delete from raw.dvf where _source_file='dvf_93_2025.csv.gz' and random() < 0.8" | Out-Null
Say "  raw.dvf (93, 2025)        : $(Sql $qRaw) lignes"

Say ""
Say "[3/5] dbt build (doit echouer)"
$out = docker compose exec -T airflow-scheduler bash -c $dbt 2>&1 | Out-String
$code = $LASTEXITCODE
$out -split "`n" | Where-Object { $_ -match "FAIL|ERROR|SKIP|Done\.|Completed" } | ForEach-Object { Say ("  " + $_.Trim()) }
Say "  code de sortie dbt : $code (0 = succes, autre = echec)"

Say ""
Say "[4/5] Etat apres l'echec"
$fctApres = Sql $qFct; $martApres = Sql $qMart
Say "  fct_ventes (93, 2025)     : $fctApres ventes (reconstruite avant son test)"
Say "  mart (93, 2025) nb_ventes : $martApres (avant : $martAvant)"
if ($martApres -eq $martAvant) { Say "  -> le mart n'a PAS ete mis a jour : il est protege." }
else { Say "  -> ATTENTION : le mart a change." }

Say ""
Say "[5/5] Meme echec cote Airflow : relance de la tache dbt_build"
docker compose exec -T airflow-scheduler airflow tasks clear pipeline_dvf -t dbt_build -s 2026-10-06 -e 2026-10-07 -d -y 2>&1 | Out-Null
Start-Sleep -Seconds 45
$states = docker compose exec -T airflow-db psql -U airflow -d airflow -t -A -F " : " -c "select task_id, state from task_instance where dag_id='pipeline_dvf' and run_id like 'manual%' order by start_date" | Out-String
$states -split "`n" | Where-Object { $_.Trim() } | ForEach-Object { Say ("  " + $_.Trim()) }
Write-Host ""
Write-Host ">>> Ouvre http://localhost:8080 -> pipeline_dvf -> dernier run manuel -> onglet Graph : dbt_build doit etre ROUGE."
Write-Host ">>> Fais ta capture, puis reviens ici."
Read-Host "Appuie sur Entree pour reparer les donnees"

Say ""
Say "=== Reparation : rechargement du fichier puis dbt build ==="
docker compose exec -T airflow-scheduler python /opt/airflow/ingestion/download_and_load.py --years 2025 --deps 93 2>&1 | ForEach-Object { Say ("  " + $_) }
$out2 = docker compose exec -T airflow-scheduler bash -c $dbt 2>&1 | Out-String
$out2 -split "`n" | Where-Object { $_ -match "Done\.|Completed" } | ForEach-Object { Say ("  " + $_.Trim()) }
Say "  mart (93, 2025) nb_ventes : $(Sql $qMart)"
Say ""
Say "Termine. Resultat dans docs\demo_test_casse.log - envoie-le moi."
