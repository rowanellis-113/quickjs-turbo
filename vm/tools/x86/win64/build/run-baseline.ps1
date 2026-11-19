[CmdletBinding()]
param(
    [ValidateSet('msvc', 'mingw')][string]$Toolchain = 'msvc',
    [string]$BuildPath,
    [string[]]$Arguments = @(),
    [ValidateSet('MD', 'MT')][string]$MsvcRuntime = 'MD'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($Toolchain -ne 'msvc' -and $PSBoundParameters.ContainsKey('MsvcRuntime')) {
    throw 'MsvcRuntime applies only to the msvc toolchain.'
}
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
$repoRoot = Split-Path -Parent $projectRoot
$runtimeTag = if ($Toolchain -eq 'msvc' -and $MsvcRuntime -eq 'MT') { '-mt' }else { '' }
if (!$BuildPath) { $BuildPath = Join-Path $repoRoot "build/$Toolchain$runtimeTag-product" }
$exe = Join-Path $BuildPath 'qjs.exe'
$receiptPath = Join-Path $BuildPath 'interpreter-build.json'
if (!(Test-Path -LiteralPath $receiptPath -PathType Leaf)) { throw 'Build this baseline with tools/x86/win64/build/build-baseline.ps1 first.' }
$receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($receipt.status -ne 'passed') { throw 'The baseline producer did not pass its build checks.' }
foreach ($setting in @('QJS_FRAME_EXPERIMENTAL_ALLOCATOR', 'QJS_FRAME_EXPERIMENTAL_COMPARE',
        'QJS_BACKPORT_COMPUTED_ASSIGN', 'QJS_BACKPORT_VALUE64_INIT',
        'QJS_BACKPORT_MIXED_NUMBERS', 'QJS_BACKPORT_MAP_POINTER_HASH', 'QJS_PROPERTY_IC',
        'QJS_BACKPORT_PORTABLE_REGEXP')) {
    if ($receipt.configure_arguments -notcontains "-D${setting}=ON") { throw "Missing baseline setting: $setting" }
}
if ((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -ne $receipt.outputs.'qjs.exe') {
    throw 'qjs.exe does not match its producer receipt.'
}
$hadAllocator = Test-Path Env:QJS_EXPERIMENT_ALLOCATOR
$savedAllocator = $env:QJS_EXPERIMENT_ALLOCATOR
try {
    $env:QJS_EXPERIMENT_ALLOCATOR = '256'
    & $exe @Arguments
    $result = $LASTEXITCODE
} finally {
    if ($hadAllocator) { $env:QJS_EXPERIMENT_ALLOCATOR = $savedAllocator }
    else { Remove-Item Env:QJS_EXPERIMENT_ALLOCATOR -ErrorAction SilentlyContinue }
}
exit $result
