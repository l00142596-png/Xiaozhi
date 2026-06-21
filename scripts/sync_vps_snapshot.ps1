param(
  [string]$Timestamp = (Get-Date -Format 'yyyyMMdd_HHmmss'),
  [string]$VpsHost = '47.82.148.97',
  [string]$VpsUser = 'root',
  [string]$KeyPath = 'C:\Users\Administrator\.ssh\tab5.pem',
  [string]$RepoRoot = 'C:\Users\Administrator\VS511\xiaozhi-server',
  [string]$LocalBackupRoot = 'C:\Users\Administrator\VS511'
)

$ErrorActionPreference = 'Stop'

$fullBackup = Join-Path $LocalBackupRoot "backup_$Timestamp"
$repoBackup = Join-Path $RepoRoot "backups\vps_$Timestamp"
$ssh = 'C:\Windows\System32\OpenSSH\scp.exe'
$sshBin = 'C:\Windows\System32\OpenSSH\ssh.exe'

New-Item -ItemType Directory -Force -Path $fullBackup, $repoBackup, (Join-Path $repoBackup 'prompts'), (Join-Path $repoBackup 'systemd') | Out-Null

$remoteBase = "/opt/xiaozhi-mcp"
$remoteFiles = @(
  @{ Remote = "$remoteBase/kb_server_v2.py"; Local = 'kb_server_v2.py'; Repo = 'kb_server_v2.py' },
  @{ Remote = "$remoteBase/xiaozhi.config.json"; Local = 'xiaozhi.config.json'; Repo = 'xiaozhi.config.json' },
  @{ Remote = "$remoteBase/xiaozhi.cache.json"; Local = 'xiaozhi.cache.json'; Repo = 'xiaozhi.cache.json' },
  @{ Remote = "$remoteBase/knowledge.json"; Local = 'knowledge.json'; Repo = 'knowledge.json' },
  @{ Remote = "$remoteBase/railway_safety_workflow_state.json"; Local = 'railway_safety_workflow_state.json'; Repo = 'railway_safety_workflow_state.json' },
  @{ Remote = "$remoteBase/prompts/default.md"; Local = 'prompts.default.md'; Repo = 'prompts/default.md' },
  @{ Remote = '/etc/systemd/system/xiaozhi-kb.service'; Local = 'xiaozhi-kb.service'; Repo = 'systemd/xiaozhi-kb.service' },
  @{ Remote = '/etc/systemd/system/xiaozhi-client.service'; Local = 'xiaozhi-client.service'; Repo = 'systemd/xiaozhi-client.service' },
  @{ Remote = '/opt/xiaozhi-mcp/xiaozhi-mcp.env.example'; Local = 'xiaozhi-mcp.env.example'; Repo = 'xiaozhi-mcp.env.example' }
)

foreach ($f in $remoteFiles) {
  & $ssh -i $KeyPath "$VpsUser@$VpsHost:$($f.Remote)" (Join-Path $fullBackup $f.Local) | Out-Null
  Copy-Item (Join-Path $fullBackup $f.Local) (Join-Path $repoBackup $f.Repo) -Force
  Copy-Item (Join-Path $fullBackup $f.Local) (Join-Path $RepoRoot "aliyun-xiaozhi-mcp\$($f.Repo)") -Force
}

# Secrets stay local only.
& $ssh -i $KeyPath "$VpsUser@$VpsHost:/etc/xiaozhi-mcp.env" (Join-Path $fullBackup 'xiaozhi-mcp.env') | Out-Null

$readme = @"
# VPS Snapshot $Timestamp

This folder is a GitHub-safe snapshot of the current Xiaozhi MCP VPS configuration.

Included:
- kb_server_v2.py
- xiaozhi-mcp.env.example
- xiaozhi.config.json
- xiaozhi.cache.json
- knowledge.json
- railway_safety_workflow_state.json
- prompts/default.md
- systemd/xiaozhi-kb.service
- systemd/xiaozhi-client.service

Not committed:
- /etc/xiaozhi-mcp.env (contains secrets)

Full local copy with secrets:
- $fullBackup
"@

Set-Content -Path (Join-Path $repoBackup 'README.md') -Value $readme -Encoding UTF8

Push-Location $RepoRoot
try {
  & git add "backups/vps_$Timestamp" "aliyun-xiaozhi-mcp"
  & git commit -m "Sync VPS Xiaozhi MCP snapshot $Timestamp"
  & git push origin master
} finally {
  Pop-Location
}

