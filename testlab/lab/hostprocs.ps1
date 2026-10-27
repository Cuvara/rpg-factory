# Optional 1 s per-process CPU sampler for S09-class runs (lab/hostguard.py ProcSampler). Passive and
# read-only like hostguard.ps1: Get-Process only, no elevation, nothing started, stopped or changed.
# One JSON object per interval on stdout: the top N processes by CPU (% of the whole host over the
# interval), the sampler's own CPU and how long the sweep took. EVIDENCE ONLY: no guard reads it.
param([double]$IntervalS = 1, [int]$TopN = 10, [double]$DurationS = 0, [int]$ParentPid = 0)
$ErrorActionPreference = 'SilentlyContinue'
$ncpu = [Environment]::ProcessorCount
$self = [System.Diagnostics.Process]::GetCurrentProcess()
$prev = @{}                 # pid -> @{c = cpu seconds; t = DateTime}
$selfPrev = @{c = $self.TotalProcessorTime.TotalSeconds; t = Get-Date}
$stop = if ($DurationS -gt 0) { (Get-Date).AddSeconds($DurationS) } else { $null }
$outw = [Console]::Out
while ($true) {
  $t = Get-Date
  if ($stop -and $t -ge $stop) { break }
  if ($ParentPid -gt 0 -and -not (Get-Process -Id $ParentPid)) { break }
  $row = [ordered]@{ epoch = [math]::Round(([DateTimeOffset]$t).ToUnixTimeMilliseconds() / 1000.0, 3) }
  try {
    $seen = @{}
    $rows = New-Object System.Collections.Generic.List[object]
    foreach ($p in @(Get-Process)) {
      $k = $p.Id; $seen[$k] = 1
      $cpu = $null; try { $cpu = $p.CPU } catch {}
      if ($cpu -eq $null) { continue }
      if ($prev.ContainsKey($k)) {
        $dt = ($t - $prev[$k].t).TotalSeconds
        if ($dt -gt 0) {
          $pct = (($cpu - $prev[$k].c) / $dt) * 100.0 / $ncpu
          if ($pct -gt 0) { $rows.Add([pscustomobject]@{ pid = $k; name = $p.ProcessName; cpu = [math]::Round($pct, 2) }) }
        }
      }
      $prev[$k] = @{c = $cpu; t = $t}
    }
    foreach ($k in @($prev.Keys)) { if (-not $seen.ContainsKey($k)) { $prev.Remove($k) } }
    $row.top = @($rows | Sort-Object cpu -Descending | Select-Object -First $TopN)
    $row.sweep_ms = [math]::Round(((Get-Date) - $t).TotalMilliseconds, 1)
  } catch { $row.error = [string]$_.Exception.Message }
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
