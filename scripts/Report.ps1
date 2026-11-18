#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$arguments=@('report')
& python (Join-Path $PSScriptRoot 'experiment.py') @arguments
if ($LASTEXITCODE -ne 0) { throw 'Research step failed; inspect saved evidence before proceeding.' }
