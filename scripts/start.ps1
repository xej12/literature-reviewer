param(
  [string]$Python,
  [ValidateRange(0, 65535)][int]$Port = 0,
  [switch]$Check,
  [switch]$Demo,
  [switch]$Install
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
if ($Install) {
  $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
  if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creating project virtual environment..."
    & $executable @prefix -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
  $executable = $venvPython
  $prefix = @()
  Write-Host "Installing project dependencies..."
  & $executable -m pip install -r (Join-Path $projectRoot "requirements.txt")
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  # Prefer the archive included in the beginner ZIP; source downloads use
  # the same pinned build and checksum. Ordinary startup never downloads.
  & (Join-Path $PSScriptRoot 'install-poppler.ps1') -Download
}
if ($Check) {
  if ($Demo) { $env:LITERATURE_REVIEWER_DEMO = "1" }
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
if ($Demo) { $env:LITERATURE_REVIEWER_DEMO = "1"; Write-Host "Demo mode: no Zotero directory or model requests will be used." }
Write-Host "Open the local URL printed below in your browser. Keep this window open; Ctrl+C stops the server."
& $executable @prefix @serverArguments
exit $LASTEXITCODE
