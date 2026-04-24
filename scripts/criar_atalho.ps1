$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = $ws.CreateShortcut("$desktop\NEXUS CLOSER.lnk")
$lnk.TargetPath = "C:\Users\ferna\Nexus-Closer\nexus-closer\launch.bat"
$lnk.WorkingDirectory = "C:\Users\ferna\Nexus-Closer\nexus-closer"
$lnk.WindowStyle = 7
$lnk.Description = "NEXUS CLOSER - Terminal de Fechamento Elite"
$lnk.Save()
Write-Host "OK - atalho criado na area de trabalho"
