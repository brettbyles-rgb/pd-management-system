$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "Kimi Revised Activity Pipeline - 200 High"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(560, 220)
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$label = New-Object System.Windows.Forms.Label
$label.Text = "Paste your Kimi API key. The pipeline will run all 3 stages and create Excel output."
$label.Location = New-Object System.Drawing.Point(20, 20)
$label.Size = New-Object System.Drawing.Size(510, 35)
$form.Controls.Add($label)

$keyBox = New-Object System.Windows.Forms.TextBox
$keyBox.Location = New-Object System.Drawing.Point(20, 62)
$keyBox.Size = New-Object System.Drawing.Size(505, 25)
$keyBox.UseSystemPasswordChar = $true
$form.Controls.Add($keyBox)

$runButton = New-Object System.Windows.Forms.Button
$runButton.Text = "Run"
$runButton.Location = New-Object System.Drawing.Point(350, 125)
$runButton.Size = New-Object System.Drawing.Size(80, 30)
$runButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
$form.AcceptButton = $runButton
$form.Controls.Add($runButton)

$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Text = "Cancel"
$cancelButton.Location = New-Object System.Drawing.Point(445, 125)
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
$outputPath = Join-Path $PSScriptRoot "output\activity-assigned-clustered-role-links-revised-high-200.xlsx"

$command = @"
`$ErrorActionPreference = 'Stop'
Write-Host 'Running revised Kimi activity pipeline for 200 PDs on high reasoning...'
Write-Host ''
Write-Host 'Work folder: $workPath'
Write-Host 'Excel output: $outputPath'
Write-Host ''

New-Item -ItemType Directory -Path '$workPath' -Force | Out-Null
Remove-Item -LiteralPath '$workPath\1_extracted.jsonl' -ErrorAction SilentlyContinue
Remove-Item -LiteralPath '$workPath\2_vocabulary.json' -ErrorAction SilentlyContinue
Remove-Item -LiteralPath '$workPath\2_cluster_members.json' -ErrorAction SilentlyContinue
Remove-Item -LiteralPath '$workPath\3_assigned.jsonl' -ErrorAction SilentlyContinue

Write-Host '[1/4] Extracting activities from 200 PDs...'
& '$pythonPath' -m pd_extractor.activities.cli extract --database '$databasePath' --work '$workPath' --limit 200

Write-Host ''
Write-Host '[2/4] Building revised vocabulary, keeping rare activities...'
& '$pythonPath' -m pd_extractor.activities.cli vocab --database '$databasePath' --work '$workPath' --min-count 1

Write-Host ''
Write-Host '[3/4] Assigning clustered activities to 200 PDs...'
& '$pythonPath' -m pd_extractor.activities.cli assign --database '$databasePath' --work '$workPath' --limit 200

Write-Host ''
Write-Host '[4/4] Building Excel workbook...'
& '$nodePath' '$toolPath' --work '$workPath' --output '$outputPath'

Write-Host ''
Write-Host 'Done.'
Write-Host "Excel output: $outputPath"
Write-Host ''
Read-Host 'Press Enter to close'
"@

Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-NoExit", "-Command", $command) `
    -WorkingDirectory $PSScriptRoot
