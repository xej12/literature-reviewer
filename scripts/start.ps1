$ErrorActionPreference = "Stop"
$python = "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$server = Join-Path $PSScriptRoot "server.py"
if (-not (Test-Path $python)) {
  throw "Bundled Python runtime not found: $python"
}
& $python $server
