param(
    [string[]]$ExePath = @(),
    [string]$ExePathList = "",

    [string]$UdpHost = "127.0.0.1",
    [int]$UdpPort = 19090,
    [int]$UdpPortStep = 1,
    [string]$UdpPortList = "",

    [string]$UdpHostArg = "--host",
    [string]$UdpPortArg = "--port",
    [string]$ExtraArgsLine = "",
    [string]$ExtraArgsList = "",

    [switch]$OnePortForAll,
    [switch]$Wait,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($ExePathList) {
    $fromList = $ExePathList.Split(";", [System.StringSplitOptions]::RemoveEmptyEntries)
    $ExePath += $fromList
}

if ($ExePath.Count -eq 0) {
    throw "Provide at least one executable with -ExePath or -ExePathList."
}

if ($UdpPort -lt 1 -or $UdpPort -gt 65535) {
    throw "UdpPort must be in [1..65535]."
}

$perEcuPorts = @()
if ($UdpPortList) {
    $portItems = $UdpPortList.Split(";", [System.StringSplitOptions]::RemoveEmptyEntries)
    foreach ($p in $portItems) {
        $portValue = [int]$p
        if ($portValue -lt 1 -or $portValue -gt 65535) {
            throw "UdpPortList contains out-of-range port: $portValue"
        }
        $perEcuPorts += $portValue
    }
    if ($perEcuPorts.Count -ne $ExePath.Count) {
        throw "UdpPortList count ($($perEcuPorts.Count)) must match executable count ($($ExePath.Count))."
    }
}

$perEcuExtraArgs = @()
if ($ExtraArgsList) {
    $perEcuExtraArgs = $ExtraArgsList.Split(";", [System.StringSplitOptions]::None)
    if ($perEcuExtraArgs.Count -ne $ExePath.Count) {
        throw "ExtraArgsList count ($($perEcuExtraArgs.Count)) must match executable count ($($ExePath.Count))."
    }
}

$started = @()

for ($i = 0; $i -lt $ExePath.Count; $i++) {
    $exe = $ExePath[$i]
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw "Executable not found: $exe"
    }

    $port = $UdpPort
    if ($perEcuPorts.Count -gt 0) {
        $port = $perEcuPorts[$i]
    } else {
        $port = if ($OnePortForAll) { $UdpPort } else { $UdpPort + ($i * $UdpPortStep) }
    }
    if ($port -lt 1 -or $port -gt 65535) {
        throw "Computed UDP port out of range for '$exe': $port"
    }

    $extraArgsForEcu = $ExtraArgsLine
    if ($perEcuExtraArgs.Count -gt 0) {
        $extraArgsForEcu = $perEcuExtraArgs[$i]
    }

    $argsParts = @()
    if ($UdpHostArg) { $argsParts += $UdpHostArg; $argsParts += $UdpHost }
    if ($UdpPortArg) { $argsParts += $UdpPortArg; $argsParts += "$port" }
    if ($extraArgsForEcu) { $argsParts += $extraArgsForEcu }
    $argLine = ($argsParts -join " ").Trim()

    Write-Host ("[{0}] {1} {2}" -f $i, $exe, $argLine)
    if (-not $DryRun) {
        $proc = Start-Process -FilePath $exe -ArgumentList $argLine -PassThru
        $started += $proc
    }
}

if ($Wait -and -not $DryRun -and $started.Count -gt 0) {
    $started | Wait-Process
}
