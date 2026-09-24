param(
    [string]$Distribution = 'Ubuntu',
    [string]$EvidenceDirectory = (Join-Path $PSScriptRoot '../artifacts/windows-distribution')
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true

function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit $LASTEXITCODE" }
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$status = & git -C $repo status --porcelain
if ($LASTEXITCODE -ne 0 -or $status) { throw 'Commit the verifier before collecting release evidence.' }
$commit = & git -C $repo rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify verifier commit.' }
$os = Get-CimInstance Win32_OperatingSystem
$distro = Get-ChildItem HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss |
    Get-ItemProperty | Where-Object DistributionName -EQ $Distribution
if (@($distro).Count -ne 1 -or $distro.Version -ne 2) { throw 'An installed WSL2 distribution is required.' }
$desktop = & docker version --format '{{json .}}' | ConvertFrom-Json
if ($LASTEXITCODE -ne 0 -or $desktop.Server.Platform.Name -notlike 'Docker Desktop*') {
    throw 'Start the real Docker Desktop Linux engine.'
}
New-Item -ItemType Directory -Force $EvidenceDirectory | Out-Null
$evidence = (Resolve-Path $EvidenceDirectory).Path
$hostFile = Join-Path $evidence 'windows-host.json'
[ordered]@{
    os = $os.Caption
    version = $os.Version
    build = $os.BuildNumber
    architecture = $os.OSArchitecture
    distribution = $Distribution
    wsl_version = $distro.Version
    desktop = $desktop.Server.Platform.Name
    runner_name = $env:RUNNER_NAME
    workflow_run_id = $env:GITHUB_RUN_ID
    verifier_commit = $commit
    captured_at_utc = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json | Set-Content -Encoding utf8 $hostFile
$wslRepo = & wsl -d $Distribution -- wslpath -a $repo
$wslEvidence = & wsl -d $Distribution -- wslpath -a $evidence
$wslHome = & wsl -d $Distribution -- printenv HOME
if ($LASTEXITCODE -ne 0 -or $wslHome -notmatch '^/home/[^/]+$') { throw 'Expected a non-root WSL home.' }
$runRoot = "$wslHome/.local/share/issue208/runs/$([guid]::NewGuid().ToString('N'))"
Invoke-Checked wsl @('-d', $Distribution, '--', 'mkdir', '-p', $runRoot)
Invoke-Checked wsl @('-d', $Distribution, '--', 'git', '-c', 'core.autocrlf=false', 'clone', '--no-hardlinks', $wslRepo, "$runRoot/source")
Invoke-Checked wsl @('-d', $Distribution, '--', 'git', '-C', "$runRoot/source", 'checkout', '--detach', $commit)
Invoke-Checked wsl @('-d', $Distribution, '--', 'python3', "$runRoot/source/scripts/verify_windows_distribution.py", '--repo', "$runRoot/source", '--host', "$wslEvidence/windows-host.json", '--evidence', $wslEvidence)
