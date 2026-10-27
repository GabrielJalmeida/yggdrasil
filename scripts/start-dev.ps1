$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ApiDir = Join-Path $Root 'services\api'
$WebDir = Join-Path $Root 'apps\web'
$VenvDir = Join-Path $ApiDir '.venv'
$Python = Join-Path $VenvDir 'Scripts\python.exe'

if (-not (Test-Path (Join-Path $Root '.env'))) {
    Copy-Item (Join-Path $Root '.env.example') (Join-Path $Root '.env')
    Write-Host 'Criado .env a partir de .env.example. Revise-o antes de expor qualquer serviço.' -ForegroundColor Yellow
}
if (-not (Test-Path $VenvDir)) {
    Write-Host 'Criando ambiente virtual Python...'
    py -3.13 -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { py -m venv $VenvDir }
}
if (-not (Test-Path $Python)) { throw 'Não foi possível localizar o Python do ambiente virtual.' }

Push-Location $ApiDir
try {
    Write-Host 'Instalando dependências da API...'
    & $Python -m pip install -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependências Python.' }
    Write-Host 'Aplicando migrations...'
    & $Python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao aplicar migrations Alembic.' }
} finally { Pop-Location }

$ApiCommand = "Set-Location '$ApiDir'; & '$Python' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoExit', '-ExecutionPolicy', 'Bypass', '-Command', $ApiCommand) | Out-Null

Push-Location $WebDir
try {
    if (-not (Test-Path (Join-Path $WebDir 'node_modules'))) {
        Write-Host 'Instalando dependências do frontend...'
        if (Test-Path (Join-Path $WebDir 'package-lock.json')) { npm ci } else { npm install }
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependências do frontend.' }
    }
    Write-Host 'Iniciando frontend em http://localhost:5173 ...' -ForegroundColor Green
    Write-Host 'A API ficará em http://127.0.0.1:8000/docs, em uma janela separada.'
    npm run dev
} finally { Pop-Location }
