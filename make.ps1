param (
    [Parameter(Position = 0)]
    [string]$Target = "help"
)

& "$PSScriptRoot\run.ps1" $Target
