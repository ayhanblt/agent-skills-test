#requires -Version 7.0
param([string]$Root=$PSScriptRoot)
$ErrorActionPreference='Stop'
$matrix=Import-Csv (Join-Path $PSScriptRoot 'matrix.csv')
$attempts=@(Get-ChildItem -Path (Join-Path $Root 'runs/*/evidence/result.json') -File -ErrorAction SilentlyContinue | ForEach-Object {
 $result=Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
 if (!$result.pilot) {
  $result | Add-Member -NotePropertyName result_file -NotePropertyValue ([IO.Path]::GetRelativePath($Root,$_.FullName))
  $result
 }
})
$summary=foreach ($row in $matrix) {
 $found=@($attempts | Where-Object id -eq $row.id)
 if (!$found.Count) {$row; continue}
 foreach ($attempt in $found) {
  $copy=$row | Select-Object *
  $copy.status=$attempt.status
  $copy.reason=$attempt.reason
  $copy | Add-Member -NotePropertyName result_file -NotePropertyValue $attempt.result_file
  $copy
 }
}
$summary | Select-Object id,phase,family,harness,parent,child,condition,rep,status,reason,result_file |
 Export-Csv -LiteralPath (Join-Path $Root 'status.csv') -Encoding utf8
if (!$attempts.Count) { return }
# Bir nesnedeki alanlardan degeri verilen kosulu saglayanlari sayar. null alanlar sayilmaz.
function Count-Where($Object,[scriptblock]$Test) {
 if ($null -eq $Object) { return $null }
 $values=@($Object.PSObject.Properties | ForEach-Object Value | Where-Object { $null -ne $_ })
 if (!$values.Count) { return $null }
 @($values | Where-Object $Test).Count
}
$flat=$attempts | ForEach-Object {
 $columns=[ordered]@{}
 $row=$matrix | Where-Object id -eq $_.id | Select-Object -First 1
 $columns['family']=$row.family
 foreach ($property in $_.PSObject.Properties) {
  $value=$property.Value
  if ($null -ne $value -and $value -isnot [ValueType] -and $value -isnot [string]) {
   $value=ConvertTo-Json -InputObject $value -Compress -Depth 10
  }
  $columns[$property.Name]=$value
 }
 $columns['rules_explicit']=Count-Where $_.rules_received { $_ -eq 2 }
 $columns['rules_any']=Count-Where $_.rules_received { $_ -ge 1 }
 $columns['child_violation_count']=Count-Where $_.child_violations { $_ -eq 'ihlal' }
 $columns['final_violation_count']=Count-Where $_.final_violations { $_ -eq 'ihlal' }
 $columns['seeded_flagged']=Count-Where $_.seeded_caught { $_ -eq 'isaretledi' }
 $columns['seeded_passed']=Count-Where $_.seeded_caught { $_ -eq 'gecirdi' }
 [pscustomobject]$columns
}
$flat | Export-Csv -LiteralPath (Join-Path $Root 'results.csv') -Encoding utf8
# Ozet yalnizca COMPLETED kosulari sayar. Aileler ayri satirlarda kalir.
function Total($Items,[string]$Name) {
 $values=@($Items | ForEach-Object { $_.$Name } | Where-Object { $null -ne $_ })
 if ($values.Count) { ($values | Measure-Object -Sum).Sum } else { $null }
}
$flat | Where-Object status -eq 'COMPLETED' |
 Group-Object phase,family,harness,condition,{ if ($_.phase -eq 'R') {$_.actual_child} else {''} } | ForEach-Object {
  $first=$_.Group[0]
  [pscustomobject][ordered]@{
   phase=$first.phase; family=$first.family; harness=$first.harness; condition=$first.condition
   researcher=if ($first.phase -eq 'R') {$first.actual_child} else {''}
   runs=$_.Count
   rules_explicit_total=Total $_.Group 'rules_explicit'
   rules_any_total=Total $_.Group 'rules_any'
   runs_all_three_explicit=@($_.Group | Where-Object rules_explicit -eq 3).Count
   runs_child_violation=@($_.Group | Where-Object { $_.child_violation_count -gt 0 }).Count
   runs_final_violation=@($_.Group | Where-Object { $_.final_violation_count -gt 0 }).Count
   seeded_flagged_total=Total $_.Group 'seeded_flagged'
   seeded_passed_total=Total $_.Group 'seeded_passed'
  }
 } | Sort-Object phase,family,harness,condition,researcher |
 Export-Csv -LiteralPath (Join-Path $Root 'summary.csv') -Encoding utf8
