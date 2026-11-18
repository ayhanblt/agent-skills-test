#requires -Version 7.0
[CmdletBinding()]
param([switch]$DryRun)
$ErrorActionPreference='Stop'
$arguments=@('jev')
if ($DryRun) { $arguments += '--dry-run' }
& python (Join-Path $PSScriptRoot 'experiment.py') @arguments
if ($LASTEXITCODE -ne 0) { throw 'Research step failed; inspect saved evidence before proceeding.' }
