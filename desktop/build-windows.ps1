param(
    [string]$PythonExe = "",
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

if (-not $PythonExe) {
    $Candidate = Join-Path $Root "services\api\.venv\Scripts\python.exe"
    if (Test-Path $Candidate) { $PythonExe = $Candidate }
    else {
        $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $PythonCommand) { throw "Python não encontrado apenas para o build. Use -PythonExe para apontar ao Python do projeto." }
        $PythonExe = $PythonCommand.Source
    }
}
if (-not (Test-Path $PythonExe)) { throw "Python não encontrado: $PythonExe" }
$Web = Join-Path $Root "apps\web"
$Api = Join-Path $Root "services\api"
$WebDist = Join-Path $Web "dist"
$BuildRoot = Join-Path $env:TEMP "yggdrasil-desktop-build"
$DistRoot = Join-Path $BuildRoot "dist"
$WorkPath = Join-Path $BuildRoot "pyinstaller-work"
$SpecPath = Join-Path $BuildRoot "spec"
$StageRoot = Join-Path $BuildRoot "stage\Yggdrasil"

Write-Host "Yggdrasil Desktop — build reproduzível para Windows" -ForegroundColor Cyan
Write-Host "Raiz: $Root"
Write-Host "Python de build: $PythonExe"

if (-not (Test-Path (Join-Path $Web "package-lock.json"))) {
    throw "apps\web\package-lock.json não encontrado. Não é possível executar npm ci de forma reproduzível."
}

Push-Location $Web
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci falhou (código $LASTEXITCODE)." }
    npm run lint
    if ($LASTEXITCODE -ne 0) { throw "ESLint falhou (código $LASTEXITCODE)." }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Build TypeScript/Vite falhou (código $LASTEXITCODE)." }
    npm run test:layout
    if ($LASTEXITCODE -ne 0) { throw "Teste do layout falhou (código $LASTEXITCODE)." }
} finally { Pop-Location }

Push-Location $Api
try {
    & $PythonExe -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Testes do backend falharam (código $LASTEXITCODE)." }
    & $PythonExe -m compileall -q app tests
    if ($LASTEXITCODE -ne 0) { throw "compileall falhou (código $LASTEXITCODE)." }
    & $PythonExe -m ruff check app tests
    if ($LASTEXITCODE -ne 0) { throw "Ruff falhou (código $LASTEXITCODE)." }
} finally { Pop-Location }

Push-Location $Root
try {
    & $PythonExe -m pytest -q desktop/tests
    if ($LASTEXITCODE -ne 0) { throw "Testes do inicializador desktop falharam (código $LASTEXITCODE)." }
} finally { Pop-Location }

& $PythonExe -m pip install "pyinstaller>=6.10,<7"
if ($LASTEXITCODE -ne 0) { throw "Não foi possível preparar PyInstaller no ambiente de build." }
if (-not (Test-Path (Join-Path $WebDist "index.html"))) { throw "Build do frontend não gerou apps\web\dist\index.html." }
if (-not (Test-Path (Join-Path $Api "alembic\env.py"))) { throw "Migrações Alembic ausentes." }

if (Test-Path $BuildRoot) { Remove-Item $BuildRoot -Recurse -Force }
New-Item -ItemType Directory -Path $DistRoot, $WorkPath, $SpecPath, $StageRoot -Force | Out-Null

$PyInstallerArgs = @(
    "--clean", "--noconfirm", "--windowed", "--onedir",
    "--name", "Yggdrasil",
    "--paths", $Api,
    "--add-data", "$WebDist;web",
    "--add-data", "$(Join-Path $Api 'alembic');alembic",
    "--add-data", "$(Join-Path $Api 'alembic.ini');.",
    "--collect-submodules", "app",
    "--collect-submodules", "uvicorn",
    "--collect-all", "alembic",
    "--collect-all", "sqlalchemy",
    "--collect-all", "uvicorn",
    "--collect-all", "httpx",
    "--collect-all", "certifi",
    "--collect-all", "psycopg",
    "--collect-all", "psycopg_binary",
    "--distpath", $DistRoot,
    "--workpath", $WorkPath,
    "--specpath", $SpecPath,
    (Join-Path $Root "desktop\launcher.py")
)
& $PythonExe -m PyInstaller @PyInstallerArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou (código $LASTEXITCODE)." }
$BuiltApp = Join-Path $DistRoot "Yggdrasil"
if (-not (Test-Path (Join-Path $BuiltApp "Yggdrasil.exe"))) { throw "Yggdrasil.exe não foi produzido." }

# Stage the runtime from a clean directory. Never copy the repository wholesale.
Copy-Item (Join-Path $BuiltApp "*") $StageRoot -Recurse -Force
Copy-Item (Join-Path $Root "LICENSE") (Join-Path $StageRoot "LICENSE") -Force
Copy-Item (Join-Path $Root "desktop\LEIA-ME-INSTALACAO.md") (Join-Path $StageRoot "LEIA-ME.md") -Force

# Remove packaging-only artifacts emitted by PyInstaller or bundled test data.
# These are generated/runtime-independent files, not user data; do not weaken the
# checks below for .env files, databases, logs, settings, or DPAPI key material.
$CleanupDirectories = Get-ChildItem -LiteralPath $StageRoot -Recurse -Force -Directory | Where-Object {
    $_.Name -in @("__pycache__", ".pytest_cache") -or
    $_.FullName -match '[\\/]certifi[\\/]tests$'
} | Sort-Object { $_.FullName.Length } -Descending
foreach ($Directory in $CleanupDirectories) {
    if (Test-Path -LiteralPath $Directory.FullName) {
        Remove-Item -LiteralPath $Directory.FullName -Recurse -Force
    }
}
Get-ChildItem -LiteralPath $StageRoot -Recurse -Force -File | Where-Object {
    $_.Extension -in @(".pyc", ".pyo")
} | Remove-Item -Force

$ForbiddenFiles = Get-ChildItem -LiteralPath $StageRoot -Recurse -Force -File | Where-Object {
    $_.Name -eq ".env" -or $_.Name -like ".env.*" -or
    $_.Name -like "*.db" -or $_.Name -like "*.sqlite" -or $_.Name -like "*.sqlite3" -or
    $_.Name -like "*.log" -or $_.Name -eq "settings.json" -or $_.Name -eq "ai-key.dpapi" -or
    $_.Name -like "*.pyc" -or $_.Name -like "*.tmp"
}
$ForbiddenDirectories = Get-ChildItem -LiteralPath $StageRoot -Recurse -Force -Directory | Where-Object {
    $_.Name -in @(".git", "node_modules", "__pycache__", ".pytest_cache", ".venv", "tests")
}
if ($ForbiddenFiles -or $ForbiddenDirectories) {
    $Names = @($ForbiddenFiles | ForEach-Object { $_.FullName }) + @($ForbiddenDirectories | ForEach-Object { $_.FullName })
    throw "O pacote contém itens locais proibidos; nada será compactado:`n$($Names -join "`n")"
}

if (-not $OutputDirectory) { $OutputDirectory = Join-Path $env:USERPROFILE "Downloads" }
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ZipPath = Join-Path $OutputDirectory "Yggdrasil-Desktop-v0.7.0-$Stamp.zip"
Compress-Archive -Path (Join-Path $StageRoot "*") -DestinationPath $ZipPath -CompressionLevel Optimal
if (-not (Test-Path $ZipPath)) { throw "O ZIP não foi criado." }
$ZipHash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$ZipPath.sha256" -Value "$ZipHash  $([IO.Path]::GetFileName($ZipPath))" -Encoding ascii

Write-Host ""
Write-Host "Pacote criado e varrido: $ZipPath" -ForegroundColor Green
Write-Host "SHA-256: $ZipHash"
Write-Host "Próximo passo: extraia o ZIP e execute desktop\test-windows-package.ps1 em Windows. A aceitação em Windows limpo ainda exige teste numa VM/máquina sem Python, Node.js e Docker."
