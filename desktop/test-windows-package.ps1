param([string]$PackageDirectory = "")
$ErrorActionPreference = "Stop"
if (-not $PackageDirectory) { $PackageDirectory = $PSScriptRoot }
$PackageDirectory = (Resolve-Path $PackageDirectory).Path
$Exe = Join-Path $PackageDirectory "Yggdrasil.exe"
if (-not (Test-Path $Exe)) { throw "Yggdrasil.exe não encontrado em $PackageDirectory" }
$DataRoot = Join-Path $env:LOCALAPPDATA "Yggdrasil"
$PortFile = Join-Path $DataRoot "desktop-port.txt"
$DbFile = Join-Path $DataRoot "data\yggdrasil.db"

if (-not ("YggdrasilSmokeWin32" -as [type])) {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class YggdrasilSmokeWin32 {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
}
"@
}

function Test-TcpPort([int]$Port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $result = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $connected = $result.AsyncWaitHandle.WaitOne(250)
        if ($connected -and $client.Connected) { $client.EndConnect($result); $client.Close(); return $true }
        $client.Close()
    } catch {}
    return $false
}

function Start-And-CheckYggdrasil {
    if (Test-Path $PortFile) {
        $oldPort = 0
        [void][int]::TryParse((Get-Content $PortFile -ErrorAction SilentlyContinue | Select-Object -First 1), [ref]$oldPort)
        if ($oldPort -gt 0 -and (Test-TcpPort $oldPort)) {
            throw "Já existe uma instância ou uma porta de Yggdrasil ativa ($oldPort). Feche-a antes do smoke test."
        }
        Remove-Item $PortFile -Force -ErrorAction SilentlyContinue
    }
    $previousSmoke = $env:YGGDRASIL_SMOKE_TEST_NO_BROWSER
    $env:YGGDRASIL_SMOKE_TEST_NO_BROWSER = "1"
    try { $launcher = Start-Process -FilePath $Exe -PassThru }
    finally { $env:YGGDRASIL_SMOKE_TEST_NO_BROWSER = $previousSmoke }

    $deadline = (Get-Date).AddSeconds(45)
    $port = 0
    while ((Get-Date) -lt $deadline) {
        if ($launcher.HasExited) { throw "O inicializador encerrou antes de publicar a porta. Verifique logs/runtime.log." }
        if (Test-Path $PortFile) {
            [void][int]::TryParse((Get-Content $PortFile -ErrorAction SilentlyContinue | Select-Object -First 1), [ref]$port)
            if ($port -gt 0 -and (Test-TcpPort $port)) { break }
        }
        Start-Sleep -Milliseconds 300
    }
    if ($port -le 0 -or -not (Test-TcpPort $port)) { throw "O servidor local não abriu uma porta dentro do prazo." }

    $base = "http://127.0.0.1:$port"
    $page = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 5
    if ($page.StatusCode -ne 200 -or $page.Content -notmatch 'id="root"') { throw "A interface web não foi servida corretamente." }
    $asset = [regex]::Match($page.Content, '(?:src|href)="(/assets/[^" ]+)"')
    if (-not $asset.Success) { throw "O HTML não referencia os assets de produção esperados." }
    $assetResponse = Invoke-WebRequest -Uri ($base + $asset.Groups[1].Value) -UseBasicParsing -TimeoutSec 5
    if ($assetResponse.StatusCode -ne 200) { throw "O frontend não carregou o asset de produção." }
    $bootstrap = Invoke-WebRequest -Uri "$base/desktop-bootstrap.js" -UseBasicParsing -TimeoutSec 5
    $match = [regex]::Match($bootstrap.Content, 'window\.__YGGDRASIL_API_TOKEN__\s*=\s*"([A-Za-z0-9_-]+)";')
    if (-not $match.Success) { throw "O token temporário da sessão não foi entregue no bootstrap local." }
    $headers = @{ "X-Yggdrasil-Token" = $match.Groups[1].Value }
    $unauthorizedRejected = $false
    try {
        Invoke-WebRequest -Uri "$base/api/v1/health" -UseBasicParsing -TimeoutSec 5 | Out-Null
    } catch {
        if ($_.Exception.Response -and [int]$_.Exception.Response.StatusCode -eq 403) {
            $unauthorizedRejected = $true
        }
    }
    if (-not $unauthorizedRejected) { throw "A API não recusou uma requisição sem token de sessão." }
    $health = Invoke-RestMethod -Uri "$base/api/v1/health" -Headers $headers -TimeoutSec 5
    if ($health.status -ne "ok" -or $health.database -ne "ok") { throw "Health check falhou." }
    if (-not (Test-Path $DbFile)) { throw "Banco SQLite não foi criado em $DbFile" }
    $dbSize = (Get-Item $DbFile).Length
    if ($dbSize -le 0) { throw "O arquivo SQLite está vazio." }
    return @{ Process = $launcher; Port = $port; Token = $match.Groups[1].Value; DatabaseSize = $dbSize }
}

function Stop-TestInstance($Instance) {
    if (-not $Instance) { return }
    $proc = Get-Process -Id $Instance.Process.Id -ErrorAction SilentlyContinue
    if ($proc -and $proc.MainWindowHandle -ne [IntPtr]::Zero) {
        [void][YggdrasilSmokeWin32]::SendMessage($proc.MainWindowHandle, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
    }
    try { $Instance.Process.WaitForExit(10000) } catch {}
    if (-not $Instance.Process.HasExited) {
        throw "O inicializador não encerrou após WM_CLOSE. Feche manualmente a janela; o teste não força o encerramento para evitar deixar o backend órfão."
    }
    $deadline = (Get-Date).AddSeconds(8)
    while ((Get-Date) -lt $deadline -and (Test-TcpPort $Instance.Port)) { Start-Sleep -Milliseconds 250 }
    if (Test-TcpPort $Instance.Port) { throw "A porta do backend continuou aberta depois do encerramento do inicializador." }
    if (Test-Path $PortFile) { throw "O arquivo temporário da porta não foi removido no encerramento controlado." }
}

Write-Host "Smoke test do pacote Yggdrasil Desktop" -ForegroundColor Cyan
Write-Host "Executável: $Exe"
$first = Start-And-CheckYggdrasil
try { Stop-TestInstance $first } catch { throw }
Write-Host "[PASS] Primeira inicialização, UI, token local, health check e SQLite." -ForegroundColor Green

$second = Start-And-CheckYggdrasil
try { Stop-TestInstance $second } catch { throw }
if ($second.DatabaseSize -le 0 -or -not (Test-Path $DbFile)) { throw "O banco não persistiu após reiniciar." }
Write-Host "[PASS] Segunda inicialização com o banco persistente." -ForegroundColor Green
Write-Host "Smoke test concluído. Ainda faça um teste manual de uso real e, para o aceite final, repita em Windows limpo sem Python/Node.js/Docker." -ForegroundColor Yellow
