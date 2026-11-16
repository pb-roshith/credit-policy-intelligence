@echo off
setlocal
set "CPI_STOP_FILE=%~f0"
set "CPI_STOP_DRY_RUN=0"
if /i "%~1"=="--dry-run" set "CPI_STOP_DRY_RUN=1"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$content = [IO.File]::ReadAllText($env:CPI_STOP_FILE); $payload = ($content -split '(?m)^# POWERSHELL PAYLOAD #\r?$', 2)[1]; & ([scriptblock]::Create($payload)) -WhatIf:($env:CPI_STOP_DRY_RUN -eq '1')"
set "stop_result=%errorlevel%"
if "%CPI_STOP_DRY_RUN%"=="1" exit /b %stop_result%
echo.
pause
exit /b %stop_result%
# POWERSHELL PAYLOAD #
[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'Low')]
param()

$ErrorActionPreference = 'Stop'
$applicationRoot = [IO.Path]::GetFullPath((Split-Path -LiteralPath $env:CPI_STOP_FILE)).TrimEnd('\') + '\'
$serverPorts = @(8004, 8003, 8081, 8002, 5173, 8005, 5174)

try {
    $processes = @{}
    Get-CimInstance Win32_Process | ForEach-Object { $processes[[int]$_.ProcessId] = $_ }
    $listeners = @(Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in $serverPorts })
    $targets = @{}
    $skipped = $false
    foreach ($listener in $listeners) {
        $candidateId = [int]$listener.OwningProcess
        $targetProcess = $null
        $visited = @{}
        while ($candidateId -gt 0 -and $processes.ContainsKey($candidateId) -and -not $visited.ContainsKey($candidateId)) {
            $visited[$candidateId] = $true
            $candidate = $processes[$candidateId]
            $isRuntime = $candidate.Name -in @('python.exe', 'pythonw.exe', 'node.exe')
            $matchesPath = $candidate.ExecutablePath -and $candidate.ExecutablePath.StartsWith($applicationRoot, [StringComparison]::OrdinalIgnoreCase)
            $matchesCommand = $candidate.CommandLine -and $candidate.CommandLine.IndexOf($applicationRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0
            if ($isRuntime -and ($matchesPath -or $matchesCommand)) { $targetProcess = $candidate }
            $candidateId = [int]$candidate.ParentProcessId
        }
        if ($null -eq $targetProcess) {
            Write-Warning "Port $($listener.LocalPort) belongs to an unrecognized process. Leaving it running."
            $skipped = $true
            continue
        }
        $targets[[int]$targetProcess.ProcessId] = $targetProcess
    }
    if ($targets.Count -eq 0 -and -not $skipped) {
        Write-Host 'All seven application servers are already stopped.'
        exit 0
    }
    foreach ($targetProcess in $targets.Values) {
        $targetId = [int]$targetProcess.ProcessId
        if ($PSCmdlet.ShouldProcess("$($targetProcess.Name) PID $targetId", 'Stop application server and child processes')) {
            $currentProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $targetId"
            if (-not $currentProcess) { continue }
            if ($currentProcess.CreationDate -ne $targetProcess.CreationDate) {
                throw "Process $targetId changed while checking servers. Run stop_all.bat again."
            }
            & taskkill.exe /PID $targetId /T /F
            if ($LASTEXITCODE -ne 0) { throw "Could not stop server process $targetId." }
        }
    }
    if ($WhatIfPreference) {
        Write-Host "Dry run: identified $($targets.Count) application server process trees. No servers were stopped."
    } else {
        Write-Host 'Application server stop commands completed. You can close the seven server tabs.'
    }
    if ($skipped) { exit 1 }
    exit 0
} catch {
    Write-Host "Could not stop all servers: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
