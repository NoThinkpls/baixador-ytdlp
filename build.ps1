<#
    Compila o baixador-ytdlp e (opcionalmente) gera o instalador.

    Uso:
        .\build.ps1                         # só compila
        .\build.ps1 -Installer              # compila e gera o setup
        .\build.ps1 -Installer -InstallInnoSetup # instala o Inno Setup, se necessário
#>
[CmdletBinding()]
param(
    [switch]$Installer,
    [switch]$InstallInnoSetup
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

# Evita mensagens corrompidas quando a saída é salva em um log UTF-8.
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

function Get-InnoSetupCompiler {
    $candidates = [System.Collections.Generic.List[string]]::new()

    # Alguns instaladores registram o compilador no PATH.
    $command = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
    if ($command -and $command.Path) { $candidates.Add($command.Path) }

    # A edição de 64 bits pode ser instalada em Program Files; a de 32 bits,
    # em Program Files (x86). As duas situações acontecem no Windows atual.
    foreach ($base in @($env:ProgramW6432, $env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ($base) { $candidates.Add((Join-Path $base 'Inno Setup 6\ISCC.exe')) }
    }

    # A localização registrada cobre instalações personalizadas.
    foreach ($key in @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1'
    )) {
        $entry = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
        if ($entry -and $entry.InstallLocation) {
            $candidates.Add((Join-Path $entry.InstallLocation 'ISCC.exe'))
        }
    }

    return $candidates |
        Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
        Select-Object -First 1
}

function Install-InnoSetup {
    $winget = Get-Command 'winget.exe' -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw 'O Inno Setup 6 não foi encontrado e o winget não está disponível. Instale-o em https://jrsoftware.org/isdl.php e execute o comando novamente.'
    }

    Write-Host '> Instalando o Inno Setup 6 via winget' -ForegroundColor Cyan
    & $winget.Path install --exact --id JRSoftware.InnoSetup --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "A instalação do Inno Setup falhou com código $LASTEXITCODE" }
}

if (-not (Test-Path .venv)) {
    Write-Host '> Criando ambiente virtual' -ForegroundColor Cyan
    python -m venv .venv
}

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "O Python do ambiente virtual não foi criado em $python"
}

function Invoke-Python {
    param([string[]]$PythonArgs)
    & $python @PythonArgs
    if ($LASTEXITCODE -ne 0) { throw "Falha ao executar: python $($PythonArgs -join ' ') (código $LASTEXITCODE)" }
}

Write-Host '> Instalando dependências' -ForegroundColor Cyan
Invoke-Python @('-m', 'pip', 'install', '--upgrade', 'pip')
Invoke-Python @('-m', 'pip', 'install', '-r', 'requirements.txt', 'pyinstaller')
# Sem PyTorch: o Whisper roda sobre CTranslate2 e as bibliotecas CUDA
# (nvidia-cublas-cu12, nvidia-cudnn-cu12) são baixadas na máquina do usuário
# apenas quando existe uma GPU NVIDIA.

Write-Host '> Compilando' -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
Invoke-Python @('-m', 'PyInstaller', 'baixador_ytdlp.spec', '--noconfirm')

$exe = Join-Path $PSScriptRoot 'dist\baixador-ytdlp\baixador-ytdlp.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "O PyInstaller terminou sem gerar $exe"
}
Write-Host "> Pronto: $exe" -ForegroundColor Green

if ($Installer) {
    $iscc = Get-InnoSetupCompiler
    if (-not $iscc -and $InstallInnoSetup) {
        Install-InnoSetup
        $iscc = Get-InnoSetupCompiler
    }
    if (-not $iscc) {
        throw 'Inno Setup 6 não encontrado. Execute .\build.ps1 -Installer -InstallInnoSetup ou instale-o em https://jrsoftware.org/isdl.php.'
    }

    $versionLine = Select-String -Path 'baixador_ytdlp\config.py' -Pattern '^APP_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
    if (-not $versionLine -or $versionLine.Line -notmatch '"([^"]+)"') {
        throw 'Não foi possível identificar APP_VERSION em baixador_ytdlp\config.py.'
    }
    $appVersion = $Matches[1]

    Write-Host '> Gerando instalador' -ForegroundColor Cyan
    & $iscc "/DAppVersion=$appVersion" installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup falhou com código $LASTEXITCODE" }

    $setup = Join-Path $PSScriptRoot "dist\installer\BaixadorYtdlp-$appVersion-setup.exe"
    if (-not (Test-Path -LiteralPath $setup -PathType Leaf)) {
        throw "O Inno Setup terminou sem gerar $setup"
    }
    $sha256 = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash
    Set-Content -LiteralPath "$setup.sha256" -Value "$sha256  $(Split-Path $setup -Leaf)" -Encoding utf8
    Write-Host "> Instalador em: $setup" -ForegroundColor Green
    Write-Host "> SHA-256 em: $setup.sha256" -ForegroundColor Green
}
