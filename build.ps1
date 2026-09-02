<#
    Compila o baixador-ytdlp e (opcionalmente) gera o instalador.

    Uso:
        .\build.ps1              # só compila
        .\build.ps1 -Installer   # compila e gera o setup (precisa do Inno Setup)
#>
param([switch]$Installer)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
    Write-Host '> Criando ambiente virtual' -ForegroundColor Cyan
    python -m venv .venv
}
& .\.venv\Scripts\Activate.ps1

Write-Host '> Instalando dependências' -ForegroundColor Cyan
python -m pip install --upgrade pip | Out-Null
pip install -r requirements.txt pyinstaller | Out-Null
# A variante CUDA deixa o Whisper usar a NVIDIA quando o driver estiver disponível.
pip install torch --index-url https://download.pytorch.org/whl/cu126 | Out-Null

Write-Host '> Compilando' -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
pyinstaller baixador_ytdlp.spec --noconfirm

Write-Host "> Pronto: dist\baixador-ytdlp\baixador-ytdlp.exe" -ForegroundColor Green

if ($Installer) {
    $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (-not (Test-Path $iscc)) { throw "Inno Setup 6 não encontrado em $iscc" }
    Write-Host '> Gerando instalador' -ForegroundColor Cyan
    & $iscc installer.iss
    Write-Host '> Instalador em: dist\installer' -ForegroundColor Green
}
