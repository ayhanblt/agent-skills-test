#requires -Version 7.0
[CmdletBinding()]
param(
 [Parameter(Mandatory)][int]$Run,
 [Parameter(Mandatory)][string]$Version,
 [string]$ParentId,
 [string]$ChildId,
 [string]$CatalogEvidence,
 [ValidateSet('v1','v2')][string]$OpenCodeSchema = 'v2',
 [string]$Root = $PSScriptRoot,
 [string]$WorkRoot = (Join-Path (Split-Path (Split-Path $PSScriptRoot)) 'ft-workspaces'),
 [string]$BlockedReason,
 [switch]$Pilot
)
$ErrorActionPreference='Stop'
$row = Import-Csv (Join-Path $PSScriptRoot 'matrix.csv') | Where-Object { [int]$_.id -eq $Run }
if (!$row) { throw "Matriste $Run numarali kosu yok." }
if ($Pilot -and $Run -ne 1) { throw 'Pilot yalnizca 01 icin tanimli.' }
if (!$Pilot -and !$BlockedReason) {
 $gatePath = Join-Path $Root 'pilot-01.json'
 if (!(Test-Path -LiteralPath $gatePath)) { throw 'Once 01 pilot kanitini dogrulayin.' }
 $gate = Get-Content -LiteralPath $gatePath -Raw | ConvertFrom-Json
 if ($gate.status -ne 'VERIFIED') { throw '01 pilot durumu VERIFIED olmali.' }
}
$phase = if ($Pilot) {'D'} else {$row.phase}
$needParent = $phase -ne 'R'
$needChild = $phase -ne 'S'
$slug = if ($Pilot) {'pilot-01'} else {$row.id}
$stamp = [guid]::NewGuid().ToString('N').Substring(0,8)
$base = Join-Path $Root "runs/$slug-$stamp"
$evidence = Join-Path $base 'evidence'
# Agent'in calistigi klasor kitin disinda ve notr adli. Kit dosyalari, puanlama olcutu
# ve diger kosular agent'in calisma dizininden gorunmez.
$work = Join-Path $WorkRoot $stamp
$project = Join-Path $work 'app'
[void][IO.Directory]::CreateDirectory($evidence)
function Put([string]$Path,[string]$Value) {
 [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($Path))
 [IO.File]::WriteAllText($Path,$Value)
}
function Read-Kit([string]$Path) { Get-Content -LiteralPath (Join-Path $PSScriptRoot $Path) -Raw -Encoding utf8 }
function Read-Text-Path([string]$Path) { Get-Content -LiteralPath $Path -Raw -Encoding utf8 }
$status = 'BLOCKED'
if (!$BlockedReason) {
 for ($dir = [IO.Path]::GetFullPath($WorkRoot); $dir; $dir = [IO.Path]::GetDirectoryName($dir)) {
  foreach ($doc in 'AGENTS.md','CLAUDE.md') {
   if (Test-Path -LiteralPath (Join-Path $dir $doc)) { throw "Ust klasorde talimat dosyasi var: $(Join-Path $dir $doc)" }
  }
 }
 $prefixed = $row.harness -in @('OpenCode Desktop','Pi')
 if (!$prefixed) {
  if ($needParent -and !$ParentId) {$ParentId=$row.parent}
  if ($needChild -and !$ChildId) {$ChildId=$row.child}
 }
 if (!$needParent) {$ParentId=$null}
 if (!$needChild) {$ChildId=$null}
 $pairs = @()
 if ($needParent) { $pairs += ,@($ParentId,$row.parent) }
 if ($needChild) { $pairs += ,@($ChildId,$row.child) }
 foreach ($pair in $pairs) {
  if ($pair[0] -notmatch '^[A-Za-z0-9][A-Za-z0-9._:/-]*$') { throw 'Katalogdaki tam kimligi girin.' }
  if ($prefixed -and $pair[0] -notmatch '/') { throw 'provider/model gerekli.' }
  if (($pair[0] -split '/')[-1] -cne $pair[1] -and !$CatalogEvidence) { throw 'Kimlik farkli. Resmi model esleme kaniti gerekli.' }
 }
 if ($prefixed -and !$CatalogEvidence) { throw 'Bu harness icin katalog kanit dosyasi gerekli.' }
 if ($CatalogEvidence) {
  $catalog = Get-Content -LiteralPath $CatalogEvidence -Raw
  foreach ($pair in $pairs) {
   if (!$catalog.Contains($pair[0])) { throw "Kimlik katalog kanitinda bulunamadi: $($pair[0])" }
  }
  Copy-Item -LiteralPath $CatalogEvidence -Destination (Join-Path $evidence 'catalog.txt')
 }
 $role = (Read-Kit 'researcher.txt').Trim()
 # D: notr proje talimati. R: researcher rolu ana modelin talimati olur. S: researcher'siz notr talimat.
 foreach ($doc in 'AGENTS.md','CLAUDE.md') {
  $text = switch ($phase) { 'D' {Read-Kit $doc} 'R' {$role} 'S' {Read-Kit 'AGENTS.S.md'} }
  Put (Join-Path $project $doc) $text
 }
 $main = if ($phase -eq 'R') {$ChildId} else {$ParentId}
 $description = 'Birincil kaynaklarla teknik arastirma yapar.'
 switch ($row.harness) {
  'OpenCode Desktop' {
   $schema = @{'$schema'='https://opencode.ai/config.json';model=$main}
   if ($phase -eq 'D') {
    $key = if ($OpenCodeSchema -eq 'v1') {'agent'} else {'agents'}
    $promptKey = if ($OpenCodeSchema -eq 'v1') {'prompt'} else {'system'}
    $schema[$key] = @{researcher=@{description=$description;mode='subagent';model=$ChildId}}
    $schema[$key].researcher[$promptKey]=$role
   }
   Put (Join-Path $project 'opencode.json') ($schema | ConvertTo-Json -Depth 6)
  }
  'Claude Code' {
   if ($phase -eq 'D') {
    Put (Join-Path $project '.claude/agents/researcher.md') (@(
     '---','name: researcher',"description: $description","model: $ChildId",
     'tools: WebSearch, WebFetch','---',$role
    ) -join [Environment]::NewLine)
   }
  }
  'Codex' {
   Put (Join-Path $project '.codex/config.toml') ('model = "'+$main+'"' + [Environment]::NewLine + 'web_search = "live"')
   if ($phase -eq 'D') {
    $config = @{
     name='researcher'; description=$description; model=$ChildId; developer_instructions=$role
    }
    Put (Join-Path $project '.codex/agents/researcher.toml') (($config.GetEnumerator() | ForEach-Object {
     $_.Key+' = '+($_.Value | ConvertTo-Json -Compress)
    }) -join [Environment]::NewLine)
   }
  }
  'Pi' {
   if ($phase -eq 'D') {
    $config = @{model=$ChildId;instructions=$role;description=$description} | ConvertTo-Json -Compress
    # Pi 1.x proje icindeki .pi klasorunu guven onayina baglar. Eklenti proje disinda durur ve -e ile yuklenir.
    Put (Join-Path $work 'pi-researcher.ts') ((Read-Kit 'pi/researcher.ts').Replace('/* BENCHMARK_CONFIG */ null',$config))
    Put (Join-Path $work 'pi-primary-sources.ts') (Read-Kit 'pi/primary-sources.ts')
    Put (Join-Path $evidence 'config-pi/pi-researcher.ts') (Read-Text-Path (Join-Path $work 'pi-researcher.ts'))
    Put (Join-Path $evidence 'config-pi/pi-primary-sources.ts') (Read-Kit 'pi/primary-sources.ts')
    [void][IO.Directory]::CreateDirectory((Join-Path $work 'log'))
   }
  }
 }
 if ($Pilot) {
  Put (Join-Path $evidence 'pilot.txt') (Read-Kit 'prompts/pilot.txt')
 } elseif ($phase -eq 'R') {
  Put (Join-Path $evidence 'task.txt') (Read-Kit "prompts/$($row.condition).txt")
 } else {
  foreach ($n in '01','02','03','04','05') { Put (Join-Path $evidence "$n.txt") (Read-Kit "prompts/$n.txt") }
  Put (Join-Path $evidence '06.txt') (Read-Kit "prompts/$($row.condition).txt")
 }
 Copy-Item -LiteralPath $project -Recurse -Destination (Join-Path $evidence 'config')
 $status='CONFIGURED'
}
$result = Read-Kit 'templates/result.json' | ConvertFrom-Json
$result.id=$row.id
$result.phase=$phase
$result.rep=$row.rep
$result.status=$status
$result.reason=$BlockedReason
$result.harness=$row.harness
$result.harness_version=$Version
$result.condition=$row.condition
$result.requested_parent=$ParentId
$result.requested_child=$ChildId
$result.project_dir=if ($status -eq 'CONFIGURED') {$project} else {$null}
$result | Add-Member -NotePropertyName pilot -NotePropertyValue ([bool]$Pilot)
$result | Add-Member -NotePropertyName planned_parent -NotePropertyValue $row.parent
$result | Add-Member -NotePropertyName planned_child -NotePropertyValue $row.child
Put (Join-Path $evidence 'result.json') ($result | ConvertTo-Json -Depth 10)
if ($status -eq 'CONFIGURED') {
 Write-Host "Proje klasoru  : $project"
 Write-Host "Gonderilecekler: $evidence"
}
$base
