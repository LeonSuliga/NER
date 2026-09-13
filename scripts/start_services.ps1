w# PowerShell helper to start Docker Compose services and apply schema.sql
# Usage: .\scripts\start_services.ps1

$composeFile = Join-Path $PSScriptRoot "..\docker-compose.yml"
$schemaFile = Join-Path $PSScriptRoot "..\schema.sql"

Write-Host "Checking Docker availability..."
try {
    docker --version | Out-Null
} catch {
    Write-Error "Docker CLI not found. Install Docker Desktop or enable WSL with Docker."; exit 1
}

Write-Host "Starting containers (docker compose up -d)..."
docker compose -f $composeFile up -d

Write-Host "Waiting for Postgres to become ready..."
$ready = $false
for ($i=0; $i -lt 30; $i++) {
    $hc = docker exec legal_postgres pg_isready -U postgres -d legaldb 2>&1
    if ($hc -and $hc -match 'accepting connections') { $ready = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $ready) { Write-Error "Postgres did not become ready in time."; exit 2 }

Write-Host "Applying schema.sql to Postgres container..."
Get-Content $schemaFile -Raw | docker exec -i legal_postgres psql -U postgres -d legaldb

Write-Host "Services started and schema applied. Postgres: postgres:postgres@localhost:5432, DB=legaldb. Neo4j: bolt://localhost:7687 (neo4j/neo4jpass)"
