#requires -Version 7.0
[CmdletBinding(DefaultParameterSetName='Files')]
param(
 [Parameter(Mandatory)][string]$RunDir,
 [Parameter(Mandatory,ParameterSetName='Files')][string]$ParentFile,
 [Parameter(ParameterSetName='Files')][string[]]$ChildFiles,
 [Parameter(Mandatory,ParameterSetName='OpenCode')][string]$ParentSession,
 [Parameter(ParameterSetName='OpenCode')][string[]]$ChildSessions,
 [Parameter(Mandatory,ParameterSetName='OpenCode')][string]$OpenCodeCli,
 [Parameter(ParameterSetName='OpenCode')][switch]$Legacy
)
$ErrorActionPreference='Stop'
# CLI ciktisi UTF-8. Konsol kod sayfasiyla okunursa Turkce karakterler bozulur.
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$OutputEncoding=[Text.UTF8Encoding]::new($false)
$base=(Resolve-Path -LiteralPath $RunDir).Path
$output=Join-Path $base ('evidence/capture-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($output)
function Capture([string]$Name,[string]$InputRef) {
 $item = [ordered]@{role=$Name;source=$InputRef;file=$null;sha256=$null;error=$null}
 try {
  if ($PSCmdlet.ParameterSetName -eq 'OpenCode') {
   if ($InputRef -notmatch '^ses_[A-Za-z0-9_-]+$') {throw 'Invalid session ID'}
   $dest=Join-Path $output "$Name.json"
   $argsList=if ($Legacy) {@('export',$InputRef)} else {@('session','export',$InputRef)}
   & $OpenCodeCli @argsList 2> (Join-Path $output "$Name.stderr.txt") | Set-Content -LiteralPath $dest -Encoding utf8
   if ($LASTEXITCODE -ne 0) {throw "Export exit code $LASTEXITCODE"}
  } else {
   $source=Get-Item -LiteralPath $InputRef
   if ($source.PSIsContainer -or $source.Length -eq 0 -or $source.Extension -notin @('.json','.jsonl')) {throw 'Expected nonempty JSON/JSONL'}
   $dest=Join-Path $output ($Name+$source.Extension)
   Copy-Item -LiteralPath $source.FullName -Destination $dest
  }
  $item.file=Split-Path -Leaf $dest
  $item.sha256=(Get-FileHash -LiteralPath $dest).Hash
  if ($dest.EndsWith('.json')) {
   $null=Get-Content -LiteralPath $dest -Raw | ConvertFrom-Json
  } else {
   Get-Content -LiteralPath $dest | Where-Object { $_.Trim() } | ForEach-Object { $null=$_ | ConvertFrom-Json }
  }
 } catch { $item.error=$_.Exception.Message }
 [pscustomobject]$item
}
if ($PSCmdlet.ParameterSetName -eq 'OpenCode') {
 $projectDir=(Get-Content -LiteralPath (Join-Path $base 'evidence/result.json') -Raw | ConvertFrom-Json).project_dir
 Push-Location -LiteralPath $projectDir
 try {
  $records = @(Capture parent $ParentSession
  $i=0
  foreach ($id in $ChildSessions) { Capture "child-$((++$i))" $id })
 } finally { Pop-Location }
} else {
 $records = @(Capture parent $ParentFile
 $i=0
 foreach ($file in $ChildFiles) { Capture "child-$((++$i))" $file })
}
@{captured_utc=[DateTime]::UtcNow.ToString('o');records=$records;complete_pair=($records.Count -ge 2 -and !($records | Where-Object error))} |
 ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $output 'capture.json') -Encoding utf8
$output
