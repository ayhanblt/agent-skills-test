#requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][ValidateSet('T2','T4','T6')][string]$Task, [Parameter(Mandatory)][ValidateSet('A','B','C')][string]$Condition)
$ErrorActionPreference='Stop'
$arguments=@('pilot','--task',$Task,'--condition',$Condition)
& python (Join-Path $PSScriptRoot 'experiment.py') @arguments
if ($LASTEXITCODE -ne 0) { throw 'Research step failed; inspect saved evidence before proceeding.' }
