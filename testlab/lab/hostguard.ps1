# Passive, read-only host sampler for the testlab host guard (lab/hostguard.py). No elevation, nothing
# is started, stopped or changed: Get-Process, one Win32_Process query filtered to AnyDesk.exe, and
# three persistent performance counters (NextValue is a delta, so no sleeping Get-Counter).
# One JSON object per interval on stdout; the parent stamps its own clock on each line.
# Derived from the proven F19 sampler (.testlab-runs/f19/sampler.ps1).
param([double]$IntervalS = 5, [double]$DurationS = 0, [int]$ParentPid = 0)
$ErrorActionPreference = 'SilentlyContinue'
$ncpu = [Environment]::ProcessorCount
$self = [System.Diagnostics.Process]::GetCurrentProcess()
$prev = @{}                 # pid -> @{c = cpu seconds; t = DateTime}
$known = @{}                # pids seen in the previous snapshot (new-process rate)
$build = 'dotnet','MSBuild','VBCSCompiler','Unity','UnityHub','Unity.Licensing.Client','cargo','rustc','cl','link','go'
$av = 'MsMpEng'
$agents = 'claude','codex'
$node = 'node','node_repl'
$shells = 'bash','sh','wsl','wslhost','git','python','python3','powershell','pwsh','cmd'
$ctr = @{}
foreach ($n in @('% Processor Time', '% DPC Time', '% Interrupt Time')) {
  try { $c = New-Object System.Diagnostics.PerformanceCounter('Processor', $n, '_Total'); [void]$c.NextValue(); $ctr[$n] = $c } catch {}
}
$selfPrev = @{c = $self.TotalProcessorTime.TotalSeconds; t = Get-Date}
$stop = if ($DurationS -gt 0) { (Get-Date).AddSeconds($DurationS) } else { $null }
$outw = [Console]::Out
while ($true) {
  $t = Get-Date
  if ($stop -and $t -ge $stop) { break }
  if ($ParentPid -gt 0 -and -not (Get-Process -Id $ParentPid)) { break }
  $row = [ordered]@{ ts = $t.ToUniversalTime().ToString('o'); epoch = [math]::Round(([DateTimeOffset]$t).ToUnixTimeMilliseconds() / 1000.0, 3) }
  try {
    $ps = @(Get-Process)
    $seen = @{}
    $grp = @{build = 0.0; av = 0.0; agents = 0.0; node = 0.0}
    $new = 0
    $adp = @()
    foreach ($p in $ps) {
      $k = $p.Id; $seen[$k] = 1
      if (-not $known.ContainsKey($k) -and $shells -contains $p.ProcessName) { $new++ }
      $cpu = $null; try { $cpu = $p.CPU } catch {}
      $pct = $null
      if ($cpu -ne $null -and $prev.ContainsKey($k)) {
        $dt = ($t - $prev[$k].t).TotalSeconds
        if ($dt -gt 0) { $pct = [math]::Round((($cpu - $prev[$k].c) / $dt) * 100.0 / $ncpu, 3) }
      }
      if ($cpu -ne $null) { $prev[$k] = @{c = $cpu; t = $t} }
      $name = $p.ProcessName
      if ($pct -ne $null) {
        if ($build -contains $name) { $grp.build += $pct }
        elseif ($av -contains $name) { $grp.av += $pct }
        elseif ($agents -contains $name) { $grp.agents += $pct }
        elseif ($node -contains $name) { $grp.node += $pct }
      }
      if ($name -eq 'AnyDesk') { $adp += [pscustomobject]@{ pid = $k; cpu = $pct; ws_mb = [math]::Round($p.WorkingSet64 / 1MB, 1); handles = $p.HandleCount } }
    }
    foreach ($k in @($prev.Keys)) { if (-not $seen.ContainsKey($k)) { $prev.Remove($k) } }
    $known = $seen
    $roles = @{}
    if ($adp.Count -gt 0) {
      foreach ($w in @(Get-CimInstance -ClassName Win32_Process -Filter "Name='AnyDesk.exe'")) {
        $cl = [string]$w.CommandLine
        $r = if ($cl -match '--backend') { 'backend' } elseif ($cl -match '--local-service|--local-control') { 'resident' } elseif ($cl -match '^\s*"?[^"]*AnyDesk\.exe"?\s*$') { 'resident' } else { 'other' }
        $roles[[int]$w.ProcessId] = $r
      }
    }
    $adout = @()
    $adtotal = 0.0
    foreach ($a in $adp) {
      $role = if ($roles.ContainsKey([int]$a.pid)) { $roles[[int]$a.pid] } else { 'unknown' }
      $adout += [ordered]@{ pid = $a.pid; role = $role; cpu = $a.cpu; ws_mb = $a.ws_mb; handles = $a.handles }
      if ($a.cpu -ne $null) { $adtotal += $a.cpu }
    }
    $row.ad = $adout
    $row.ad_cpu = [math]::Round($adtotal, 3)
    $row.groups = [ordered]@{ build = [math]::Round($grp.build, 3); av = [math]::Round($grp.av, 3); agents = [math]::Round($grp.agents, 3); node = [math]::Round($grp.node, 3) }
    $row.newproc = $new
  } catch { $row.error = [string]$_.Exception.Message }
  try {
    $row.cpu = [math]::Round($ctr['% Processor Time'].NextValue(), 2)
    $row.dpc = [math]::Round($ctr['% DPC Time'].NextValue(), 2)
    $row.intr = [math]::Round($ctr['% Interrupt Time'].NextValue(), 2)
  } catch {}
  try {
    $self.Refresh()
    $sc = $self.TotalProcessorTime.TotalSeconds; $sdt = ((Get-Date) - $selfPrev.t).TotalSeconds
    if ($sdt -gt 0) { $row.own_cpu = [math]::Round((($sc - $selfPrev.c) / $sdt) * 100.0 / $ncpu, 4) }
    $selfPrev = @{c = $sc; t = Get-Date}
  } catch {}
  $outw.WriteLine(($row | ConvertTo-Json -Compress -Depth 5)); $outw.Flush()
  $sl = $IntervalS - ((Get-Date) - $t).TotalSeconds
  if ($sl -gt 0) { Start-Sleep -Milliseconds ([int]($sl * 1000)) }
}
