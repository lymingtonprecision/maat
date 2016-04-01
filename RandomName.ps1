param (
  [string]$leftsPath = "./names/lefts.txt",
  [string]$rightsPath = "./names/rights.txt"
)

$lefts = Get-Content $leftsPath
$rights = Get-Content $rightsPath

($lefts | Get-Random) + "-" + ($rights | Get-Random)
