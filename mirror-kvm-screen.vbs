Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
scriptPath = fso.BuildPath(baseDir, "kvm-screen-mirror.py")

shell.Run "pythonw """ & scriptPath & """ --scale 2", 0, False
