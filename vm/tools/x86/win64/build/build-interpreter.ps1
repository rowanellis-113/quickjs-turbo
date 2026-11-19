[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('msvc', 'mingw')][string]$Toolchain,
    [ValidateSet('PORTABLE', 'AUTO', 'WIN64')][string]$Backend = 'PORTABLE',
    [string]$BuildPath,
    [string]$CMake = 'cmake',
    [string]$Ninja = 'ninja',
    [string]$Compiler,
    [string]$Objdump,
    [string]$Assembler,
    [switch]$PortableRegExp,
    [string]$VisualStudioPath,
    [ValidateRange(1, 64)][int]$Jobs = 4,
    [switch]$Diagnostics,
    [switch]$ExperimentalAllocator,
    [switch]$ExperimentalCompare,
    [switch]$ComputedAssignment,
    [switch]$Value64Init,
    [switch]$MixedNumbers,
    [switch]$MapPointerHash,
    [switch]$PropertyIC,
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
$sourcePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../../..'))
$repoRoot = Split-Path -Parent $sourcePath
$runtimeTag = if ($Toolchain -eq 'msvc' -and $MsvcRuntime -eq 'MT') { '-mt' }else { '' }
if (!$BuildPath) { $BuildPath = Join-Path $repoRoot "build/$Toolchain$runtimeTag-$($Backend.ToLowerInvariant())" }
$buildDirectory = [IO.Path]::GetFullPath($BuildPath)
if ($buildDirectory -eq $sourcePath) { throw 'Use an out-of-source BuildPath.' }

function Resolve-Tool([string]$Value) {
    $found = Get-Command -Name $Value -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (!$found) { throw "Tool not found: $Value. Supply its full path or add it to PATH." }
    return $found.Source
}
function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    # Windows PowerShell represents native stderr as ErrorRecord objects;
    # warnings on stderr must not replace the process exit-code decision.
    $ErrorActionPreference = 'Continue'
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
function Get-FrameBuildOutputs {
    param(
        [Parameter(Mandatory = $true)][string]$BuildDirectory,
        [Parameter(Mandatory = $true)][ValidateSet('msvc', 'mingw')][string]$Toolchain,
        [switch]$Shared,
        [bool]$IncludeProducts = $true,
        [bool]$RequireComplete = $true
    )
    $names = @('CMakeCache.txt', 'compile_commands.json')
    if ($IncludeProducts) {
        $library = if ($Toolchain -eq 'mingw') {
            if ($Shared) { 'libqjs.dll.a' }else { 'libqjs.a' }
        } else { 'qjs.lib' }
        $required = @($library)
        $names += @($library, 'qjs.exe', 'qjsc.exe', 'run-test262.exe', 'api-test.exe',
            'function_source.exe', 'qjs.pdb', 'qjs_exe.pdb', 'qjs_cli.pdb', 'qjsc.pdb')
        $names += if ($Toolchain -eq 'mingw') { 'libqjs-libc.a' }else { 'qjs-libc.lib' }
        if ($Shared) {
            $dll = if ($Toolchain -eq 'mingw') { 'libqjs.dll' }else { 'qjs.dll' }
            $required += , $dll
            $names += , $dll
        }
        if ($RequireComplete) {
            foreach ($name in $required) {
                if (!(Test-Path -LiteralPath (Join-Path $BuildDirectory $name) -PathType Leaf)) {
                    throw "Required engine artifact missing: $name"
                }
            }
        }
    }
    $outputs = @{}
    foreach ($name in $names) {
        $path = Join-Path $BuildDirectory $name
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $outputs[$name] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    return $outputs
}

if ($Toolchain -eq 'msvc') {
    if (!(Get-Command cl -ErrorAction SilentlyContinue) -or $VisualStudioPath) {
        if (!$VisualStudioPath) {
            $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
            if (!(Test-Path -LiteralPath $vswhere -PathType Leaf)) { throw 'Use an x64 VS developer shell or specify VisualStudioPath.' }
            $VisualStudioPath = (& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1)
        }
        $vcvars = Join-Path $VisualStudioPath 'VC/Auxiliary/Build/vcvars64.bat'
        if (!(Test-Path -LiteralPath $vcvars -PathType Leaf)) { throw "Missing vcvars64.bat: $vcvars" }
        $lines = & $env:ComSpec /d /c "call `"$vcvars`" >nul && set"
        if ($LASTEXITCODE -ne 0) { throw 'vcvars64 failed' }
        foreach ($line in $lines) {
            if ($line -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') }
        }
    }
    $env:VSLANG = '1033'
    if (!$Compiler) { $Compiler = 'cl' }
} else {
    if (!$Compiler) { $Compiler = 'gcc' }
}
$compilerPath = Resolve-Tool $Compiler
$cmakePath = Resolve-Tool $CMake
$ninjaPath = Resolve-Tool $Ninja
$env:Path = "$(Split-Path -Parent $compilerPath);$env:Path"
if (!$Objdump) {
    $sibling = Join-Path (Split-Path -Parent $compilerPath) 'objdump.exe'
    if (Test-Path -LiteralPath $sibling -PathType Leaf) { $Objdump = $sibling }
}
if ($Objdump) { $Objdump = Resolve-Tool $Objdump }
if ($Assembler) { $Assembler = Resolve-Tool $Assembler }

New-Item -ItemType Directory -Path $buildDirectory -Force | Out-Null
$env:PYTHONDONTWRITEBYTECODE = '1'
$diagnosticValue = if ($Diagnostics) { 'ON' }else { 'OFF' }
$sharedValue = if ($Shared) { 'ON' }else { 'OFF' }
$allocatorValue = if ($ExperimentalAllocator) { 'ON' }else { 'OFF' }
$compareValue = if ($ExperimentalCompare) { 'ON' }else { 'OFF' }
$assignmentValue = if ($ComputedAssignment) { 'ON' }else { 'OFF' }
$value64Value = if ($Value64Init) { 'ON' }else { 'OFF' }
$mixedValue = if ($MixedNumbers) { 'ON' }else { 'OFF' }
$mapHashValue = if ($MapPointerHash) { 'ON' }else { 'OFF' }
$propertyICValue = if ($PropertyIC) { 'ON' }else { 'OFF' }
$portableRegExpValue = if ($PortableRegExp) { 'ON' }else { 'OFF' }
$arguments = @('-S', $sourcePath, '-B', $buildDirectory, '-G', 'Ninja',
    "-DCMAKE_MAKE_PROGRAM=$ninjaPath", "-DCMAKE_C_COMPILER=$compilerPath", '-DCMAKE_BUILD_TYPE=Release',
    '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON', "-DQJS_FRAME_BACKEND=$Backend",
    "-DQJS_INTERP_FRAME_DIAGNOSTICS=$diagnosticValue", "-DBUILD_SHARED_LIBS=$sharedValue",
    "-DQJS_FRAME_EXPERIMENTAL_ALLOCATOR=$allocatorValue",
    "-DQJS_FRAME_EXPERIMENTAL_COMPARE=$compareValue", "-DQJS_BACKPORT_COMPUTED_ASSIGN=$assignmentValue",
    "-DQJS_BACKPORT_VALUE64_INIT=$value64Value", "-DQJS_BACKPORT_MIXED_NUMBERS=$mixedValue",
    "-DQJS_BACKPORT_MAP_POINTER_HASH=$mapHashValue",
    "-DQJS_PROPERTY_IC=$propertyICValue",
    "-DQJS_BACKPORT_PORTABLE_REGEXP=$portableRegExpValue",
    '-DQJS_FRAME_BUILD_TESTS=ON')
if ($DefaultExperimentAllocator) {
    $arguments += , "-DQJS_DEFAULT_EXPERIMENT_ALLOCATOR=$DefaultExperimentAllocator"
}
if ($Objdump -and $Backend -ne 'PORTABLE') { $arguments += , "-DQJS_FRAME_OBJDUMP=$Objdump" }
if ($Assembler -and $Backend -ne 'PORTABLE') { $arguments += , "-DQJS_FRAME_AS=$Assembler" }
if ($Toolchain -eq 'msvc') {
    # Probe the installed compiler's actual include prefix. VSLANG cannot
    # select English when that language pack is absent; hard-coding either
    # language breaks Ninja dependencies on another installation.
    $probeHeader = Join-Path $buildDirectory 'interpreter-include-probe.h'
    $probeSource = Join-Path $buildDirectory 'interpreter-include-probe.c'
    Set-Content -LiteralPath $probeHeader -Value '/* include-prefix probe */' -Encoding ASCII
    Set-Content -LiteralPath $probeSource -Value '#include "interpreter-include-probe.h"' -Encoding ASCII
    $probe = New-Object Diagnostics.Process
    $probe.StartInfo.FileName = $compilerPath
    $probe.StartInfo.Arguments = '/nologo /showIncludes /EP "' + $probeSource + '"'
    $probe.StartInfo.UseShellExecute = $false
    $probe.StartInfo.CreateNoWindow = $true
    $probe.StartInfo.RedirectStandardOutput = $true
    $probe.StartInfo.RedirectStandardError = $true
    $probe.StartInfo.StandardOutputEncoding = [Text.Encoding]::Default
    $probe.StartInfo.StandardErrorEncoding = [Text.Encoding]::Default
    [void]$probe.Start()
    $stdoutTask = $probe.StandardOutput.ReadToEndAsync()
    $stderrTask = $probe.StandardError.ReadToEndAsync()
    if (!$probe.WaitForExit(20000)) { $probe.Kill(); throw 'MSVC include-prefix probe timed out' }
    $probeText = $stdoutTask.GetAwaiter().GetResult() + "`n" + $stderrTask.GetAwaiter().GetResult()
    if ($probe.ExitCode -ne 0) { throw "MSVC include-prefix probe failed: $probeText" }
    $probe.Dispose()
    $probeLines = $probeText -split '\r?\n'
    $prefix = $null
    foreach ($line in $probeLines) {
        if ($line -match '^(.*?)([A-Za-z]:[\\/].*interpreter-include-probe\.h)\s*$') { $prefix = $matches[1]; break }
    }
    if (!$prefix) { throw 'Could not detect the installed MSVC /showIncludes prefix' }
    $prefixFile = Join-Path $buildDirectory 'interpreter-msvc-prefix.cmake'
    $prefixText = 'set(CMAKE_CL_SHOWINCLUDES_PREFIX [==[' + $prefix + ']==])'
    [IO.File]::WriteAllText($prefixFile, $prefixText + "`n", (New-Object Text.UTF8Encoding($false)))
    $msvcRuntimeLibrary = if ($MsvcRuntime -eq 'MT') { 'MultiThreaded' }else { 'MultiThreadedDLL' }
    $arguments += @('-DCMAKE_C_FLAGS=/utf-8 /Zi',
        "-DCMAKE_MSVC_RUNTIME_LIBRARY=$msvcRuntimeLibrary",
        "-DCMAKE_PROJECT_quickjs_INCLUDE=$prefixFile",
        '-DCMAKE_EXE_LINKER_FLAGS_RELEASE=/INCREMENTAL:NO /DEBUG:FULL /OPT:REF /OPT:ICF')
} else { $arguments += , '-DCMAKE_C_FLAGS=-g -gdwarf-4' }
$started = [DateTime]::UtcNow.ToString('o')
$receipt = [ordered]@{schema=1; status='running'; started=$started; source=$sourcePath; build=$buildDirectory;
    toolchain=$Toolchain; msvc_runtime=$(if ($Toolchain -eq 'msvc') { $MsvcRuntime }else { $null });
    default_experiment_allocator=$DefaultExperimentAllocator;
    backend_requested=$Backend; compiler=$compilerPath; cmake=$cmakePath; ninja=$ninjaPath;
    objdump=$Objdump; assembler=$Assembler; configure_arguments=$arguments; steps=@()
}
$receiptPath = Join-Path $buildDirectory 'interpreter-build.json'
$artifactFailure = $null
try {
    Invoke-Checked $cmakePath $arguments
    $receipt.steps += , 'configure'
    if (!$ConfigureOnly) {
        Invoke-Checked $cmakePath @('--build', $buildDirectory, '--parallel', "$Jobs")
        $receipt.steps += , 'build'
        if ($Test) {
            $ctest = Join-Path (Split-Path -Parent $cmakePath) 'ctest.exe'
            Invoke-Checked $ctest @('--test-dir', $buildDirectory, '--output-on-failure')
            $receipt.steps += , 'ctest'
        }
    }
    $receipt.status = 'passed'
} catch {
    $receipt.status = 'failed'; $receipt.error = $_.Exception.Message; throw
} finally {
    $receipt.finished = [DateTime]::UtcNow.ToString('o')
    $receipt.source_revision = $null
    $receipt.source_status = $null
    if ((Test-Path -LiteralPath (Join-Path $repoRoot '.git')) -and (Get-Command git -ErrorAction SilentlyContinue)) {
        $receipt.source_revision = (& git -C $repoRoot rev-parse HEAD | Out-String).Trim()
        $receipt.source_status = @(& git -C $repoRoot status --porcelain)
    }
    $epochPath = Join-Path $buildDirectory 'interpreter-native-epoch.json'
    $backendPath = Join-Path $buildDirectory 'interpreter-backend.json'
    if (Test-Path -LiteralPath $backendPath -PathType Leaf) {
        $receipt.backend = Get-Content -LiteralPath $backendPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    if ((Test-Path -LiteralPath $epochPath -PathType Leaf) -and $receipt.Contains('backend') -and $receipt.backend.effective -eq 'WIN64') {
        $receipt.native_epoch = Get-Content -LiteralPath $epochPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    $receipt.inputs = @{}
    foreach ($path in @($compilerPath, $cmakePath, $ninjaPath)) { $receipt.inputs[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() }
    try {
        $receipt.outputs = Get-FrameBuildOutputs -BuildDirectory $buildDirectory -Toolchain $Toolchain `
            -Shared:$Shared -IncludeProducts:(-not $ConfigureOnly) `
            -RequireComplete:($receipt.status -eq 'passed' -and -not $ConfigureOnly)
    } catch {
        $artifactFailure = $_.Exception
        $receipt.outputs = @{}
        $receipt.status = 'failed'
        $receipt.artifact_error = $artifactFailure.Message
    }
    $receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $receiptPath -Encoding UTF8
}
if ($artifactFailure) { throw $artifactFailure }
