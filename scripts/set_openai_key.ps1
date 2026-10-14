# Open a local masked dialog; never pass the key through a terminal or chat.
[CmdletBinding()]
param([switch]$Check)
$ErrorActionPreference = 'Stop'
Add-Type -Path (Join-Path $PSScriptRoot 'windows_key_store.cs')

if ($Check) {
    if ([NewsKeyStore]::Exists([NewsKeyStore]::Target)) { Write-Output 'OpenAI credential is configured.' }
    else { Write-Output 'OpenAI credential is not configured.' }
    exit 0
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$form = New-Object System.Windows.Forms.Form
$form.Text = 'AI In the News - OpenAI key'
$form.ClientSize = New-Object System.Drawing.Size(560, 245)
$form.FormBorderStyle = 'FixedDialog'
$form.StartPosition = 'CenterScreen'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$label = New-Object System.Windows.Forms.Label
$label.Text = "Paste your replacement OpenAI API key below.`r`nSaved in Windows Credential Manager for your Windows account.`r`nSaving does not start an embedding run or approve charges."
$label.Location = New-Object System.Drawing.Point(20, 20)
$label.Size = New-Object System.Drawing.Size(520, 65)
$form.Controls.Add($label)

$keyBox = New-Object System.Windows.Forms.TextBox
$keyBox.UseSystemPasswordChar = $true
$keyBox.MaxLength = 1024
$keyBox.Location = New-Object System.Drawing.Point(20, 100)
$keyBox.Size = New-Object System.Drawing.Size(520, 28)
$form.Controls.Add($keyBox)

$status = New-Object System.Windows.Forms.Label
$status.Location = New-Object System.Drawing.Point(20, 140)
$status.Size = New-Object System.Drawing.Size(520, 35)
$status.Text = 'The key is not sent to this chat or written into the repository.'
$form.Controls.Add($status)

$save = New-Object System.Windows.Forms.Button
$save.Text = 'Save key'
$save.Location = New-Object System.Drawing.Point(330, 190)
$save.Size = New-Object System.Drawing.Size(100, 32)
$save.Add_Click({
    if ($keyBox.Text -notmatch '^sk-[A-Za-z0-9_-]{16,}$') {
        $status.Text = 'Enter an OpenAI API key with no spaces or extra text.'
        return
    }
    try {
        [NewsKeyStore]::Save($keyBox.Text, [NewsKeyStore]::Target)
        $keyBox.Clear()
        $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.Close()
    } catch {
        # Never expose exception details or key values in the UI or output.
        $status.Text = 'Windows could not save the credential. No embedding run was started.'
    }
})
$form.Controls.Add($save)
$form.AcceptButton = $save

$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = 'Cancel'
$cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$cancel.Location = New-Object System.Drawing.Point(440, 190)
$cancel.Size = New-Object System.Drawing.Size(100, 32)
$form.Controls.Add($cancel)
$form.CancelButton = $cancel
$form.Add_Shown({ [void]$keyBox.Focus() })
try {
    $result = $form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output 'OpenAI credential saved.' }
    else { Write-Output 'Credential entry cancelled.' }
} finally {
    $keyBox.Clear()
    $form.Dispose()
}
