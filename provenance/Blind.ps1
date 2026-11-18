#requires -Version 7.0
# Puanlanacak metinleri kosul, model ve harness etiketi olmadan scoring klasorune yazar.
# key.csv kod ile kosu eslesmesini tutar. Puanlar verilene kadar acilmaz.
param([string]$Root=$PSScriptRoot)
$ErrorActionPreference='Stop'
$out=Join-Path $Root 'scoring'
[void][IO.Directory]::CreateDirectory($out)
$keyPath=Join-Path $out 'key.csv'
$key=@(if (Test-Path -LiteralPath $keyPath) { Import-Csv -LiteralPath $keyPath })
# key.csv dosya yollarini kite gore goreli tutar; depo baska bir klasore kopyalansa da calisir.
$new=Get-ChildItem -Path (Join-Path $Root 'runs/*/evidence/result.json') -File -ErrorAction SilentlyContinue | ForEach-Object {
 $result=Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
 $rel=[IO.Path]::GetRelativePath($Root,$_.FullName)
 if ($result.pilot -or $key.result_file -contains $rel) { return }
 if ($result.status -in @('FAILED','BLOCKED')) { return }
 if (!$result.child_output_raw -and !$result.parent_final_raw) { return }
 [pscustomobject]@{result=$result;file=$rel}
} | Sort-Object { Get-Random }
foreach ($item in $new) {
 do { $code=[guid]::NewGuid().ToString('N').Substring(0,6) } while ($key.code -contains $code)
 $r=$item.result
 $parts=@("# $code",'')
 if ($r.phase -ne 'S') {
  # Child'in ilk baglami harness'in kendi ekleriyle gelir ve harness'i ele verir. Kor dosyada yalnizca
  # parent'in yazdigi gorev metni (Faz R'de sabit gorev) durur. Harness eklerindeki kurallar
  # (orn. Codex'in devraldigi gecmis) kor olmayan ayri adimda child_auto_context_observed alanindan puanlanir.
  $task=[string]$r.parent_child_raw
  if ($task.StartsWith('OKUNAMIYOR')) { $task='[Gorev metni kayitta okunamiyor. rules_received bu dosyadan puanlanmaz, null yazin.]' }
  $parts+=@('## Researcher''in aldigi gorev','',$task,'')
  $parts+=@('## Researcher ciktisi','',[string]$r.child_output_raw,'')
 }
 if ($r.phase -ne 'R') { $parts+=@('## Parent nihai cevabi','',[string]$r.parent_final_raw,'') }
 [IO.File]::WriteAllText((Join-Path $out "$code.md"),($parts -join [Environment]::NewLine))
 $key+=[pscustomobject]@{code=$code;id=$r.id;phase=$r.phase;result_file=$item.file}
}
$key | Export-Csv -LiteralPath $keyPath -Encoding utf8
"$(@($new).Count) yeni metin $out klasorune yazildi."
