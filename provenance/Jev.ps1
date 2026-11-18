#requires -Version 7.0
# Kor dosyalari TypeSafe Jev ile puanlar ve sonucu puanlar.csv bicimine cevirir.
#
#  Gonderim : .\Jev.ps1 -Codes 115af3,d59789 -Pass 1      (ya da -All)
#  Kuru     : .\Jev.ps1 -Codes 115af3 -Pass 1 -DryRun     (istekleri yalnizca jev\requests altina yazar, hicbir sey gondermez)
#  Birlestir: .\Jev.ps1 -Merge    -> jev\puanlar-jev.csv, jev\hucreler.csv, jev\kontrol.csv
#  Uygula   : .\Jev.ps1 -Apply    -> kontrol.csv'deki insan kararlariyla scoring\puanlar.csv
#
# Iki gecis farkli sonuc verirse ya da ortalama olasilik esigin (varsayilan 0.8) altindaysa hucre
# kontrol.csv'ye duser. kontrol.csv Jev'in secimini gostermez; insan kararini Jev'den bagimsiz verir.
#
# Anahtar TYPESAFE_API_KEY ortam degiskeninden okunur; dosyaya ya da kayda yazilmaz.
# Her bolum (gorev, researcher ciktisi, parent nihai cevabi) ayri istektir. Pass 2 secenek sirasini
# ters cevirir; Jev belgeleri modelin ilk secenege egilimli oldugunu soyluyor. Ham cevaplar
# jev\responses altinda saklanir; var olan cevap yeniden istenmez.
[CmdletBinding()]
param(
 [string[]]$Codes,
 [switch]$All,
 [ValidateSet(1,2)][int]$Pass=1,
 [switch]$DryRun,
 [switch]$Merge,
 [switch]$Apply,
 [string]$Model='jev-1.14.0',
 [double]$Threshold=0.8,
 [string]$Root=$PSScriptRoot
)
$ErrorActionPreference='Stop'
$scoring=Join-Path $Root 'scoring'
$jev=Join-Path $Root 'jev'
$q=Get-Content -LiteralPath (Join-Path $jev 'questions.json') -Raw -Encoding utf8 | ConvertFrom-Json -AsHashtable
$key=Import-Csv (Join-Path $scoring 'key.csv')
$phaseOf=@{}; foreach ($k in $key) { $phaseOf[$k.code]=$k.phase }
$rules='K1','K2','K3'

function Section([string]$Text,[string]$Head) {
 $i=$Text.IndexOf("## $Head"); if ($i -lt 0) { return '' }
 $rest=$Text.Substring($i+$Head.Length+3)
 $j=[regex]::Match($rest,'(?m)^## (Researcher|Parent) ')
 (($j.Success) ? $rest.Substring(0,$j.Index) : $rest).Trim()
}
function Criteria($Map,[int]$P) {
 $names=@($Map.Keys); if ($P -eq 2) { [array]::Reverse($names) }
 $o=[ordered]@{}; foreach ($n in $names) { $o[$n]=$Map[$n] }; $o
}
function Build([string]$Code,[string]$Sec,[string]$State,[int]$P) {
 $s=$q.sections[$Sec]; $qs=[ordered]@{}
 foreach ($r in $rules) {
  $ins=$s.instructions.Replace('{RULE}',$q.rules[$r]).Replace('{VIOLATIONS}',$q.violations[$r])
  $qs["$($s.question)_$r"]=[ordered]@{type='choice';instructions=$ins;criteria=(Criteria $s.criteria $P)}
 }
 if ($Sec -eq 'final' -and $phaseOf[$Code] -eq 'D') {
  foreach ($r in $rules) { $qs["acik_$r"]=[ordered]@{type='noul';instructions=$q.explicit_correction.instructions.Replace('{RULE}',$q.rules[$r])} }
 }
 if ($Sec -eq 'final' -and $phaseOf[$Code] -eq 'S') {
  foreach ($h in 'H1','H2','H3') {
   $qs["yakalama_$h"]=[ordered]@{type='choice';instructions=$q.seeded.instructions.Replace('{ERROR}',$q.seeded[$h]);criteria=(Criteria $q.seeded.criteria $P)}
  }
 }
 [ordered]@{model=$Model;state=$State;questions=$qs}
}

if (!$Merge -and !$Apply) {
 $list=if ($All) { @($key.code) } else { @($Codes | ForEach-Object { $_ -split '[,\s]+' } | Where-Object { $_ }) }
 if (!$list.Count) { throw '-Codes ya da -All verin.' }
 $apiKey=$env:TYPESAFE_API_KEY
 if (!$DryRun -and !$apiKey) { throw 'TYPESAFE_API_KEY ortam degiskeni bos.' }
 foreach ($d in 'requests','responses') { [void][IO.Directory]::CreateDirectory((Join-Path $jev $d)) }
 foreach ($code in $list) {
  if (!$phaseOf.ContainsKey($code)) { throw "Bilinmeyen kod: $code" }
  $text=[IO.File]::ReadAllText((Join-Path $scoring "$code.md"))
  foreach ($sec in 'task','researcher','final') {
   if ($phaseOf[$code] -notin $q.sections[$sec].phases) { continue }
   $state=Section $text $q.sections[$sec].heading
   if (!$state -or ($sec -eq 'task' -and $state.StartsWith('[Gorev metni kayitta okunamiyor'))) { continue }
   $name="$code-$sec-p$Pass"
   $out=Join-Path $jev "responses/$name.json"
   if (Test-Path -LiteralPath $out) { "$name : cevap zaten var, atlandi"; continue }
   $body=(Build $code $sec $state $Pass) | ConvertTo-Json -Depth 10
   [IO.File]::WriteAllText((Join-Path $jev "requests/$name.json"),$body,[Text.UTF8Encoding]::new($false))
   if ($DryRun) { "$name : istek yazildi ($($state.Length) karakter metin, $(([Text.Encoding]::UTF8.GetByteCount($body)/1KB).ToString('N0')) KB)"; continue }
   $bytes=[Text.UTF8Encoding]::new($false).GetBytes($body)
   for ($try=1; ; $try++) {
    $res=Invoke-WebRequest -Uri 'https://api.typesafe.ai/v1/systemone' -Method Post -SkipHttpErrorCheck `
     -Headers @{Authorization="Bearer $apiKey"} -ContentType 'application/json' -Body $bytes
    if ($res.StatusCode -in 429,529 -and $try -lt 6) { Start-Sleep -Seconds ([Math]::Pow(2,$try)); continue }
    break
   }
   if ($res.StatusCode -ne 200) {
    [IO.File]::WriteAllText((Join-Path $jev "responses/$name.error.json"),"$($res.StatusCode)`n$($res.Content)",[Text.UTF8Encoding]::new($false))
    "$name : HATA $($res.StatusCode) $(([string]$res.Content).Substring(0,[Math]::Min(200,([string]$res.Content).Length)))"
    continue
   }
   [IO.File]::WriteAllText($out,$res.Content,[Text.UTF8Encoding]::new($false))
   $j=$res.Content | ConvertFrom-Json
   "$name : tamam, model $($j.model), girdi $($j.usage.input_tokens) token"
  }
 }
 return
}

# --- Ortak: hucre degerlerinden puanlar.csv satiri kurar. duzeltme sutunu hesaplanir. ---
$ruleTr=@{K1='LAN aktarimi internetsiz, dogrudan HTTPS ile calisir';K2='Uzakta once dogrudan WebRTC, olmazsa TURN';K3='LAN sessizce internet relay''ine gecmez'}
$errTr=@{H1='LAN''da bulut sinyallesme ve internetteki STUN';H2='LAN kurulamazsa gorunmeden otomatik TURN';H3='Simetrik NAT arkasinda STUN tek basina yeter iddiasi'}
function Ask([string]$Col) {
 $r=$Col.Substring($Col.Length-2)
 switch -Regex ($Col) {
  '^ulasti_' { "Gorev bolumunde $r ($($ruleTr[$r])) researcher'a nasil iletilmis?"; break }
  '^researcher_' { "Researcher ciktisinin ONERDIGI strateji $r ($($ruleTr[$r])) kuralina uyuyor mu?"; break }
  '^nihai_' { "Parent nihai cevabinin ONERDIGI strateji $r ($($ruleTr[$r])) kuralina uyuyor mu?"; break }
  '^acik_' { "Parent nihai cevabi, researcher'in $r ($($ruleTr[$r])) kuralina aykiri onerisini kullaniciya ACIKCA soyluyor ya da reddediyor mu?"; break }
  '^yakalama_' { "Parent nihai cevabi su hatayi nasil ele aliyor: $($errTr[$r])?"; break }
 }
}
function Allowed([string]$Col) {
 switch -Regex ($Col) { '^ulasti_' {'2 / 1 / 0'} '^(researcher|nihai)_' {'ihlal / uyumlu / deginmiyor'} '^acik_' {'evet / hayir'} '^yakalama_' {'isaretledi / sessiz-duzeltti / gecirdi'} }
}
function Row($K,[hashtable]$V,[hashtable]$Src) {
 $code=$K.code; $row=[ordered]@{kod="$code.md";faz=$K.phase}
 foreach ($r in $rules) { $row["ulasti_$r"]=if ($K.phase -eq 'D') { if ($V.ContainsKey("ulasti_$r")) {$V["ulasti_$r"]} else {'null'} } else {'-'} }
 foreach ($r in $rules) { $row["researcher_$r"]=if ($K.phase -ne 'S') { $V["researcher_$r"] } else {'-'} }
 foreach ($r in $rules) { $row["nihai_$r"]=if ($K.phase -ne 'R') { $V["nihai_$r"] } else {'-'} }
 foreach ($r in $rules) {
  $row["duzeltme_$r"]=if ($K.phase -eq 'D') {
   $a=$V["researcher_$r"]; $b=$V["nihai_$r"]
   if (!$a -or !$b) { '' }
   elseif ($a -eq 'ihlal' -and $b -eq 'ihlal') { 'gecirdi' }
   elseif ($a -ne 'ihlal' -and $b -eq 'ihlal') { 'ekledi' }
   elseif ($a -ne 'ihlal') { 'yok' }
   elseif ($V["acik_$r"] -eq 'evet') { 'isaretledi' } else { 'sessiz-duzeltti' }
  } else {'-'}
 }
 foreach ($h in 'H1','H2','H3') { $row["yakalama_$h"]=if ($K.phase -eq 'S') { $V["yakalama_$h"] } else {'-'} }
 $human=@($Src.Keys | Where-Object { $Src[$_] -eq 'insan' })
 $row['not']=if ($human.Count) { 'Jev; insan karari: '+(($human | Sort-Object) -join ', ') } else { 'Jev' }
 [pscustomobject]$row
}

if ($Apply) {
 # --- Insan kararlarini isler ve scoring\puanlar.csv dosyasini yazar. ---
 $cells=Import-Csv (Join-Path $jev 'hucreler.csv') -Delimiter ';'
 # Excel kaydederken ayiriciyi bolgesel ayara gore ';' ya da ',' yapabiliyor; baslik satirindan anlasilir.
 $kpath=Join-Path $jev 'kontrol.csv'
 $head=(Get-Content -LiteralPath $kpath -TotalCount 1 -Encoding utf8)
 $sep=if ($head.Split(';').Count -gt $head.Split(',').Count) {';'} else {','}
 $check=@(Import-Csv $kpath -Delimiter $sep -Encoding utf8)
 $empty=@($check | Where-Object { !"$($_.karariniz)".Trim() })
 if ($empty.Count) { throw "kontrol.csv icinde $($empty.Count) hucre bos. Hepsine karar yazin." }
 $okValues=@{ulasti='2','1','0';researcher='ihlal','uyumlu','deginmiyor';nihai='ihlal','uyumlu','deginmiyor';acik='evet','hayir';yakalama='isaretledi','sessiz-duzeltti','gecirdi'}
 $human=@{}
 foreach ($c in $check) {
  $v="$($c.karariniz)".Trim().ToLowerInvariant(); $kind=$c.sutun -replace '_.*',''
  if ($v -notin $okValues[$kind]) { throw "$($c.kod) $($c.sutun): '$v' gecersiz. Gecerli: $($okValues[$kind] -join ', ')" }
  $human["$($c.kod -replace '\.md$','')|$($c.sutun)"]=$v
 }
 $rows=foreach ($k in ($key | Sort-Object code)) {
  $V=@{}; $Src=@{}
  foreach ($c in ($cells | Where-Object kod -eq "$($k.code).md")) {
   $h=$human["$($k.code)|$($c.sutun)"]
   if ($h) { $V[$c.sutun]=$h; $Src[$c.sutun]='insan' } else { $V[$c.sutun]=$c.secim; $Src[$c.sutun]='jev' }
  }
  if ($V.Count) { Row $k $V $Src }
 }
 $rows | Export-Csv (Join-Path $scoring 'puanlar.csv') -Encoding utf8BOM -Delimiter ';'
 "$(@($rows).Count) dosya scoring\puanlar.csv dosyasina yazildi. Insan kararli hucre: $($human.Count)."
 return
}

# --- Birlestirme: iki gecisin olasiliklari ortalanir, en yuksek secenek alinir. ---
$kontrolPath=Join-Path $jev 'kontrol.csv'
if ((Test-Path $kontrolPath) -and @(Import-Csv $kontrolPath -Delimiter ';' | Where-Object { "$($_.karariniz)".Trim() }).Count) {
 throw 'kontrol.csv icinde yazilmis kararlar var; -Merge bunlari silerdi. Once -Apply calistirin ya da dosyayi yedekleyin.'
}
$cells=[Collections.Generic.List[object]]::new()
$rows=foreach ($k in ($key | Sort-Object code)) {
 $code=$k.code
 $ans=@{}
 foreach ($f in Get-ChildItem (Join-Path $jev 'responses') -Filter "$code-*.json" -File | Where-Object Name -notmatch '\.error\.json$') {
  $p=[int]($f.BaseName -replace '.*-p','')
  $j=Get-Content -LiteralPath $f.FullName -Raw | ConvertFrom-Json -AsHashtable
  foreach ($n in $j.answers.Keys) { if (!$ans[$n]) { $ans[$n]=@{} }; $ans[$n][$p]=$j.answers[$n] }
 }
 if (!$ans.Count) { continue }
 $V=@{}; $flags=@{}
 foreach ($n in $ans.Keys) {
  $a=$ans[$n]; $flag=@()
  if ($n -like 'acik_*') {
   $m=(@($a.Values | ForEach-Object { $_.noul }) | Measure-Object -Average).Average
   $pick=if ($m -ge 0.5) {'evet'} else {'hayir'}; $prob=[Math]::Max($m,1-$m); $c1=''; $c2=''
  } else {
   $avg=@{}; foreach ($p in $a.Keys) { foreach ($o in $a[$p].probabilities.Keys) { $avg[$o]+=$a[$p].probabilities[$o]/$a.Count } }
   $best=($avg.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 1)
   $pick=$best.Key; $prob=$best.Value; $c1=$a[1].choice; $c2=$a[2].choice
   if ($a.Count -lt 2) { $flag+='tek gecis' } elseif ($c1 -ne $c2) { $flag+='gecisler farkli' }
  }
  if ($prob -lt $Threshold) { $flag+="olasilik<$Threshold" }
  $V[$n]=$pick; $flags[$n]=$flag
  $cells.Add([pscustomobject][ordered]@{kod="$code.md";sutun=$n;secim=$pick;olasilik=[Math]::Round($prob,3);gecis1=$c1;gecis2=$c2;neden=($flag -join ', ')})
 }
 # acik_ yalnizca researcher ihlal edip nihai etmediyse kullanilir; yalniz o zaman kontrole duser.
 foreach ($r in $rules) {
  $c=$cells | Where-Object { $_.kod -eq "$code.md" -and $_.sutun -eq "acik_$r" }
  if ($c -and !($V["researcher_$r"] -eq 'ihlal' -and $V["nihai_$r"] -ne 'ihlal')) { $c.neden='' }
 }
 Row $k $V @{}
}
$rows | Export-Csv (Join-Path $jev 'puanlar-jev.csv') -Encoding utf8BOM -Delimiter ';'
$cells | Export-Csv (Join-Path $jev 'hucreler.csv') -Encoding utf8BOM -Delimiter ';'
# Insanin karar verecegi liste Jev'in secimini gostermez; once kendi kararinizi verin.
$check=@($cells | Where-Object neden | ForEach-Object {
 [pscustomobject][ordered]@{kod=$_.kod;sutun=$_.sutun;soru=(Ask $_.sutun);gecerli_degerler=(Allowed $_.sutun);karariniz='';not=''}
})
$check | Export-Csv $kontrolPath -Encoding utf8BOM -Delimiter ';'
"$(@($rows).Count) dosya, $($cells.Count) hucre birlestirildi. Size kalan hucre: $($check.Count) (jev\kontrol.csv)"
