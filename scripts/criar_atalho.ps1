$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = $ws.CreateShortcut("$desktop\NEXUS CLOSER.lnk")
$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$lnk.TargetPath = Join-Path $ProjectDir "launch.bat"
$lnk.WorkingDirectory = $ProjectDir
$lnk.WindowStyle = 7
$lnk.Description = "NEXUS CLOSER - Terminal de Fechamento Elite"
$lnk.Save()
Write-Host "OK - atalho criado na area de trabalho"
