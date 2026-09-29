<#
    Atualiza o runtime C++ (msvcp140*, vcruntime140*) dentro da pasta gerada pelo Nuitka.

    O Nuitka copia essas DLLs da primeira pasta que as tem. Na prática vieram
    versões 14.29, mais antigas que as exigidas pelo onnxruntime 1.30: o
    `import onnxruntime` derrubava o processo com "segmentation fault" e o
    autoteste da build falhava (a 1.10.9 passava por acaso, com outra origem).
    Aqui cada DLL do pacote é trocada pela cópia mais nova entre o System32 e o
    PySide6 instalado, sem nunca rebaixar a versão.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Bundle,
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'
$names = 'msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'msvcp140_codecvt_ids.dll',
    'vcruntime140.dll', 'vcruntime140_1.dll', 'concrt140.dll'

$sources = [System.Collections.Generic.List[string]]::new()
$sources.Add((Join-Path $env:SystemRoot 'System32'))
$pyside = & $Python -c "import PySide6, pathlib; print(pathlib.Path(PySide6.__file__).parent)"
if ($LASTEXITCODE -eq 0 -and $pyside) { $sources.Add($pyside.Trim()) }

function Get-DllVersion([string]$path) {
    try { return [version](Get-Item -LiteralPath $path).VersionInfo.ProductVersion } catch { return [version]'0.0' }
}

foreach ($name in $names) {
    $bundled = Join-Path $Bundle $name
    if (-not (Test-Path -LiteralPath $bundled -PathType Leaf)) { continue }
    $best = $null
    $bestVersion = Get-DllVersion $bundled
    foreach ($folder in $sources) {
        $candidate = Join-Path $folder $name
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $version = Get-DllVersion $candidate
        if ($version -gt $bestVersion) { $best = $candidate; $bestVersion = $version }
    }
    if ($best) {
        Copy-Item -LiteralPath $best -Destination $bundled -Force
        Write-Host "> $name atualizado para $bestVersion ($best)" -ForegroundColor DarkGray
    }
}
