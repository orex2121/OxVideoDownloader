$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$repository = "orex2121/OxVideoDownloader"
$branch = "main"
$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$workDir = Join-Path ([IO.Path]::GetTempPath()) ("OxVideoDownloader-update-" + [guid]::NewGuid().ToString("N"))
$archive = Join-Path $workDir "source.zip"
$extractDir = Join-Path $workDir "source"
$downloadUrl = "https://codeload.github.com/$repository/zip/refs/heads/$branch"

try {
    Write-Host "[1/4] Downloading the latest source from GitHub..."
    New-Item -ItemType Directory -Path $extractDir -Force | Out-Null
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri $downloadUrl -OutFile $archive

    Write-Host "[2/4] Verifying and extracting the update..."
    Expand-Archive -LiteralPath $archive -DestinationPath $extractDir -Force
    $sourceDir = Get-ChildItem -LiteralPath $extractDir -Directory | Select-Object -First 1
    if (-not $sourceDir -or
        -not (Test-Path -LiteralPath (Join-Path $sourceDir.FullName "oxvideodownloader.py")) -or
        -not (Test-Path -LiteralPath (Join-Path $sourceDir.FullName "requirements.txt"))) {
        throw "The downloaded archive is not a valid OxVideoDownloader repository."
    }

    Write-Host "[3/4] Updating application files..."
    $files = @(
        ".gitignore",
        "INSTALL.bat",
        "OxVideo Downloader.bat",
        "OxVideo Downloader.exe",
        "README.md",
        "requirements.txt",
        "oxvideodownloader.py"
    )
    $directories = @("assets", "docs", "launcher", "local", "oxvd")

    foreach ($name in $files) {
        $source = Join-Path $sourceDir.FullName $name
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination (Join-Path $appDir $name) -Force
        }
    }
    foreach ($name in $directories) {
        $source = Join-Path $sourceDir.FullName $name
        if (Test-Path -LiteralPath $source) {
            Copy-Item -LiteralPath $source -Destination $appDir -Recurse -Force
        }
    }

    Write-Host "[4/4] Updating Python dependencies..."
    $python = Join-Path $appDir "python\python.exe"
    if (Test-Path -LiteralPath $python) {
        & $python -m pip install --disable-pip-version-check --upgrade -r (Join-Path $appDir "requirements.txt")
        if ($LASTEXITCODE -ne 0) {
            throw "pip could not update the application dependencies."
        }
        & $python -c "import tkinter, yt_dlp, PIL, curl_cffi; print('Environment verification: OK')"
        if ($LASTEXITCODE -ne 0) {
            throw "The updated Python environment did not pass verification."
        }
    } else {
        Write-Host "Portable Python is not installed. Run INSTALL.bat before starting the application."
    }

    Write-Host "Updated from https://github.com/$repository (branch: $branch)."
    exit 0
}
catch {
    Write-Error $_
    exit 1
}
finally {
    if (Test-Path -LiteralPath $workDir) {
        Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
