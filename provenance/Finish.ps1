#requires -Version 7.0
# Bir kosunun kayitlarini bulur, evidence altina kopyalar ve result.json ham alanlarini doldurur.
# Puan alanlarina dokunmaz. Kullanim: .\Finish.ps1 -Run 2
[CmdletBinding()]
param(
 [Parameter(Mandatory)][int]$Run,
 [string]$Root=$PSScriptRoot
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$OutputEncoding=[Text.UTF8Encoding]::new($false)

$id='{0:d2}' -f $Run
$runDir=Get-ChildItem -Path (Join-Path $Root 'runs') -Directory -Filter "$id-*" -ErrorAction SilentlyContinue |
 Sort-Object CreationTime -Descending | Select-Object -First 1
if (!$runDir) { throw "Kosu $id icin klasor yok. Once Prepare.ps1 calistirin." }
$evidence=Join-Path $runDir.FullName 'evidence'
$resultPath=Join-Path $evidence 'result.json'
$r=Get-Content -LiteralPath $resultPath -Raw -Encoding utf8 | ConvertFrom-Json
if ($r.status -eq 'BLOCKED') { throw "Kosu $id BLOCKED olarak kayitli." }
if ($r.status -eq 'COMPLETED') { throw "Kosu $id zaten puanlanmis (COMPLETED)." }
$project=$r.project_dir
$work=Split-Path $project
$capName='capture-'+[guid]::NewGuid().ToString('N')
$cap=Join-Path $evidence $capName
[void][IO.Directory]::CreateDirectory($cap)
$warnings=[Collections.Generic.List[string]]::new()
$records=[Collections.Generic.List[object]]::new()

# Harness acikken kayit dosyasi yazmaya kilitli olabilir. Paylasimli okuma bunu asar.
function Open-Shared([string]$Path) { [IO.FileStream]::new($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]'ReadWrite,Delete') }
function Read-Text([string]$Path) {
 $reader=[IO.StreamReader]::new((Open-Shared $Path),[Text.Encoding]::UTF8)
 try { $reader.ReadToEnd() } finally { $reader.Dispose() }
}
function Read-JsonLines([string]$Path) {
 foreach ($line in ((Read-Text $Path) -split "`r?`n")) {
  if (!$line.Trim().StartsWith('{')) { continue }
  try { $line | ConvertFrom-Json -Depth 64 } catch { }
 }
}
function Save([string]$Role,[string]$Source) {
 $dest=Join-Path $cap ($Role+[IO.Path]::GetExtension($Source))
 $in=Open-Shared $Source
 try { $out=[IO.File]::Create($dest); try { $in.CopyTo($out) } finally { $out.Dispose() } } finally { $in.Dispose() }
 $records.Add([ordered]@{role=$Role;source=$Source;file=(Split-Path -Leaf $dest);sha256=(Get-FileHash -LiteralPath $dest).Hash})
 $dest
}
function Turn([string]$Role,[string]$Text,[string]$Model,$Tools) {
 [pscustomobject]@{role=$Role;text=$Text;model=$Model;tools=@($Tools | Where-Object { $_ })}
}
function Join-Parts($Content,[string[]]$Types) {
 if ($Content -is [string]) { return $Content }
 (@($Content | Where-Object { $_.type -in $Types -and $_.text }) | ForEach-Object text) -join "`n"
}

# --- Harness'a ozel ayristiricilar. Hepsi ayni turn listesini dondurur. ---
function Parse-OpenCode([string]$Path) {
 $j=Read-Text $Path | ConvertFrom-Json -Depth 64
 foreach ($m in $j.messages) {
  switch ($m.type) {
   'user' { Turn 'user' $m.text $null $null }
   'synthetic' { Turn 'user' $m.text $null $null }
   'assistant' {
    $tools=@($m.content | Where-Object type -eq 'tool' | ForEach-Object { [pscustomobject]@{name=$_.name;input=$_.state.input} })
    Turn 'assistant' (Join-Parts $m.content @('text')) "$($m.model.providerID)/$($m.model.id)" $tools
   }
  }
 }
}
function Parse-Claude([string]$Path,[bool]$SkipSidechain) {
 foreach ($o in Read-JsonLines $Path) {
  if ($o.type -notin @('user','assistant') -or !$o.message) { continue }
  if ($SkipSidechain -and $o.isSidechain) { continue }
  $c=$o.message.content
  $tools=if ($c -isnot [string]) { @($c | Where-Object type -eq 'tool_use' | ForEach-Object { [pscustomobject]@{name=$_.name;input=$_.input} }) }
  $model=if ($o.message.model -and $o.message.model -ne '<synthetic>') { $o.message.model }
  $text=Join-Parts $c @('text')
  # Claude Code 2.1.3xx: subagent nihai raporunu metin olarak degil SubagentHandback araciyla teslim eder.
  $handback=@($tools | Where-Object { $_.name -eq 'SubagentHandback' -and $_.input.message } | ForEach-Object { "$($_.input.message)" })
  if ($handback.Count) { $text=(@($text) + $handback | Where-Object { $_ }) -join "`n" }
  Turn $o.message.role $text $model $tools
 }
}
function Parse-Codex([string]$Path) {
 # Codex subagent kaydi parent gecmisinin kopyasiyla baslar (forked_from_id). Kopya kisim
 # ilk thread_settings_applied olayina kadar surer ve inherited=$true ile isaretlenir.
 $model=$null; $inherited=$false; $first=$true
 foreach ($o in Read-JsonLines $Path) {
  $p=$o.payload
  if ($first) { $first=$false; if ($o.type -eq 'session_meta' -and $p.forked_from_id) { $inherited=$true } }
  if ($o.type -eq 'event_msg' -and $p.type -eq 'thread_settings_applied') { $inherited=$false; continue }
  if ($o.type -eq 'turn_context' -and $p.model) { if (!$inherited) { $model=$p.model }; continue }
  if ($o.type -ne 'response_item') { continue }
  $turn=$null
  if ($p.type -eq 'message') {
   $role=if ($p.role -eq 'assistant') {'assistant'} else {'user'}
   $turn=Turn $role (Join-Parts $p.content @('input_text','output_text','text')) $(if ($role -eq 'assistant') {$model}) $null
  } elseif ($p.type -in @('function_call','custom_tool_call')) {
   $raw=if ($p.arguments) {$p.arguments} else {$p.input}
   $parsed=$raw
   if ($raw -is [string]) { try { $parsed=$raw | ConvertFrom-Json -Depth 32 } catch { } }
   $turn=Turn 'assistant' '' $model ([pscustomobject]@{name=$p.name;input=$parsed})
  }
  if ($turn) {
   $turn | Add-Member -NotePropertyName inherited -NotePropertyValue $inherited
   $turn | Add-Member -NotePropertyName source_role -NotePropertyValue "$($p.role)"
   $turn
  }
 }
}
function Codex-Meta([string]$Path) { (Read-JsonLines $Path | Select-Object -First 1).payload }
function Parse-Pi([string]$Path) {
 foreach ($o in Read-JsonLines $Path) {
  $m=$o.message
  if (!$m -or !$m.role) { continue }
  if ($o.type -like 'message_*' -and $o.type -ne 'message_end') { continue }
  $c=$m.content
  $tools=if ($c -isnot [string]) { @($c | Where-Object { $_.type -in @('toolCall','tool_use','tool_call') } | ForEach-Object {
   [pscustomobject]@{name=$_.name;input=$(if ($_.arguments) {$_.arguments} else {$_.input})} }) }
  $model=if ($m.model) { if ($m.provider) {"$($m.provider)/$($m.model)"} else {"$($m.model)"} }
  $role=if ($m.role -eq 'assistant') {'assistant'} elseif ($m.role -eq 'user') {'user'} else {'tool'}
  Turn $role (Join-Parts $c @('text')) $model $tools
 }
}

# --- Ortak cikarimlar ---
# Claude Code kullanicinin claude.ai belge araclari acikken raporu sohbete degil belgeye yazabiliyor.
# Belge icerigi arac cagrilarindaki inline markdown parcalarindan sirayla toplanir.
function Inline-Content($x) {
 if ($x -is [string] -or $null -eq $x) { return }
 if ($x -is [Collections.IEnumerable] -and $x -isnot [Collections.IDictionary]) { foreach ($i in $x) { Inline-Content $i }; return }
 if ($x -is [pscustomobject]) {
  if ($x.kind -eq 'inline' -and $x.content -is [string]) { $x.content; return }
  foreach ($p in $x.PSObject.Properties) { Inline-Content $p.Value }
 }
}
function Doc-Content($Turns) {
 $parts=@()
 foreach ($t in $Turns) { foreach ($tool in $t.tools) {
  if ($tool.name -notmatch 'Claude_Docs__(batch|update|create)') { continue }
  if ($tool.input.object -eq 'utterance') { $parts+='[Belgeye birakilan yorum] '+(($tool.input.payload.value | ConvertTo-Json -Depth 10 -Compress)); continue }
  $parts+=@(Inline-Content $tool.input)
 } }
 $parts -join "`n`n"
}
function Last-Answer($Turns) { (@($Turns | Where-Object { $_.role -eq 'assistant' -and $_.text.Trim() }) | Select-Object -Last 1).text }
function First-Context($Turns) {
 $out=@()
 foreach ($t in $Turns) { if ($t.role -eq 'assistant') { break }; if ($t.role -eq 'user' -and $t.text) { $out+=$t.text } }
 $out -join "`n`n"
}
function Models($Turns) { @($Turns | ForEach-Object model | Where-Object { $_ } | Select-Object -Unique) }
function Delegations($Turns) {
 foreach ($t in $Turns) { foreach ($tool in $t.tools) {
  $in=$tool.input
  $agent=@($in.agent,$in.subagent_type,$in.agent_type,$in.agent_name) | Where-Object { $_ } | Select-Object -First 1
  if ($tool.name -notmatch '(?i)subagent|^task$|^agent$|researcher|spawn' -and !$agent) { continue }
  if (!$agent -and $tool.name -match '(?i)researcher') { $agent='researcher' }
  $prompt=@($in.prompt,$in.task,$in.message,$in.instructions) | Where-Object { $_ -is [string] -and $_ } | Select-Object -First 1
  if (!$prompt) { $prompt=if ($in -is [string]) {$in} else {$in | ConvertTo-Json -Depth 16 -Compress} }
  [pscustomobject]@{agent=$agent;prompt=$prompt;tool=$tool.name}
 } }
}
# OpenCode claude-agent saglayicisinda gercek model kimligi Claude kayitlarindadir.
function Native-Models([string]$Raw) {
 $base=if ($env:CLAUDE_CONFIG_DIR) {$env:CLAUDE_CONFIG_DIR} else {Join-Path $HOME '.claude'}
 $ids=[regex]::Matches($Raw,'"sessionID"\s*:\s*"([0-9a-f-]{36})"') | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique
 foreach ($sid in $ids) {
  $file=Get-ChildItem -Path (Join-Path $base 'projects') -Recurse -Filter "$sid.jsonl" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($file) { Models (Parse-Claude $file.FullName $false) }
 }
}

$parentTurns=@(); $children=@(); $identity=''; $tokens=$null; $elapsed=$null; $effort=$null
$piDispatch=@()
switch ($r.harness) {
 'OpenCode Desktop' {
  Push-Location -LiteralPath $project
  try {
   $list=@(& opencode session list 2>$null | ForEach-Object { if ($_ -match '^(ses_[A-Za-z0-9_-]+)') { $Matches[1] } })
   if (!$list.Count) { throw 'Bu proje klasorunde OpenCode oturumu bulunamadi.' }
   $tops=foreach ($sid in $list) {
    $tmp=Join-Path $cap "tmp-$sid.json"
    & opencode session export $sid 2>$null | Set-Content -LiteralPath $tmp -Encoding utf8
    $info=(Read-Text $tmp | ConvertFrom-Json -Depth 64).info
    [pscustomobject]@{id=$sid;file=$tmp;created=$info.time.created;parent=$info.parentID}
   }
   $top=@($tops | Where-Object { !$_.parent } | Sort-Object created -Descending)
   if ($top.Count -gt 1) { $warnings.Add("Proje klasorunde $($top.Count) ust oturum var. En yenisi kullanildi.") }
   $parentId=$top[0].id
   $parentFile=Join-Path $cap 'parent.json'
   Move-Item -LiteralPath $top[0].file -Destination $parentFile
   $tops | Where-Object { Test-Path -LiteralPath $_.file } | ForEach-Object { Remove-Item -LiteralPath $_.file }
   $records.Add([ordered]@{role='parent';source=$parentId;file='parent.json';sha256=(Get-FileHash -LiteralPath $parentFile).Hash})
   $parentRaw=Read-Text $parentFile
   $parentInfo=($parentRaw | ConvertFrom-Json -Depth 64).info
   $parentTurns=@(Parse-OpenCode $parentFile)
   $tokens=[ordered]@{parent=$parentInfo.tokens;child=@()}
   $elapsed=[math]::Round(($parentInfo.time.updated-$parentInfo.time.created)/1000)
   $effort=$parentInfo.model.variant
   $nativeParent=@(Native-Models $parentRaw)
   $n=0
   foreach ($sid in ([regex]::Matches($parentRaw,'ses_[A-Za-z0-9_-]+') | ForEach-Object Value | Select-Object -Unique | Where-Object { $_ -ne $parentId })) {
    $n++
    $file=Join-Path $cap "child-$n.json"
    & opencode session export $sid 2>$null | Set-Content -LiteralPath $file -Encoding utf8
    $raw=Read-Text $file
    $info=($raw | ConvertFrom-Json -Depth 64).info
    $records.Add([ordered]@{role="child-$n";source=$sid;file="child-$n.json";sha256=(Get-FileHash -LiteralPath $file).Hash})
    $turns=@(Parse-OpenCode $file)
    $native=@(Native-Models $raw)
    $children+=[pscustomobject]@{turns=$turns;agent=$info.agent;models=$(if ($native.Count) {$native} else {Models $turns})}
    $tokens.child+=$info.tokens
   }
   $parentModels=if ($nativeParent.Count) {$nativeParent} else {Models $parentTurns}
   $identity=if ($nativeParent.Count) {'OpenCode export native.sessionID degerleri ~/.claude/projects altindaki JSONL kayitlariyla eslestirildi, assistant message.model alanlari okundu.'}
             else {'OpenCode export icindeki assistant model.providerID ve model.id alanlari.'}
  } finally { Pop-Location }
 }
 'Claude Code' {
  $base=if ($env:CLAUDE_CONFIG_DIR) {$env:CLAUDE_CONFIG_DIR} else {Join-Path $HOME '.claude'}
  $dir=Join-Path $base ('projects/'+($project -replace '[^A-Za-z0-9]','-'))
  $top=@(Get-ChildItem -LiteralPath $dir -Filter '*.jsonl' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
  if (!$top.Count) { throw "Claude Code kaydi bulunamadi: $dir" }
  if ($top.Count -gt 1) { $warnings.Add("Proje klasorunde $($top.Count) oturum var. En yenisi kullanildi.") }
  $parentTurns=@(Parse-Claude (Save 'parent' $top[0].FullName) $true)
  $parentModels=Models $parentTurns
  $sub=Join-Path $dir $top[0].BaseName
  $n=0
  foreach ($file in @(Get-ChildItem -LiteralPath $sub -Recurse -Filter '*.jsonl' -File -ErrorAction SilentlyContinue | Sort-Object CreationTime)) {
   $n++
   $turns=@(Parse-Claude (Save "child-$n" $file.FullName) $false)
   $children+=[pscustomobject]@{turns=$turns;agent=$null;models=(Models $turns)}
  }
  $identity='Claude Code JSONL kayitlarindaki assistant message.model alanlari.'
 }
 'Codex' {
  $base=if ($env:CODEX_HOME) {$env:CODEX_HOME} else {Join-Path $HOME '.codex'}
  $since=$runDir.CreationTime.AddMinutes(-1)
  $want=$project.TrimEnd('\','/')
  $found=@(Get-ChildItem -Path (Join-Path $base 'sessions') -Recurse -Filter '*.jsonl' -File -ErrorAction SilentlyContinue |
   Where-Object { $_.LastWriteTime -ge $since } | Where-Object {
    $meta=Read-JsonLines $_.FullName | Select-Object -First 1
    "$($meta.payload.cwd)".TrimEnd('\','/') -ieq $want
   } | Sort-Object Name)
  if (!$found.Count) { throw "Codex kaydi bulunamadi (cwd $want)." }
  # Ana kayit: subagent olarak baslatilmamis en eski oturum.
  $main=@($found | Where-Object { (Codex-Meta $_.FullName).thread_source -ne 'subagent' }) | Select-Object -First 1
  if (!$main) { $main=$found[0] }
  $parentTurns=@(Parse-Codex (Save 'parent' $main.FullName))
  $parentModels=Models $parentTurns
  $n=0; $codexInherited=@(); $codexFollowUps=@($parentTurns.tools | Where-Object { $_.name -eq 'send_message' }).Count
  foreach ($file in ($found | Where-Object { $_.FullName -ne $main.FullName })) {
   $n++
   $meta=Codex-Meta $file.FullName
   $all=@(Parse-Codex (Save "child-$n" $file.FullName))
   $turns=@($all | Where-Object { !$_.inherited })
   $codexInherited+=,@($all | Where-Object { $_.inherited -and $_.source_role -eq 'user' -and $_.text } | ForEach-Object text)
   $children+=[pscustomobject]@{turns=$turns;agent=$meta.agent_role;models=(Models $turns)}
  }
  if ($r.phase -ne 'D' -and $n) { $warnings.Add("Ayni klasorde $($n+1) Codex oturumu var. En eskisi ana kayit sayildi.") }
  $identity='Codex rollout kayitlarindaki turn_context model alanlari.'
 }
 'Pi' {
  $log=Join-Path $work 'log'
  $top=@(Get-ChildItem -Path (Join-Path $log 'pi-parent') -Recurse -Filter '*.jsonl' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
  if (!$top.Count) { throw "Pi parent kaydi yok. Pi'yi --session-dir ..\log\pi-parent ile baslatin." }
  if ($top.Count -gt 1) { $warnings.Add("$($top.Count) Pi parent kaydi var. En yenisi kullanildi.") }
  $parentTurns=@(Parse-Pi (Save 'parent' $top[0].FullName))
  $parentModels=Models $parentTurns
  $n=0
  foreach ($file in @(Get-ChildItem -LiteralPath $log -Filter 'pi-child-*.jsonl' -File -ErrorAction SilentlyContinue | Sort-Object CreationTime)) {
   $n++
   $turns=@(Parse-Pi (Save "child-$n" $file.FullName))
   $stem=$file.FullName.Substring(0,$file.FullName.Length-6)
   $dispatch=$null; $system=$null
   if (Test-Path -LiteralPath "$stem.dispatch.json") { $dispatch=Read-Text (Save "child-$n.dispatch" "$stem.dispatch.json") | ConvertFrom-Json }
   if (Test-Path -LiteralPath "$stem.system.txt") { $system=Read-Text (Save "child-$n.system" "$stem.system.txt") }
   $models=@(Models $turns); if (!$models.Count -and $dispatch.model) { $models=@("$($dispatch.model) (dispatch)") }
   $children+=[pscustomobject]@{turns=$turns;agent='researcher';models=$models}
   $piDispatch+=[pscustomobject]@{task=$dispatch.task;system=$system}
  }
  $identity='Pi oturum ve child kayitlarindaki assistant message model alanlari. Child icin dispatch.json model alani yedek kanit.'
 }
 default { throw "Bilinmeyen harness: $($r.harness)" }
}

# --- result.json alanlari ---
$missing=[Collections.Generic.List[string]]::new()
$failed=[Collections.Generic.List[string]]::new()
function Check-Model([string]$Label,$Actual,[string]$Planned) {
 if (!@($Actual).Count) { $missing.Add("$Label model kimligi"); return }
 if (@($Actual | Where-Object { $_ -notlike "*$Planned*" }).Count) { $failed.Add("$Label modeli beklenen $Planned, gozlenen $(@($Actual) -join ', ')") }
}
$r.provider=if ($r.requested_parent -match '/') {($r.requested_parent -split '/')[0]} elseif ($r.requested_child -match '/') {($r.requested_child -split '/')[0]} else {$null}
$r.model_identity_evidence="$identity Kayitlar evidence/$capName altinda."
$r.artifacts=@("evidence/$capName")
$r.effort=$effort
$r.elapsed_seconds=$elapsed
if ($tokens) { $r | Add-Member -NotePropertyName tokens_detail -NotePropertyValue $tokens -Force }
$visibility='Kayit child oturumunun ilk kullanici mesajlarini gosteriyor. Child sistem promptu ve harness tarafindan eklenen diger baglam kayitta gorunmuyorsa burada yoktur.'

if ($r.phase -eq 'R') {
 # Tek oturum. Ana model researcher'in kendisi.
 $r.actual_child=(@($parentModels) -join ', ')
 $r.child_first_message_raw=First-Context $parentTurns
 $r.child_output_raw=Last-Answer $parentTurns
 $task=(Read-Text (Join-Path $evidence 'task.txt')).Trim()
 $r.parent_child_raw=$task
 $first="$($r.child_first_message_raw)"
 $r.child_auto_context_observed=if ($first.Contains($task)) { $first.Replace($task,'').Trim() } else { 'ELLE KONTROL: gorev metni ilk mesajda birebir bulunamadi' }
 $r.child_context_visibility=$visibility
 Check-Model 'Researcher' $parentModels $r.planned_child
 if (!$r.child_output_raw) { $missing.Add('researcher ciktisi') }
} else {
 $r.actual_parent=(@($parentModels) -join ', ')
 $r.parent_final_raw=Last-Answer $parentTurns
 $doc=Doc-Content $parentTurns
 if ($doc) {
  # Kor puanlamada harness belli olmasin: isaret notr, sohbetteki belge baglantisi ayri alanda.
  $r | Add-Member -NotePropertyName parent_chat_reply -NotePropertyValue $r.parent_final_raw -Force
  $r.parent_final_raw="[Nihai cevap bir belgeye yazildi. Asagidaki metin belgeye yazilan parcalardir.]`n`n$doc"
  $warnings.Add('Parent raporu claude.ai belgesine yazdi; belge icerigi kayittan toplandi. Bu harness ortamindan gelen bir sapma, scoring_notes alanina yazildi.')
  $r.scoring_notes=(@($r.scoring_notes,'Parent nihai raporu sohbet yerine claude.ai belgesine yazdi (kullanicinin genel Claude Docs araclari acik).') | Where-Object { $_ }) -join ' '
 }
 Check-Model 'Parent' $parentModels $r.planned_parent
 if (!$r.parent_final_raw) { $missing.Add('parent nihai cevabi') }
 $calls=@(Delegations $parentTurns)
 if ($r.harness -eq 'Pi' -and !$calls.Count -and $piDispatch.Count) {
  $calls=@($piDispatch | ForEach-Object { [pscustomobject]@{agent='researcher';prompt=$_.task;tool='researcher'} })
 }
 $r.delegation_count=$calls.Count
 if ($r.phase -eq 'S') {
  if ($calls.Count) { $warnings.Add("Parent $($calls.Count) kez baska agent cagirdi. scoring_notes alanina yazildi.") ; $r.scoring_notes="Faz S sirasinda parent agent cagirdi: $(@($calls.agent) -join ', ')" }
 } else {
  $r.agent_called=(@($calls.agent | Where-Object { $_ } | Select-Object -Unique) -join ', ')
  $r.parent_child_raw=(@($calls.prompt) -join "`n`n-----`n`n")
  $childModels=@($children | ForEach-Object { $_.models } | Select-Object -Unique)
  $r.actual_child=($childModels -join ', ')
  $firsts=@(); $i=0
  foreach ($child in $children) {
   $text=First-Context $child.turns
   if (!$text -and $r.harness -eq 'Pi' -and $piDispatch[$i]) { $text='Task: '+$piDispatch[$i].task }
   $firsts+=$text; $i++
  }
  $r.child_first_message_raw=($firsts -join "`n`n-----`n`n")
  $auto=@()
  for ($i=0; $i -lt $firsts.Count; $i++) {
   $prompt=if ($i -lt $calls.Count) {"$($calls[$i].prompt)"} else {''}
   if ($prompt -and $firsts[$i].Contains($prompt)) { $rest=$firsts[$i].Replace($prompt,'').Trim(); if ($rest) { $auto+=$rest } }
   else { $auto+='ELLE KONTROL: delegasyon metni child ilk mesajinda birebir bulunamadi' }
   if ($r.harness -eq 'Pi' -and $piDispatch[$i].system) { $auto+="[sistem promptu eki] $($piDispatch[$i].system)" }
  }
  $r.child_auto_context_observed=($auto | Select-Object -Unique) -join "`n`n"
  $r.child_context_visibility=$visibility
  if ($r.harness -eq 'Codex' -and $children.Count) {
   # Codex 0.163: agentlar arasi mesajlar kayitta sifreli, child ise parent gecmisini devraliyor.
   if ("$($r.parent_child_raw)" -match 'gAAAA[A-Za-z0-9_\-=]{40,}') {
    $r.parent_child_raw='OKUNAMIYOR: Codex agentlar arasi mesajlari kayitta sifreli tutuyor (encrypted_content). Sifreli hali ham kayitta.'
    $r.child_first_message_raw='OKUNAMIYOR: gorev mesaji sifreli. Child ayrica parent gecmisini devraldi, bkz. child_auto_context_observed.'
    $warnings.Add('Delegasyon metni sifreli, okunamiyor. Kural aktarimi delegasyon metninden puanlanamaz.')
   }
   $parts=@(); $i=0
   foreach ($list in $codexInherited) { $i++; if (@($list).Count) { $parts+="[child-$i parent gecmisinden $(@($list).Count) kullanici mesaji devraldi]`n`n"+(@($list) -join "`n`n---`n`n") } }
   if ($parts.Count) {
    $r.child_auto_context_observed=$parts -join "`n`n=====`n`n"
    $warnings.Add('Child oturumu parent konusma gecmisini devraldi (fork). Ilk mesajdaki kurallar child kaydinda mevcut.')
   } else { $r.child_auto_context_observed='Child kaydinda devralinan parent gecmisi yok.' }
   $r.child_context_visibility="Codex rollout kaydi. Child kaydinin basi parent gecmisinin kopyasi (session_meta.forked_from_id). Agentlar arasi mesajlar sifreli. Parent ilk gorevden sonra child'a $codexFollowUps ek mesaj gonderdi (send_message)."
  }
  $r.child_output_raw=(@($children | ForEach-Object { Last-Answer $_.turns } | Where-Object { $_ }) -join "`n`n-----`n`n")
  if (!$calls.Count) { $missing.Add('delegasyon cagrisi (parent researcher cagirmamis olabilir)') }
  elseif ($r.agent_called -ne 'researcher') {
   $agents=@($children.agent | Where-Object { $_ } | Select-Object -Unique)
   if ($agents.Count -eq 1 -and $agents[0] -eq 'researcher') { $r.agent_called='researcher' }
   elseif ($r.agent_called -or $agents.Count) { $failed.Add("Cagrilan agent researcher degil: $($r.agent_called) $($agents -join ', ')") }
   else { $missing.Add('cagrilan agent adi') }
  }
  if (!$children.Count) { $missing.Add('child kaydi') }
  else {
   Check-Model 'Child' $childModels $r.planned_child
   if (!$r.child_first_message_raw.Trim('-',"`n",' ')) { $missing.Add('child ilk mesaji') }
   if (!$r.child_output_raw) { $missing.Add('child ciktisi') }
   elseif ("$($r.child_output_raw)".Length -lt 1000) { $missing.Add("child ciktisi supheli kisa ($("$($r.child_output_raw)".Length) karakter)") }
  }
 }
}
$text="$($r.child_output_raw)"
$r.source_links=@([regex]::Matches($text,'https?://[^\s\)\]>"|`]+') | ForEach-Object { $_.Value.TrimEnd('.',',',';',':','*') } | Select-Object -Unique)

if ($failed.Count) { $r.status='FAILED'; $r.reason=($failed -join ' | ') }
elseif ($missing.Count) { $r.status='CONFIGURED'; $r.reason='EKSIK: '+($missing -join ', ') }
else { $r.status='VERIFIED'; $r.reason=$null }
[IO.File]::WriteAllText($resultPath,($r | ConvertTo-Json -Depth 20))
[ordered]@{captured_utc=[DateTime]::UtcNow.ToString('o');records=$records;warnings=$warnings} |
 ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $cap 'capture.json') -Encoding utf8

''
"Kosu $id | Faz $($r.phase) | $($r.harness) | kosul $($r.condition)"
"Kayit dosyasi : $($records.Count) (evidence/$capName)"
"Parent modeli : $($r.actual_parent)"
"Child modeli  : $($r.actual_child)"
if ($r.phase -eq 'D') { "Cagrilan agent: $($r.agent_called) | cagri sayisi $($r.delegation_count)" }
"Metin boylari : delegasyon $("$($r.parent_child_raw)".Length), child cikti $("$($r.child_output_raw)".Length), parent nihai $("$($r.parent_final_raw)".Length)"
foreach ($w in $warnings) { "UYARI  : $w" }
switch ($r.status) {
 'VERIFIED' { "SONUC  : TAMAM. Siradaki kosuya gecebilirsiniz." }
 'FAILED' { "SONUC  : BASARISIZ. $($r.reason)"; "         Bu kosuyu runbook'taki ayni komutlarla bir kez yeniden yapin." }
 default { "SONUC  : EKSIK ALAN VAR. $($r.reason)"; "         Kayitlar alindi. Siradaki kosuya gecin, eksikler en sonda tamamlanacak." }
}
