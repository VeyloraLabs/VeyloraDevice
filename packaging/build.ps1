param(
    [string]$Version = "",
    [switch]$Yes,
    [string]$Targets = "installer,zip"
)

& (Join-Path $PSScriptRoot "windows\build.ps1") -Version $Version -Yes:$Yes -Targets $Targets
exit $LASTEXITCODE
