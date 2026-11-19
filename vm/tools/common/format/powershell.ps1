param(
    [Parameter(Mandatory = $true)][string]$ModulePath,
    [switch]$Write
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Import-Module -Name $ModulePath -Force -ErrorAction Stop
if ((Get-Command Invoke-Formatter).Version -ne [version]'1.24.0') {
    throw 'Expected PSScriptAnalyzer 1.24.0'
}
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$settings = @{
    IncludeRules = @(
        'PSPlaceOpenBrace', 'PSPlaceCloseBrace',
        'PSUseConsistentWhitespace', 'PSUseConsistentIndentation'
    )
    Rules = @{
        PSPlaceOpenBrace = @{
            Enable = $true; OnSameLine = $true; NewLineAfter = $true
            IgnoreOneLineBlock = $true
        }
        PSPlaceCloseBrace = @{
            Enable = $true; NewLineAfter = $false; IgnoreOneLineBlock = $true
            NoEmptyLineBefore = $false
        }
        PSUseConsistentIndentation = @{
            Enable = $true; Kind = 'space'; IndentationSize = 4
            PipelineIndentation = 'IncreaseIndentationForFirstPipeline'
        }
        PSUseConsistentWhitespace = @{
            Enable = $true; CheckInnerBrace = $true; CheckOpenBrace = $true
            CheckOpenParen = $true; CheckOperator = $true; CheckPipe = $true
            CheckPipeForRedundantWhitespace = $true; CheckSeparator = $true
            CheckParameter = $false; IgnoreAssignmentOperatorInsideHashTable = $true
        }
    }
}

function Get-SyntaxContract([string]$Text) {
    $tokens = $null
    $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseInput($Text, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw "PowerShell parse error: $($errors[0].Message)" }
    $contract = [Collections.Generic.List[string]]::new()
    foreach ($token in $tokens) {
        if ($token.Kind.ToString() -notin @('NewLine', 'LineContinuation', 'Comment', 'EndOfInput')) {
            $contract.Add("$($token.Kind):$($token.Text.Length):$($token.Text)")
        }
    }
    foreach ($node in $ast.FindAll({ $true }, $true)) {
        $depth = 0
        for ($parent = $node.Parent; $null -ne $parent; $parent = $parent.Parent) { $depth++ }
        $contract.Add("AST:$depth`:$($node.GetType().FullName)")
    }
    return [string]::Join("`n", $contract)
}

$changes = @{}
$files = @(Get-ChildItem -LiteralPath (Join-Path $root 'tools') -Filter '*.ps1' -File -Recurse)
foreach ($file in $files) {
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Refusing linked source: $($file.FullName)"
    }
    $original = [IO.File]::ReadAllText($file.FullName).Replace("`r`n", "`n")
    $formatted = (Invoke-Formatter -ScriptDefinition $original -Settings $settings).Replace("`r`n", "`n").TrimEnd() + "`n"
    if ((Get-SyntaxContract $original) -cne (Get-SyntaxContract $formatted)) {
        throw "PowerShell formatter changed tokens or AST: $($file.FullName)"
    }
    $repeated = (Invoke-Formatter -ScriptDefinition $formatted -Settings $settings).Replace("`r`n", "`n").TrimEnd() + "`n"
    if ($repeated -cne $formatted) { throw "Unstable formatting: $($file.FullName)" }
    if ($original -cne $formatted) { $changes[$file.FullName] = $formatted }
}
if ($Write) {
    $encoding = [Text.UTF8Encoding]::new($false)
    foreach ($path in $changes.Keys) { [IO.File]::WriteAllText($path, $changes[$path], $encoding) }
} elseif ($changes.Count) {
    $changes.Keys | Sort-Object | ForEach-Object { Write-Host "Formatting required: $_" }
}
Write-Host "PowerShell format: $($files.Count) files; $($changes.Count) changed"
if (!$Write -and $changes.Count) { exit 1 }
