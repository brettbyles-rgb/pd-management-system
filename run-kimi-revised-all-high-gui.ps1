$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "Kimi Revised Activity Pipeline - All Roles High"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(590, 230)
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$label = New-Object System.Windows.Forms.Label
$label.Text = "Paste your Kimi API key. This continues the 200-role run, then rebuilds vocabulary, assignments, Excel output, and database activity tables for all roles."
$label.Location = New-Object System.Drawing.Point(20, 20)
$label.Size = New-Object System.Drawing.Size(540, 45)
$form.Controls.Add($label)

$keyBox = New-Object System.Windows.Forms.TextBox
$keyBox.Location = New-Object System.Drawing.Point(20, 72)
$keyBox.Size = New-Object System.Drawing.Size(535, 25)
$keyBox.UseSystemPasswordChar = $true
$form.Controls.Add($keyBox)

$runButton = New-Object System.Windows.Forms.Button
$runButton.Text = "Run"
$runButton.Location = New-Object System.Drawing.Point(380, 135)
$runButton.Size = New-Object System.Drawing.Size(80, 30)
$runButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
$form.AcceptButton = $runButton
$form.Controls.Add($runButton)

$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Text = "Cancel"
$cancelButton.Location = New-Object System.Drawing.Point(475, 135)
$cancelButton.Size = New-Object System.Drawing.Size(80, 30)
$cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.CancelButton = $cancelButton
$form.Controls.Add($cancelButton)

$form.Add_Shown({ $keyBox.Focus() })
$result = $form.ShowDialog()

if ($result -ne [System.Windows.Forms.DialogResult]::OK) {
    exit 0
}

$kimiKey = $keyBox.Text.Trim()
if ([string]::IsNullOrWhiteSpace($kimiKey)) {
    [System.Windows.Forms.MessageBox]::Show(
        "No key was entered.",
        "Kimi Revised Activity Pipeline",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Warning
    ) | Out-Null
    exit 1
}

$env:MOONSHOT_API_KEY = $kimiKey
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
$env:ACTIVITY_LLM_BACKEND = "kimi"
$env:LLM_MODEL = "kimi-k3"
$env:KIMI_REASONING_EFFORT = "high"
$env:NODE_PATH = "C:\Users\BrettB\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules"

$pythonPath = Join-Path $PSScriptRoot ".activity-venv\Scripts\python.exe"
$nodePath = "C:\Users\BrettB\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$databasePath = Join-Path $PSScriptRoot "output\pd-management-bulk-fixed.sqlite3"
$workPath = Join-Path $PSScriptRoot "work\activities-revised-200-high"
$toolPath = Join-Path $PSScriptRoot "tools\build_activity_assigned_claude_workbook.mjs"
$jsonOutputPath = Join-Path $PSScriptRoot "output\activities-revised-high-all.json"
$excelOutputPath = Join-Path $PSScriptRoot "output\activity-assigned-clustered-role-links-revised-high-all.xlsx"
$targetClusters = 700

$command = @"
`$ErrorActionPreference = 'Stop'
Write-Host 'Running revised Kimi activity pipeline for all roles on high reasoning...'
Write-Host ''
Write-Host 'Database: $databasePath'
Write-Host 'Work folder: $workPath'
Write-Host 'Excel output: $excelOutputPath'
Write-Host 'JSON output: $jsonOutputPath'
Write-Host ''

New-Item -ItemType Directory -Path '$workPath' -Force | Out-Null

Write-Host '[1/6] Continuing Stage 1 extraction across all roles...'
Write-Host '      Existing extracted roles in this work folder will be skipped.'
& '$pythonPath' -m pd_extractor.activities.cli extract --database '$databasePath' --work '$workPath'

Write-Host ''
Write-Host '[2/6] Clearing stale 200-role Stage 2 and Stage 3 outputs...'
Remove-Item -LiteralPath '$workPath\2_vocabulary.json' -ErrorAction SilentlyContinue
Remove-Item -LiteralPath '$workPath\2_cluster_members.json' -ErrorAction SilentlyContinue
Remove-Item -LiteralPath '$workPath\3_assigned.jsonl' -ErrorAction SilentlyContinue

Write-Host ''
Write-Host '[3/6] Building all-role vocabulary, keeping rare activities...'
& '$pythonPath' -m pd_extractor.activities.cli vocab --database '$databasePath' --work '$workPath' --min-count 1 --clusters $targetClusters

Write-Host ''
Write-Host '[4/6] Assigning clustered activities to all roles...'
& '$pythonPath' -m pd_extractor.activities.cli assign --database '$databasePath' --work '$workPath'

Write-Host ''
Write-Host '[5/6] Exporting JSON and importing activities into the database...'
& '$pythonPath' -m pd_extractor.activities.cli export --database '$databasePath' --work '$workPath' --export-path '$jsonOutputPath'
& '$pythonPath' -m pd_extractor.activities.cli import-db --database '$databasePath' --export-path '$jsonOutputPath'

Write-Host ''
Write-Host '[6/6] Building Excel workbook...'
& '$nodePath' --max-old-space-size=8192 '$toolPath' --work '$workPath' --output '$excelOutputPath'

Write-Host ''
Write-Host 'Done.'
Write-Host "Excel output: $excelOutputPath"
Write-Host "JSON output: $jsonOutputPath"
Write-Host 'Database activity tables updated.'
Write-Host ''
Read-Host 'Press Enter to close'
"@

Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-NoExit", "-Command", $command) `
    -WorkingDirectory $PSScriptRoot
