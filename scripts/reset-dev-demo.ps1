# Reset the dev demo: delete all DEMO returns in the cloud database, so every
# receipt line can be returned again. Runs `manage_tenancy.py
# reset-demo-returns DEMO` as a one-off ECS task with the service's own task
# definition, network and normal task role. Prints no secrets.
#
#   powershell -ExecutionPolicy Bypass -File scripts\reset-dev-demo.ps1

$ErrorActionPreference = "Stop"
$region = "ca-central-1"
$cluster = "autorefund-dev"
$service = "autorefund-dev-core-api"

# Same task definition and network as the running service.
$svc = aws ecs describe-services --region $region --cluster $cluster --services $service `
    --query "services[0]" --output json | ConvertFrom-Json
$net = $svc.networkConfiguration.awsvpcConfiguration
$network = "awsvpcConfiguration={subnets=[$($net.subnets -join ',')]," +
    "securityGroups=[$($net.securityGroups -join ',')],assignPublicIp=$($net.assignPublicIp)}"

# A temp file avoids PowerShell 5.1's broken quoting of inline JSON.
$overrides = Join-Path $env:TEMP "reset-dev-demo-overrides.json"
'{"containerOverrides":[{"name":"core-api","command":["python","manage_tenancy.py","reset-demo-returns","DEMO"]}]}' |
    Set-Content -Path $overrides -Encoding ascii

$task = aws ecs run-task --region $region --cluster $cluster --launch-type FARGATE `
    --task-definition $svc.taskDefinition --network-configuration $network `
    --overrides "file://$overrides" --query "tasks[0].taskArn" --output text
Remove-Item $overrides
$taskId = $task.Split("/")[-1]
Write-Host "Started reset task $taskId, waiting for it to finish..."

aws ecs wait tasks-stopped --region $region --cluster $cluster --tasks $task
$exitCode = aws ecs describe-tasks --region $region --cluster $cluster --tasks $task `
    --query "tasks[0].containers[0].exitCode" --output text
Write-Host "Exit code: $exitCode"
aws logs get-log-events --region $region --log-group-name /ecs/autorefund-dev-core-api `
    --log-stream-name "core-api/core-api/$taskId" --query "events[].message" --output text
exit [int]$exitCode
