<#
.SYNOPSIS
  API-level end-to-end smoke test (no LLM calls, so it spends no AI quota).
.EXAMPLE
  .\scripts\smoke.ps1 -BaseUrl https://isushant-aggroso.hf.space
#>
param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Password = "migrateiq-demo",
    [switch]$Stress
)
$ErrorActionPreference = "Stop"
$api = "$($BaseUrl.TrimEnd('/'))/api"
$failures = 0

function Step([string]$name, [scriptblock]$body) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    try { $r = & $body; Write-Host ("PASS  {0,-46} {1,6} ms  {2}" -f $name, $sw.ElapsedMilliseconds, $r) }
    catch { $script:failures++; Write-Host ("FAIL  {0,-46} {1}" -f $name, $_.Exception.Message) -ForegroundColor Red; throw }
}
function Call([string]$method, [string]$path, $token, $body = $null, [hashtable]$extra = @{}) {
    $headers = @{ Authorization = "Bearer $token" } + $extra
    $args = @{ Uri = "$api$path"; Method = $method; Headers = $headers; ContentType = "application/json"; TimeoutSec = 120 }
    if ($null -ne $body) { $args.Body = ($body | ConvertTo-Json -Depth 10) }
    Invoke-RestMethod @args
}
function Login([string]$user) {
    (Invoke-RestMethod "$api/auth/login" -Method Post -ContentType "application/json" `
        -Body (@{ username = $user; password = $Password } | ConvertTo-Json)).access_token
}
function Assert($cond, [string]$msg) { if (-not $cond) { throw $msg } }

try {
    Step "health" { $h = Invoke-RestMethod "$api/health"; Assert ($h.db.status -eq "ok") "db not ok"; "status=$($h.status) ai=$($h.ai.status) version=$($h.version)" }
    $op = Login "operator"; $ap = Login "approver"
    $project = $null; $version = $null; $run = $null
    Step "create project (baseline_60)" { $script:project = Call POST "/projects" $op @{ name = "smoke $(Get-Date -Format s)"; dataset_key = "baseline_60" }; "project=$($script:project.id) records=$($script:project.record_count)" }
    Step "load reference plan" { $script:version = Call POST "/projects/$($project.id)/plan-versions/reference" $op; "version=$($script:version.id)" }
    Step "acknowledge high risks" { $ids = @($version.unacknowledged_high_risk_ids); if ($ids.Count) { $script:version = Call POST "/plan-versions/$($version.id)/risk-acks" $op @{ risk_ids = $ids } }; "acked=$($ids.Count)" }
    Step "dry run (expect 60/55/45/15)" {
        $d = Call POST "/plan-versions/$($version.id)/dry-runs" $op
        Assert ("$($d.counts.source)/$($d.counts.transformed)/$($d.counts.accepted)/$($d.counts.rejected)" -eq "60/55/45/15") "counts $($d.counts.source)/$($d.counts.transformed)/$($d.counts.accepted)/$($d.counts.rejected)"
        "60/55/45/15"
    }
    Step "execute before approval is refused" {
        try { Call POST "/plan-versions/$($version.id)/runs" $op @{} @{ "Idempotency-Key" = [guid]::NewGuid().ToString() } | Out-Null; throw "not refused" }
        catch { if ($_.Exception.Message -eq "not refused") { throw }; "refused" }
    }
    Step "approve" { $a = Call POST "/plan-versions/$($version.id)/approve" $ap @{ comment = "smoke" }; "status=$($a.version.status)" }
    $key = [guid]::NewGuid().ToString()
    Step "execute with fault after 20" {
        $script:run = Call POST "/plan-versions/$($version.id)/runs" $op @{ simulate_failure_after = 20 } @{ "Idempotency-Key" = $key }
        Assert ($script:run.status -eq "FAILED") "expected FAILED, got $($script:run.status)"; "run=$($script:run.id) inserted=$($script:run.inserted)"
    }
    Step "replay same idempotency key" { $r = Call POST "/plan-versions/$($version.id)/runs" $op @{ simulate_failure_after = 20 } @{ "Idempotency-Key" = $key }; Assert ($r.id -eq $run.id) "new run created"; "replayed=$($r.replayed)" }
    Step "retry" { $script:run = Call POST "/runs/$($run.id)/retry" $op; Assert ($script:run.status -eq "COMPLETED") "status $($script:run.status)"; "inserted=$($script:run.inserted) skipped=$($script:run.skipped_existing) quarantined=$($script:run.quarantined)" }
    Step "reconcile (expect PASS)" { $rc = Call GET "/runs/$($run.id)/reconciliation" $op; Assert ($rc.status -eq "PASS") "status $($rc.status)"; "PASS" }
    Step "rollback" { $rb = Call POST "/runs/$($run.id)/rollback" $ap @{ reason = "smoke test cleanup" }; Assert ($rb.status -eq "ROLLED_BACK") "status $($rb.status)"; "status=$($rb.status)" }
    Step "reconcile after rollback" { $rc = Call GET "/runs/$($run.id)/reconciliation" $op; "status=$($rc.status)" }
    Step "history has events" { $h = Call GET "/projects/$($project.id)/history" $op; $n = @($h.events).Count; if (-not $n) { $n = @($h).Count }; Assert ($n -gt 0) "no events"; "events=$n" }
    Step "limit: overflow_501 rejected" {
        try { Call POST "/projects" $op @{ name = "overflow"; dataset_key = "overflow_501" } | Out-Null; throw "accepted" }
        catch { if ($_.Exception.Message -eq "accepted") { throw }; "rejected" }
    }
    if ($Stress) {
        Step "stress_500: project + reference + dry run" {
            $p = Call POST "/projects" $op @{ name = "stress"; dataset_key = "stress_500" }
            $v = Call POST "/projects/$($p.id)/plan-versions/reference" $op
            $d = Call POST "/plan-versions/$($v.id)/dry-runs" $op
            "source=$($d.counts.source) accepted=$($d.counts.accepted)"
        }
    }
} catch { }
if ($failures) { Write-Host "SMOKE FAILED ($failures)" -ForegroundColor Red; exit 1 } else { Write-Host "SMOKE PASSED" -ForegroundColor Green }
