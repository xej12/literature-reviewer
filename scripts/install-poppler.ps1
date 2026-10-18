param([switch]$Download)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$vendorRoot = Join-Path $projectRoot 'vendor\poppler'
$runtime = Join-Path $vendorRoot 'runtime'
$archive = Join-Path $vendorRoot 'windows-x64.zip'
$manifest = Get-Content -Raw -LiteralPath (Join-Path $vendorRoot 'manifest.json') | ConvertFrom-Json

if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64' -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
  throw 'The bundled Poppler package requires Windows x64.'
}

function Find-PopplerBin([string]$Root) {
  if (-not (Test-Path -LiteralPath $Root)) { return $null }
  foreach ($tool in @(Get-ChildItem -LiteralPath $Root -Filter 'pdfinfo.exe' -File -Recurse)) {
    if (Test-Path -LiteralPath (Join-Path $tool.DirectoryName 'pdftoppm.exe')) { return $tool.DirectoryName }
  }
  return $null
}

if (-not (Find-PopplerBin $runtime)) {
  if (-not (Test-Path -LiteralPath $archive)) {
    if (-not $Download) { throw 'Poppler archive missing. Run setup.cmd with an internet connection.' }
    Write-Host "Downloading Poppler $($manifest.version) (about 42 MB)..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $temporaryArchive = "$archive.download"
    try {
      Invoke-WebRequest -UseBasicParsing -Uri $manifest.url -OutFile $temporaryArchive
      if ((Get-FileHash -LiteralPath $temporaryArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.sha256) {
        throw 'Poppler download failed its SHA256 integrity check. Please retry setup.'
      }
      Move-Item -LiteralPath $temporaryArchive -Destination $archive -Force
    } finally {
      if (Test-Path -LiteralPath $temporaryArchive) { Remove-Item -LiteralPath $temporaryArchive -Force }
    }
  }
  if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.sha256) {
    throw 'Poppler archive failed its SHA256 integrity check. Download a fresh package.'
  }
  $staging = Join-Path $vendorRoot ('.install-' + [Guid]::NewGuid().ToString('N'))
  Write-Host 'Unpacking bundled Poppler...'
  Expand-Archive -LiteralPath $archive -DestinationPath $staging
  if (-not (Find-PopplerBin $staging)) { throw 'Poppler archive is missing pdfinfo.exe or pdftoppm.exe.' }
  # Leave any incomplete previous install intact for troubleshooting.
  if (Test-Path -LiteralPath $runtime) { throw "Incomplete Poppler install at $runtime. Rename this folder and retry setup." }
  Move-Item -LiteralPath $staging -Destination $runtime
}
$bin = Find-PopplerBin $runtime
foreach ($name in @('pdfinfo.exe', 'pdftoppm.exe')) {
  & (Join-Path $bin $name) -v
  if ($LASTEXITCODE -ne 0) { throw "Poppler tool $name could not start (exit $LASTEXITCODE)." }
}
Write-Host "Poppler ready: $bin (no system PATH changes required)."
