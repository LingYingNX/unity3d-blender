$ErrorActionPreference = 'Stop'

$repo = Split-Path -Parent $PSScriptRoot
$blender = if ($env:BLENDER_EXE) { $env:BLENDER_EXE } else { 'D:\blender\blender-5.3.0-beta\blender.exe' }
$tests = @(
    'tests\test_menu_entries_headless.py',
    'tests\test_zipmod_import_headless.py'
)

if (!(Test-Path -Path $blender)) {
    Write-Host "RED: Blender not found at $blender"
    exit 1
}

foreach ($test in $tests) {
    $path = Join-Path $repo $test
    $output = & $blender -b --factory-startup --python $path 2>&1 | Out-String
    if ($output -notmatch 'RESULT: \d+ passed, 0 failed' -and $output -notmatch 'RESULT: 0 failure\(s\)') {
        Write-Host "RED: $test failed"
        Write-Host $output
        exit 1
    }
    Write-Host "GREEN: $test"
}

Write-Host 'GREEN: UnityPy zipmod importer verified'
