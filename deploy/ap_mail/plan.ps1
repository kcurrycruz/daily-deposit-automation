param([Parameter(Mandatory=$true)][string]$VariablesFile)
$ErrorActionPreference = 'Stop'
$taskDirectory = $PSScriptRoot
$taskVariables = (Resolve-Path -LiteralPath $VariablesFile).Path
# Only public target IDs and secret references belong in this file. Never token values.
& terraform "-chdir=$taskDirectory" init -input=false
if ($LASTEXITCODE -ne 0) { throw 'Terraform initialization failed.' }
& terraform "-chdir=$taskDirectory" fmt -check
if ($LASTEXITCODE -ne 0) { throw 'Terraform formatting failed.' }
& terraform "-chdir=$taskDirectory" validate
if ($LASTEXITCODE -ne 0) { throw 'Terraform validation failed.' }
& terraform "-chdir=$taskDirectory" plan -input=false "-var-file=$taskVariables"
if ($LASTEXITCODE -ne 0) { throw 'Terraform planning failed.' }
Write-Output 'Plan only. No infrastructure was applied. Both queue and schedule are configured paused.'
