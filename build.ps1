<#
    Compila o baixador-ytdlp e (opcionalmente) gera o instalador.

    Uso:
        .\build.ps1                         # compila com Nuitka
        .\build.ps1 -Packager PyInstaller   # usa a rota de contingência
        .\build.ps1 -Installer              # compila e gera o setup
        .\build.ps1 -Installer -InstallInnoSetup # instala o Inno Setup, se necessário
#>
[CmdletBinding()]
param(
    [switch]$Installer,
    [switch]$InstallInnoSetup,
    [ValidateSet('PyInstaller', 'Nuitka')]
    [string]$Packager = 'Nuitka'
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
# Locks com hashes (gerados por scripts/update_locks.sh): a build local recebe
# exatamente os mesmos pacotes do CI, inclusive o CTranslate2 compatível com cuDNN 8.
Invoke-Python @('-m', 'pip', 'install', '--require-hashes', '-r', 'requirements-windows.lock', '-r', 'requirements-build-windows.lock')
# Sem PyTorch: o Whisper roda sobre CTranslate2. As DLLs CUDA compatíveis
# (runtime, cuBLAS e cuDNN 8) entram no instalador e não são baixadas pelo app.

$versionLine = Select-String -Path 'baixador_ytdlp\config.py' -Pattern '^APP_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $versionLine -or $versionLine.Line -notmatch '"([^"]+)"') {
    throw 'Não foi possível identificar APP_VERSION em baixador_ytdlp\config.py.'
}
$appVersion = $Matches[1]

Write-Host "> Compilando com $Packager" -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
if ($Packager -eq 'Nuitka') {
    # A distribuição standalone preserva bibliotecas e dados ao lado do executável.
    # Ao final ela é normalizada para o mesmo layout esperado pelo Inno Setup e
    # pelos artefatos portáteis: dist\baixador-ytdlp\baixador-ytdlp.exe.
    Invoke-Python @(
        '-m', 'nuitka', '--mode=standalone', '--assume-yes-for-downloads',
        '--enable-plugin=pyside6', '--windows-console-mode=disable',
        '--windows-icon-from-ico=assets\icon.ico',
        "--file-version=$appVersion", "--product-version=$appVersion",
        '--file-description=Baixador YT-DLP', '--include-data-dir=assets=assets',
        '--include-data-files=THIRD_PARTY_NOTICES.md=THIRD_PARTY_NOTICES.md',
        '--user-package-configuration-file=nuitka-package.config.yml',
        '--include-package=nvidia.cuda_runtime', '--include-package=nvidia.cublas',
        '--include-package=nvidia.cudnn',
        # O VAD do faster-whisper abre este modelo ONNX em tempo de execução.
        # Ele não é importável como módulo Python e precisa ser declarado como dado.
        '--include-package-data=faster_whisper:assets/silero_encoder_v5.onnx',
        # O resumo do motor usa importlib.metadata; sem estes metadados a build
        # funciona, mas exibe versoes desconhecidas em vez das versoes incluidas.
        '--include-distribution-metadata=faster-whisper',
        '--include-distribution-metadata=ctranslate2',
        '--include-distribution-metadata=nvidia-cuda-runtime-cu12',
        '--include-distribution-metadata=nvidia-cublas-cu12',
        '--include-distribution-metadata=nvidia-cudnn-cu12',
        '--output-dir=dist', '--output-filename=baixador-ytdlp.exe', 'main.py'
    )
    $nuitkaBundle = Join-Path $PSScriptRoot 'dist\main.dist'
    $releaseBundle = Join-Path $PSScriptRoot 'dist\baixador-ytdlp'
    if (-not (Test-Path -LiteralPath $nuitkaBundle -PathType Container)) {
        throw "O Nuitka terminou sem gerar a pasta $nuitkaBundle"
    }
    Move-Item -LiteralPath $nuitkaBundle -Destination $releaseBundle
    $exe = Join-Path $releaseBundle 'baixador-ytdlp.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw "O Nuitka terminou sem gerar $exe"
    }
} else {
    Invoke-Python @('-m', 'PyInstaller', 'baixador_ytdlp.spec', '--noconfirm')
    $exe = Join-Path $PSScriptRoot 'dist\baixador-ytdlp\baixador-ytdlp.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw "O PyInstaller terminou sem gerar $exe"
    }
}

# Falha o build se alguma DLL carregada tardiamente pelo CTranslate2 ficar fora
# do pacote. Isso evita publicar uma build que só descobre a falta na inferência.
$requiredCudaDlls = @(
    'cudart64_12.dll', 'cublas64_12.dll', 'cublasLt64_12.dll',
    'cudnn64_8.dll', 'cudnn_ops_infer64_8.dll', 'cudnn_cnn_infer64_8.dll'
)
$missingCudaDlls = foreach ($dll in $requiredCudaDlls) {
    if (-not (Get-ChildItem -Path (Split-Path -Parent $exe) -Filter $dll -File -Recurse -ErrorAction SilentlyContinue)) {
        $dll
    }
}
if ($missingCudaDlls) {
    throw "A build não incluiu as DLLs CUDA obrigatórias: $($missingCudaDlls -join ', ')"
}
$requiredRuntimeFiles = @('faster_whisper\assets\silero_encoder_v5.onnx')
$missingRuntimeFiles = foreach ($file in $requiredRuntimeFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path (Split-Path -Parent $exe) $file) -PathType Leaf)) {
        $file
    }
}
if ($missingRuntimeFiles) {
    throw "A build não incluiu os dados obrigatórios do faster-whisper: $($missingRuntimeFiles -join ', ')"
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
