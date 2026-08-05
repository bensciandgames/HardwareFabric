# push-changes.ps1
#
# Two modes:
#
# 1) Manual (default)  -  one command instead of three, with a review step:
#      powershell -File "F:\HardwareFabric\scripts\push-changes.ps1" -Message "commit message"
#      powershell -File "F:\HardwareFabric\scripts\push-changes.ps1" -Message "commit message" -Files "backend/app/api/routes/orders.py","db/schema.sql"
#
#    With -Files: stages exactly those repo-root-relative paths.
#    Without -Files: stages all modified/deleted TRACKED files (git add -u)  - 
#    this does NOT pick up new untracked files, so you have to pass -Files
#    to add something new. Shows you what's staged and asks for a y/n
#    confirmation before committing.
#
# 2) Watch (automatic, no prompts)  -  commits and pushes on its own whenever
#    the repo has been quiet for a bit after a change:
#      powershell -File "F:\HardwareFabric\scripts\push-changes.ps1" -Watch
#      powershell -File "F:\HardwareFabric\scripts\push-changes.ps1" -Watch -DebounceSeconds 60
#
#    Watches the whole repo tree (ignoring .git\ itself). After a change,
#    it waits for -DebounceSeconds (default 90) of no further changes
#    before doing anything  -  so a burst of edits/saves becomes ONE commit,
#    not one per keystroke/autosave.
#
#    Stages with `git add -A`, which respects .gitignore  -  real secrets
#    (backend/.env, frontend/.env.local, etc.) are excluded there, not by
#    this script. As a second layer of defense, before committing this
#    script also scans the staged file LIST (not contents) for filenames
#    that look like secrets (.env, .pem, .key, id_rsa, credentials.*,
#    secrets.*)  -  if anything matches, it skips the auto-commit entirely,
#    leaves the files staged, and prints a warning so you can review by
#    hand instead of having it silently pushed.
#
#    Auto-generates a commit message listing the changed files. Runs until
#    you close the window / Ctrl+C. Always pins the repo root with -C, so
#    it doesn't matter what directory the terminal is in when you start it.
#
#    Remember: every push here triggers a live Render redeploy of whichever
#    service changed. This mode is convenient, but it means unfinished /
#    broken edits go live automatically too  -  there's no "are you sure".

param(
    [Parameter(Mandatory = $false)]
    [string]$Message,

    [Parameter(Mandatory = $false)]
    [string[]]$Files,

    [switch]$Watch,

    [int]$DebounceSeconds = 90
)

$ErrorActionPreference = "Stop"
$repoRoot = "F:\HardwareFabric"

# Filename patterns that should never go through on an unattended auto-commit,
# even though .gitignore should already be keeping them out of `git add -A`.
$secretLikePatterns = @(
    '(^|[\\/])\.env($|\.[^.]+$)',
    '\.pem$',
    '\.key$',
    '(^|[\\/])id_rsa',
    '_rsa$',
    '\.pfx$',
    '(^|[\\/])secrets\.',
    '(^|[\\/])credentials\.'
)

function Test-LooksLikeSecret([string]$path) {
    foreach ($pattern in $secretLikePatterns) {
        if ($path -match $pattern) { return $true }
    }
    return $false
}

function Invoke-CommitAndPush([string]$commitMessage) {
    $staged = git -C $repoRoot diff --cached --name-only
    if (-not $staged) {
        return
    }

    Write-Host ""
    Write-Host "--- About to commit these files ---"
    $staged | ForEach-Object { Write-Host "  $_" }

    $risky = $staged | Where-Object { Test-LooksLikeSecret $_ }
    if ($risky) {
        Write-Host ""
        Write-Host "SKIPPING auto-commit  -  these staged files look like they could be secrets:" -ForegroundColor Yellow
        $risky | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
        Write-Host "They're left staged (not committed). Review by hand  -  'git -C `"$repoRoot`" status'  -  then either" -ForegroundColor Yellow
        Write-Host "commit manually if they're safe, or 'git -C `"$repoRoot`" reset' to unstage." -ForegroundColor Yellow
        return
    }

    git -C $repoRoot commit -m "$commitMessage"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Commit failed  -  leaving as-is." -ForegroundColor Red
        return
    }

    git -C $repoRoot push
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Push failed. Commit succeeded locally  -  will retry the push on the next detected change, or run 'git -C `"$repoRoot`" push' manually." -ForegroundColor Red
        return
    }

    Write-Host "Pushed to remote." -ForegroundColor Green
}

if ($Watch) {
    Write-Host "Repo: $repoRoot"
    Write-Host "Watching for changes (debounce: ${DebounceSeconds}s). Ctrl+C to stop."
    Write-Host ""

    $global:HF_LastChangeAt = $null

    $watcher = New-Object System.IO.FileSystemWatcher
    $watcher.Path = $repoRoot
    $watcher.Filter = "*.*"
    $watcher.IncludeSubdirectories = $true
    $watcher.EnableRaisingEvents = $true

    $onChange = {
        $path = $Event.SourceEventArgs.FullPath
        if ($path -like "*\.git\*") { return }
        $global:HF_LastChangeAt = Get-Date
    }

    $handlers = @()
    $handlers += Register-ObjectEvent $watcher "Changed" -Action $onChange
    $handlers += Register-ObjectEvent $watcher "Created" -Action $onChange
    $handlers += Register-ObjectEvent $watcher "Deleted" -Action $onChange
    $handlers += Register-ObjectEvent $watcher "Renamed" -Action $onChange

    try {
        while ($true) {
            Start-Sleep -Seconds 2

            if ($null -eq $global:HF_LastChangeAt) { continue }

            $quietFor = (Get-Date) - $global:HF_LastChangeAt
            if ($quietFor.TotalSeconds -lt $DebounceSeconds) { continue }

            # Consume this batch before doing any work, so changes that land
            # mid-push start a fresh debounce window instead of being dropped.
            $global:HF_LastChangeAt = $null

            git -C $repoRoot add -A
            $changedFiles = git -C $repoRoot diff --cached --name-only
            if (-not $changedFiles) { continue }

            $fileList = @($changedFiles)
            if ($fileList.Count -le 5) {
                $summary = $fileList -join ", "
            } else {
                $summary = ($fileList[0..4] -join ", ") + ", +$($fileList.Count - 5) more"
            }
            $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            $autoMessage = "Auto-sync ${timestamp}: $summary"

            Write-Host "[$timestamp] Change batch detected  -  $($fileList.Count) file(s)." -ForegroundColor Cyan
            Invoke-CommitAndPush $autoMessage
        }
    }
    finally {
        $handlers | ForEach-Object { Unregister-Event -SourceIdentifier $_.Name -ErrorAction SilentlyContinue }
        $watcher.EnableRaisingEvents = $false
        $watcher.Dispose()
    }

    exit 0
}

# --- Manual mode -------------------------------------------------------

if (-not $Message) {
    Write-Host "Manual mode requires -Message. (Use -Watch for automatic mode.)" -ForegroundColor Red
    exit 1
}

Write-Host "Repo: $repoRoot"
Write-Host ""

if ($Files -and $Files.Count -gt 0) {
    Write-Host "Staging specified files:"
    $Files | ForEach-Object { Write-Host "  $_" }
    git -C $repoRoot add -- $Files
}
else {
    Write-Host "No -Files given; staging all modified/deleted tracked files (git add -u)."
    Write-Host "New untracked files are NOT included this way  -  pass -Files to add them explicitly."
    git -C $repoRoot add -u
}

Write-Host ""
Write-Host "--- git status ---"
git -C $repoRoot status --short

$staged = git -C $repoRoot diff --cached --name-only
if (-not $staged) {
    Write-Host ""
    Write-Host "Nothing staged  -  nothing to commit. Exiting."
    exit 0
}

Write-Host ""
Write-Host "--- About to commit these files ---"
$staged | ForEach-Object { Write-Host "  $_" }
Write-Host ""

$confirm = Read-Host "Commit and push with message '$Message'? (y/n)"
if ($confirm -ne "y") {
    Write-Host "Aborted. Files remain staged  -  run 'git -C `"$repoRoot`" reset' to unstage."
    exit 0
}

git -C $repoRoot commit -m "$Message"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Commit failed  -  stopping before push."
    exit 1
}

git -C $repoRoot push
if ($LASTEXITCODE -ne 0) {
    Write-Host "Push failed. The commit succeeded locally  -  check the error above, fix it, then run 'git -C `"$repoRoot`" push' manually."
    exit 1
}

Write-Host ""
Write-Host "Done  -  pushed to remote."
