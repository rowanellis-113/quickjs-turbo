[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('msvc', 'mingw')][string]$Toolchain,
    [ValidateSet('PORTABLE', 'AUTO', 'WIN64')][string]$Backend = 'AUTO',
    [string]$BuildPath,
    [string]$CMake = 'cmake',
    [string]$Ninja = 'ninja',
    [string]$Compiler,
    [string]$Objdump,
    [string]$Assembler,
    [string]$VisualStudioPath,
    [ValidateRange(1, 64)][int]$Jobs = 4,
    [switch]$Shared,
    [ValidateSet('MD', 'MT')][string]$MsvcRuntime = 'MD',
    [string]$DefaultExperimentAllocator = '',
    [switch]$ConfigureOnly,
    [switch]$Test
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($Toolchain -ne 'msvc' -and $PSBoundParameters.ContainsKey('MsvcRuntime')) {
    throw 'MsvcRuntime applies only to the msvc toolchain.'
}
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
$repoRoot = Split-Path -Parent $projectRoot
$runtimeTag = if ($Toolchain -eq 'msvc' -and $MsvcRuntime -eq 'MT') { '-mt' }else { '' }
if (!$BuildPath) {
    $suffix = if ($Shared) { '-shared' }elseif ($Backend -eq 'PORTABLE') { '-portable' }else { '' }
    $BuildPath = Join-Path $repoRoot "build/$Toolchain$runtimeTag-product$suffix"
}
$options = @{}
foreach ($key in $PSBoundParameters.Keys) { $options[$key] = $PSBoundParameters[$key] }
$options['Toolchain'] = $Toolchain
$options['Backend'] = $Backend
$options['BuildPath'] = $BuildPath
$options['Jobs'] = $Jobs
foreach ($flag in @('ExperimentalAllocator', 'ExperimentalCompare', 'ComputedAssignment',
        'Value64Init', 'MixedNumbers', 'MapPointerHash', 'PropertyIC', 'PortableRegExp')) {
    $options[$flag] = $true
}
$hadAllocator = Test-Path Env:QJS_EXPERIMENT_ALLOCATOR
$savedAllocator = $env:QJS_EXPERIMENT_ALLOCATOR
try {
    $env:QJS_EXPERIMENT_ALLOCATOR = '256'
    & (Join-Path $PSScriptRoot 'build-interpreter.ps1') @options
} finally {
    if ($hadAllocator) { $env:QJS_EXPERIMENT_ALLOCATOR = $savedAllocator }
    else { Remove-Item Env:QJS_EXPERIMENT_ALLOCATOR -ErrorAction SilentlyContinue }
}
