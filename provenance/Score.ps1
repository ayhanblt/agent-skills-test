#requires -Version 7.0
# Puanlamayi bitirir: scoring\puanlar.csv (Jev + insan) ve scoring\iddialar.csv (Codex) degerlerini
# key.csv ile kosulara esler, result.json dosyalarina yazar ve durumu COMPLETED yapar.
# key.csv ancak puanlama bittikten sonra okunur.
param([string]$Root=$PSScriptRoot)
$ErrorActionPreference='Stop'
$dir=Join-Path $Root 'scoring'
function Read-Sep([string]$Path) {
 $h=Get-Content -LiteralPath $Path -TotalCount 1 -Encoding utf8
 $s=if ($h.Split(';').Count -gt $h.Split(',').Count) {';'} else {','}
 Import-Csv -LiteralPath $Path -Delimiter $s -Encoding utf8
}
$key=Import-Csv (Join-Path $dir 'key.csv')
$scores=Read-Sep (Join-Path $dir 'puanlar.csv')
$claims=Read-Sep (Join-Path $dir 'iddialar.csv')
$jevModel=((Get-ChildItem (Join-Path $Root 'jev/responses') -Filter *.json | Where-Object Name -notmatch 'error' | Select-Object -First 1 | Get-Content -Raw | ConvertFrom-Json).model)
function V([string]$x) { $x="$x".Trim(); if (!$x -or $x -eq '-' -or $x -eq 'null') { $null } elseif ($x -match '^\d$') { [int]$x } else { $x } }
$n=0
foreach ($k in $key) {
 $path=Join-Path $Root $k.result_file
 $r=Get-Content -LiteralPath $path -Raw -Encoding utf8 | ConvertFrom-Json
 $s=$scores | Where-Object { ($_.kod -replace '\.md$','') -eq $k.code }
 if (!$s) { throw "puanlar.csv icinde $($k.code) yok" }
 if ($k.phase -eq 'D') {
  $r.rules_received.k1_lan_https_offline=V $s.ulasti_K1
  $r.rules_received.k2_remote_direct_then_turn=V $s.ulasti_K2
  $r.rules_received.k3_no_silent_relay=V $s.ulasti_K3
  $r.parent_correction.k1=V $s.duzeltme_K1; $r.parent_correction.k2=V $s.duzeltme_K2; $r.parent_correction.k3=V $s.duzeltme_K3
 }
 if ($k.phase -ne 'S') {
  $r.child_violations.k1_lan_internet_dependency=V $s.researcher_K1
  $r.child_violations.k2_remote_order=V $s.researcher_K2
  $r.child_violations.k3_silent_relay=V $s.researcher_K3
 }
 if ($k.phase -ne 'R') {
  $r.final_violations.k1_lan_internet_dependency=V $s.nihai_K1
  $r.final_violations.k2_remote_order=V $s.nihai_K2
  $r.final_violations.k3_silent_relay=V $s.nihai_K3
 }
 if ($k.phase -eq 'S') {
  $r.seeded_caught.h1_lan_cloud_dependency=V $s.yakalama_H1
  $r.seeded_caught.h2_silent_relay=V $s.yakalama_H2
  $r.seeded_caught.h3_stun_symmetric_nat=V $s.yakalama_H3
 }
 $notes=@()
 if ($k.phase -ne 'S') {
  $mine=@($claims | Where-Object { ($_.kod -replace '\.md$','') -eq $k.code -and "$($_.karar)".Trim() })
  $r.claims_checked=@($mine | ForEach-Object { [ordered]@{claim=$_.iddia;url=$_.url;verdict="$($_.karar)".Trim();evidence=$_.gerekce} })
  $r.source_accuracy=if ($mine.Count) { "$(@($mine | Where-Object { "$($_.karar)".Trim() -eq 'destekliyor' }).Count)/$($mine.Count)" } else { $null }
  if ($mine.Count -lt 5) { $notes+="Kaynak gosterilen iddia sayisi $($mine.Count)." }
 }
 # Codex alt agent'i parent konusmasini devraliyor; ilk mesajdaki kurallar oradan ulasir (RUBRIC 1. bolum).
 if ($k.phase -eq 'D' -and "$($r.child_auto_context_observed)" -match 'parent gecmisinden \d+ kullanici mesaji devraldi') {
  $r | Add-Member -NotePropertyName rules_received_auto_context -NotePropertyValue ([ordered]@{k1_lan_https_offline=2;k2_remote_direct_then_turn=2;k3_no_silent_relay=2;source='Child, kurallarin acikca yazildigi ilk kullanici mesajini devralinan parent gecmisinde aldi (child_auto_context_observed).'}) -Force
 }
 if ($s.not -match 'insan karari: (.+)$') { $notes+="Insan karari verilen hucreler: $($Matches[1])." }
 $r.scorer="Kural puanlari: TypeSafe $jevModel (iki gecis, secenek sirasi ters). Belirsiz hucreler: insan. Kaynak kontrolu: Codex Desktop, GPT-6.1 Sol."
 $r.second_scorer=$null
 $r.scoring_notes=(@($r.scoring_notes)+$notes | Where-Object { $_ }) -join ' '
 $r.status='COMPLETED'
 [IO.File]::WriteAllText($path,($r | ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
 $n++
}
"$n result.json dosyasi puanlandi ve COMPLETED yapildi."
