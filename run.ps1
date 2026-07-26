param(
    [int]$InferenceWorkers = -1
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($InferenceWorkers -ge 0) {
    $env:INFERENCE_WORKERS = "$InferenceWorkers"
    Write-Host "[run.ps1] INFERENCE_WORKERS=$env:INFERENCE_WORKERS"
} elseif ($env:INFERENCE_WORKERS) {
    Write-Host "[run.ps1] INFERENCE_WORKERS=$env:INFERENCE_WORKERS"
} else {
    Write-Host "[run.ps1] INFERENCE_WORKERS not set — app defaults to inline mode."
    Write-Host "           Example: ./run.ps1 -InferenceWorkers 2"
    Write-Host "           Or: `$env:INFERENCE_WORKERS=2; ./run.bat"
}

& "$PSScriptRoot\run.bat"
