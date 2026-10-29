param(
    [string]$Version = "",
    [switch]$Yes,
    [string]$Targets = "installer,zip",
    [switch]$NoTools
)

$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Pack = Split-Path -Parent $Here
$Root = Split-Path -Parent $Pack
$VersionFile = Join-Path $Root "app\__init__.py"
$AppName = "VeyloraDevice"

function Log($Text) { Write-Host ""; Write-Host "==> $Text" -ForegroundColor Green }
function Warn($Text) { Write-Host "WARNING: $Text" -ForegroundColor Yellow }
function HasTarget($Name) { return (",$Targets,").Contains(",$Name,") }

function Invoke-Native([scriptblock]$Command) {
    $Previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Command } finally { $ErrorActionPreference = $Previous }
}

$Match = Select-String -Path $VersionFile -Pattern '^__version__ = "(.*)"$'
if (-not $Match) { throw "Could not read __version__ from $VersionFile" }
$Current = $Match.Matches[0].Groups[1].Value

if (-not $Version) {
    if ($Yes -or -not [Environment]::UserInteractive) {
        $Version = $Current
    } else {
        Write-Host "Current version: $Current"
        $Answer = Read-Host "Version to build [$Current]"
        $Version = if ($Answer) { $Answer } else { $Current }
    }
}
$Version = $Version.TrimStart("v")
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Invalid version '$Version'. Use the form MAJOR.MINOR.PATCH (for example 1.2.0)."
}

if ($Version -ne $Current) {
    $Text = [IO.File]::ReadAllText($VersionFile)
    $Text = [regex]::Replace($Text, '(?m)^__version__ = "[^"]*"', "__version__ = `"$Version`"")
    [IO.File]::WriteAllText($VersionFile, $Text, (New-Object Text.UTF8Encoding($false)))
    Log "Version updated: $Current -> $Version (written to app\__init__.py)"
} else {
    Log "Building version $Version"
}

$Machine = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x86_64" }
$ShortMachine = if ($Machine -eq "arm64") { "arm64" } else { "x64" }
$Out = Join-Path $Pack "compilation\Windows-$Machine"
$Work = Join-Path $Pack ".work-windows"
$Venv = Join-Path $Pack ".venv-windows"
$Dist = Join-Path $Work "dist"
$Bundle = Join-Path $Dist $AppName

if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
New-Item -ItemType Directory -Force -Path $Out, $Work | Out-Null

Log "Preparing the Python environment"
$Python = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $Python) { throw "Python 3.10 or newer is required (https://www.python.org/downloads/)" }
if (-not (Test-Path $Venv)) { & python -m venv $Venv }
$VenvPython = Join-Path $Venv "Scripts\python.exe"
Invoke-Native { & $VenvPython -m pip install --quiet --upgrade pip }
Invoke-Native { & $VenvPython -m pip install --quiet -r (Join-Path $Root "requirements.txt") pyinstaller }
if ($LASTEXITCODE -ne 0) { throw "pip could not install the dependencies" }

Log "Compiling $AppName $Version with PyInstaller"
$Excludes = @(
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D", "PySide6.QtQml",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech", "PySide6.QtVirtualKeyboard",
    "PySide6.QtHttpServer", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtUiTools", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSpatialAudio", "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets", "tkinter", "scipy", "numpy", "matplotlib"
)
$PyArgs = @(
    "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", $AppName,
    "--icon", (Join-Path $Root "assets\icon.ico"),
    "--distpath", $Dist, "--workpath", (Join-Path $Work "build"), "--specpath", $Work,
    "--add-data", ((Join-Path $Root "assets") + ";assets"),
    "--collect-data", "qfluentwidgets", "--collect-data", "qtawesome",
    "--hidden-import", "qtawesome", "--hidden-import", "darkdetect"
)
foreach ($Module in $Excludes) { $PyArgs += @("--exclude-module", $Module) }
$PyArgs += (Join-Path $Root "main.py")
$LogFile = Join-Path $Work "pyinstaller.log"
Invoke-Native { & $VenvPython @PyArgs *> $LogFile }
if ($LASTEXITCODE -ne 0) { Get-Content $LogFile -Tail 40; throw "PyInstaller failed" }
if (-not (Test-Path (Join-Path $Bundle "$AppName.exe"))) { throw "PyInstaller did not produce $AppName.exe" }

if (-not $NoTools) {
    Log "Bundling the Android platform-tools (adb, fastboot)"
    try {
        $Zip = Join-Path $Work "platform-tools.zip"
        Invoke-WebRequest -UseBasicParsing -Uri "https://dl.google.com/android/repository/platform-tools-latest-windows.zip" -OutFile $Zip
        Expand-Archive -Path $Zip -DestinationPath (Join-Path $Work "tools-src") -Force
        $ToolsTarget = Join-Path $Bundle "_internal\tools"
        New-Item -ItemType Directory -Force -Path $ToolsTarget | Out-Null
        Copy-Item -Recurse -Force (Join-Path $Work "tools-src\platform-tools") (Join-Path $ToolsTarget "platform-tools")
    } catch {
        Warn "Could not download the platform-tools: the app will look for adb in your PATH"
    }
}

$Base = "$AppName-$Version-windows-$ShortMachine"

if (HasTarget "zip") {
    Log "Building the portable .zip"
    $Stage = Join-Path $Work "zip\$Base"
    New-Item -ItemType Directory -Force -Path $Stage | Out-Null
    Copy-Item -Recurse -Force (Join-Path $Bundle "*") $Stage
    Copy-Item (Join-Path $Root "LICENSE"), (Join-Path $Root "README.md"), (Join-Path $Root "THIRD_PARTY_NOTICES.md") $Stage
    Compress-Archive -Path $Stage -DestinationPath (Join-Path $Out "$Base.zip") -Force
}

if (HasTarget "installer") {
    Log "Building the installer (Inno Setup)"
    $Iscc = (Get-Command iscc -ErrorAction SilentlyContinue)
    $IsccPath = if ($Iscc) { $Iscc.Source } else { $null }
    if (-not $IsccPath) {
        foreach ($Candidate in @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
            if (Test-Path $Candidate) { $IsccPath = $Candidate; break }
        }
    }
    if ($IsccPath) {
        & $IsccPath "/Q" "/DAppVersion=$Version" "/DSourceDir=$Bundle" "/DRepoRoot=$Root" "/DOutputDir=$Out" "/DOutputName=$AppName-Setup-$Version-windows-$ShortMachine" (Join-Path $Here "installer.iss")
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
    } else {
        Warn "Inno Setup not found (winget install JRSoftware.InnoSetup): skipping the installer"
    }
}

Log "Writing checksums"
$Lines = Get-ChildItem -File $Out | Where-Object { $_.Name -ne "SHA256SUMS" } | ForEach-Object {
    $Hash = (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower()
    "$Hash  $($_.Name)"
}
[IO.File]::WriteAllText((Join-Path $Out "SHA256SUMS"), (($Lines -join "`n") + "`n"), (New-Object Text.UTF8Encoding($false)))

Remove-Item -Recurse -Force $Work

Log "Done. Packages for $AppName ${Version}:"
Get-ChildItem $Out | Format-Table Name, @{Label = "Size (MB)"; Expression = { [math]::Round($_.Length / 1MB, 1) }} -AutoSize
Write-Host "Output folder: $Out"
Write-Host "Note: the installer is not code signed, so Windows SmartScreen may warn: More info -> Run anyway."
