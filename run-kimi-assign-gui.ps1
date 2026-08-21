$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "Kimi Activity Assignment"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(520, 190)
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$label = New-Object System.Windows.Forms.Label
$label.Text = "Paste your Kimi API key:"
$label.Location = New-Object System.Drawing.Point(20, 20)
$label.AutoSize = $true
$form.Controls.Add($label)

$keyBox = New-Object System.Windows.Forms.TextBox
$keyBox.Location = New-Object System.Drawing.Point(20, 48)
$keyBox.Size = New-Object System.Drawing.Size(465, 25)
$keyBox.UseSystemPasswordChar = $true
$form.Controls.Add($keyBox)

$runButton = New-Object System.Windows.Forms.Button
$runButton.Text = "Run"
$runButton.Location = New-Object System.Drawing.Point(310, 95)
$runButton.Size = New-Object System.Drawing.Size(80, 30)
$runButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
$form.AcceptButton = $runButton
$form.Controls.Add($runButton)

$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Text = "Cancel"
$cancelButton.Location = New-Object System.Drawing.Point(405, 95)
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
        "Kimi Activity Assignment",
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

$pythonPath = Join-Path $PSScriptRoot ".activity-venv\Scripts\python.exe"
$databasePath = Join-Path $PSScriptRoot "output\pd-management-bulk-fixed.sqlite3"
$workPath = Join-Path $PSScriptRoot "work\activities-filtered"
$command = "& '$pythonPath' -m pd_extractor.activities.cli assign --database '$databasePath' --work '$workPath' --limit 200; Write-Host ''; Read-Host 'Finished. Press Enter to close'"

Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-NoExit", "-Command", $command) `
    -WorkingDirectory $PSScriptRoot
