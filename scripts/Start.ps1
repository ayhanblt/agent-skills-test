#requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][ValidateRange(1,36)][int]$Run)
$ErrorActionPreference='Stop'
$arguments=@('start','--id',('{0:D2}' -f $Run))
& python (Join-Path $PSScriptRoot 'experiment.py') @arguments
if ($LASTEXITCODE -ne 0) { throw 'Research step failed; inspect saved evidence before proceeding.' }
