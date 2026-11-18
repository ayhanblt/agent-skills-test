#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
& python (Join-Path $PSScriptRoot 'selfcheck.py')
if ($LASTEXITCODE -ne 0) { throw 'Test self-check failed' }
& python -m unittest discover -s (Join-Path $PSScriptRoot '../selfcheck') -p 'test_*.py'
if ($LASTEXITCODE -ne 0) { throw 'Research step failed; inspect saved evidence before proceeding.' }
