param(
  [string]$Python,
  [ValidateRange(0, 65535)][int]$Port = 0,
  [switch]$Check
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path $PSScriptRoot -Parent
$candidates = @()
if ($Python) {
  $candidates += @{ Command = $Python; Prefix = @() }
} else {
  # Prefer this checkout's isolated environment, then the user's own Python.
  $candidates += @{ Command = (Join-Path $projectRoot ".venv\Scripts\python.exe"); Prefix = @() }
  $candidates += @{ Command = "python"; Prefix = @() }
  $candidates += @{ Command = "py"; Prefix = @("-3") }
  # Retain compatibility with an existing Codex-managed installation.
  $candidates += @{ Command = (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"); Prefix = @() }
}

$selected = $null
foreach ($candidate in $candidates) {
  $executable = Get-Command $candidate.Command -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $executable) { continue }
  $prefix = $candidate.Prefix
  try {
    & $executable.Source @prefix -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
      $selected = @{ Command = $executable.Source; Prefix = $prefix }
      break
    }
  } catch { continue }
}

if (-not $selected) {
  Write-Host "Python 3.11+ was not found. Install Python and follow docs/installation.md."
  exit 1
}

$prefix = $selected.Prefix
$executable = $selected.Command
if ($Check) {
  & $executable @prefix (Join-Path $PSScriptRoot "check_environment.py")
  exit $LASTEXITCODE
}

$dependencyExit = 1
try {
  & $executable @prefix -c "import pypdf, pdf2image, PIL" 2>$null
  $dependencyExit = $LASTEXITCODE
} catch { }
if ($dependencyExit -ne 0) {
  Write-Host "Missing Python dependencies. From the project folder, run:"
  Write-Host "  & '$executable' $($prefix -join ' ') -m pip install -r requirements.txt"
  exit 1
}

$serverArguments = @((Join-Path $PSScriptRoot "server.py"))
if ($Port -gt 0) { $serverArguments += "$Port" }
Write-Host "Open the local URL printed below in your browser. Keep this window open; Ctrl+C stops the server."
& $executable @prefix @serverArguments
exit $LASTEXITCODE
