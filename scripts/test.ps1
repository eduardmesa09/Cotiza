# Equivalente a "make test" para Windows sin make. Uso: .\scripts\test.ps1
$ErrorActionPreference = "Stop"

function Run($cmd) {
    Write-Host ">> $cmd" -ForegroundColor Cyan
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) { throw "Falló: $cmd" }
}

Run "docker compose build erp-mock api"
Run "docker compose run --rm --no-deps erp-mock pytest"
Run "docker compose up -d --wait db"
Run "docker compose run --rm --no-deps api pytest"
Run "docker compose --profile test build frontend-test"
Run "docker compose --profile test run --rm frontend-test"

Write-Host "Todas las pruebas pasaron." -ForegroundColor Green
