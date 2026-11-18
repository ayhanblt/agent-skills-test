#requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Note)
$ErrorActionPreference='Stop'
$arguments=@('pilot-verify','--note',$Note)
& python (Join-Path $PSScriptRoot 'experiment.py') @arguments
if ($LASTEXITCODE -ne 0) { throw 'Research step failed; inspect saved evidence before proceeding.' }
