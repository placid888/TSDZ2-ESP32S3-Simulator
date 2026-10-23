param([string]$Python = '')
$ErrorActionPreference = 'Stop'
$pcRoot = $PSScriptRoot
$address = 'http://127.0.0.1:8765'
try {
    $existing = Invoke-RestMethod "$address/api/state" -TimeoutSec 2
    if ($null -ne $existing.connected) { Start-Process $address; exit 0 }
} catch {}
if (!$Python) {
    $candidates = @(
        "$pcRoot/.venv/Scripts/python.exe",
        'C:/Espressif/python_env/idf5.5_py3.14_env/Scripts/python.exe',
        'C:/Espressif/python_env/idf5.5_py3.11_env/Scripts/python.exe'
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { $Python = $candidate; break }
    }
}
if (!$Python) { throw '請先建立 Python 環境並安裝 pc/requirements.txt，或使用 -Python 指定執行檔。' }
& $Python -c 'import serial'
if ($LASTEXITCODE -ne 0) { throw '這個 Python 尚未安裝 pyserial，請安裝 requirements.txt。' }
Start-Process -FilePath $Python -ArgumentList 'server.py' -WorkingDirectory $pcRoot -WindowStyle Hidden -RedirectStandardOutput "$pcRoot/server.log" -RedirectStandardError "$pcRoot/server-error.log"
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 250
    try {
        Invoke-RestMethod "$address/api/state" -TimeoutSec 1 | Out-Null
        Start-Process $address
        exit 0
    } catch {}
}
throw '控制台未成功啟動，請檢查 server-error.log。'
