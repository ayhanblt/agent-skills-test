#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$arguments=@('preflight')
& python (Join-Path $PSScriptRoot 'experiment.py') @arguments
if ($LASTEXITCODE -ne 0) { throw 'Research step failed; inspect saved evidence before proceeding.' }
