#Requires -Version 5.1
<#
.SYNOPSIS
    Android BaseUnit ADB Skill — reusable helpers for managing dual-ADB (USB + Ethernet) on Android BaseUnit (MT8395).

.DESCRIPTION
    Android BaseUnit exposes two ADB transports whose availability depends on gadget mount state:

        State A  (fresh boot / after reboot):
            USB ADB  ✔  (device serial visible in `adb devices`)
            Eth ADB  ✘  (not yet configured)

        State B  (Ethernet bootstrapped, UVC not yet mounted):
            USB ADB  ✔  (still alive)
            Eth ADB  ✔  (192.168.10.1:5555)

        State C  (UVC/UAC gadget mounted — normal running state):
            USB ADB  ✘  (USB-C1 taken over by gadget functions)
            Eth ADB  ✔  (only remaining path)

    Transition rules encoded in this module:
      • Ethernet ADB MUST be bootstrapped via USB ADB (State A→B) before USB breaks.
      • setup_uvc.sh MUST NOT be run when vendor.usb.adb.uvc=99 (kernel panic risk).
      • After reboot, device always lands in State A — USB ADB must be re-awaited.

    Exported functions:
        Get-AndroidBaseUnitAdbState            — Probe and return current ADB state struct
        Wait-AndroidBaseUnitUsbAdb             — Block until USB ADB device appears
        Connect-AndroidBaseUnitEthernetAdb     — Bootstrap Ethernet ADB via USB ADB
        Invoke-AndroidBaseUnitReboot           — Safe reboot with optional recovery wait
        Invoke-AndroidBaseUnitMount            — Safe UVC/UAC mount (checks sentinel before setup_uvc.sh)

    Import with:
        Import-Module .\scripts\AndroidBaseUnitAdb.psm1

    None of these functions touch start-wired-roomdock.ps1 — that script remains fully
    standalone. This module adds interactive / scripted control on top.
#>

Set-StrictMode -Version Latest

# ─── Internal colour helpers ──────────────────────────────────────────────────
function script:Write-Step { param($m) Write-Host "`n▶  $m" -ForegroundColor Cyan   }
function script:Write-OK   { param($m) Write-Host "   ✔  $m" -ForegroundColor Green  }
function script:Write-Warn { param($m) Write-Host "   ⚠  $m" -ForegroundColor Yellow }
function script:Write-Fail { param($m) Write-Host "   ✘  $m" -ForegroundColor Red    }
function script:Write-Info { param($m) Write-Host "   •  $m" -ForegroundColor Gray   }

# ─── Internal: run adb and return stdout ──────────────────────────────────────
function script:Invoke-Adb {
    param([string[]]$Args)
    & adb @Args 2>&1
}

# ─────────────────────────────────────────────────────────────────────────────
# Get-AndroidBaseUnitAdbState
# ─────────────────────────────────────────────────────────────────────────────
function Get-AndroidBaseUnitAdbState {
    <#
    .SYNOPSIS
        Probe both ADB transports and return the current Android BaseUnit ADB state.

    .PARAMETER DeviceIP
        Ethernet IP of the Android BaseUnit device.  Default: 192.168.10.1

    .OUTPUTS
        PSCustomObject with:
            UsbSerial    [string|$null]  — serial of USB ADB device if detected
            EthConnected [bool]          — whether Ethernet ADB is responsive
            UvcMounted   [bool]          — vendor.usb.adb.uvc == "99"
            BestAdb      [string]        — "-s <id>" args string for the best transport
            State        [string]        — "A" | "B" | "C" | "Unknown"
    #>
    [CmdletBinding()]
    param(
        [string]$DeviceIP = "192.168.10.1"
    )

    $AdbEth = "${DeviceIP}:5555"

    # --- probe USB ADB ---
    $usbSerial = $null
    $rawDevices = & adb devices 2>&1 | Select-Object -Skip 1 |
        Where-Object { $_ -match '\S' -and $_ -notmatch 'offline' }
    $usbLine = $rawDevices | Where-Object { $_ -notmatch '^\d+\.\d+' } | Select-Object -First 1
    if ($usbLine) {
        $usbSerial = ($usbLine -replace '\s.*', '')
    }

    # --- probe Ethernet ADB ---
    $ethConnected = $false
    $ethLine = $rawDevices | Where-Object { $_ -match [regex]::Escape($AdbEth) } | Select-Object -First 1
    if ($ethLine -and $ethLine -notmatch 'offline') {
        # verify it actually responds
        $ping = & adb -s $AdbEth shell "echo ok" 2>&1
        $ethConnected = ($ping -match 'ok')
    }

    # --- read UVC sentinel (prefer Ethernet, fall back to USB) ---
    $uvcMounted = $false
    $bestAdbArgs = @()
    if ($ethConnected) {
        $bestAdbArgs = @("-s", $AdbEth)
        $prop = (& adb -s $AdbEth shell "getprop vendor.usb.adb.uvc" 2>&1).Trim()
        $uvcMounted = ($prop -eq "99")
    } elseif ($usbSerial) {
        $bestAdbArgs = @("-s", $usbSerial)
        $prop = (& adb -s $usbSerial shell "getprop vendor.usb.adb.uvc" 2>&1).Trim()
        $uvcMounted = ($prop -eq "99")
    }

    # --- classify state ---
    $state = switch ($true) {
        { $usbSerial -and -not $ethConnected -and -not $uvcMounted } { "A"; break }
        { $usbSerial -and $ethConnected -and -not $uvcMounted }       { "B"; break }
        { -not $usbSerial -and $ethConnected -and $uvcMounted }       { "C"; break }
        { -not $usbSerial -and $ethConnected -and -not $uvcMounted }  { "C"; break }  # post-mount, streams restarted
        default                                                        { "Unknown" }
    }

    [PSCustomObject]@{
        UsbSerial    = $usbSerial
        EthConnected = $ethConnected
        UvcMounted   = $uvcMounted
        BestAdb      = if ($bestAdbArgs) { $bestAdbArgs -join ' ' } else { $null }
        State        = $state
        DeviceIP     = $DeviceIP
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Wait-AndroidBaseUnitUsbAdb
# ─────────────────────────────────────────────────────────────────────────────
function Wait-AndroidBaseUnitUsbAdb {
    <#
    .SYNOPSIS
        Block until a USB ADB device appears, returning its serial.

    .DESCRIPTION
        Polls `adb devices` every PollingInterval seconds.
        Ignores offline entries and TCP (Ethernet) devices.
        Throws if timeout is reached.

    .PARAMETER TimeoutSec
        Maximum seconds to wait.  Default: 120

    .PARAMETER PollingInterval
        Seconds between polls.  Default: 5

    .OUTPUTS
        [string] USB device serial.

    .EXAMPLE
        $serial = Wait-AndroidBaseUnitUsbAdb -TimeoutSec 60
    #>
    [CmdletBinding()]
    param(
        [int]$TimeoutSec       = 120,
        [int]$PollingInterval  = 5
    )

    Write-Step "Waiting for USB ADB device (timeout ${TimeoutSec}s)..."
    Write-Info "Connect USB-C cable to Android BaseUnit 'laptop-icon' port (USB-C1, no border)."

    $elapsed = 0
    while ($elapsed -lt $TimeoutSec) {
        $lines = & adb devices 2>&1 | Select-Object -Skip 1 |
            Where-Object { $_ -match '\S' -and $_ -notmatch 'offline' }
        $usbLine = $lines | Where-Object { $_ -notmatch '^\d+\.\d+' } | Select-Object -First 1
        if ($usbLine) {
            $serial = ($usbLine -replace '\s.*', '')
            Write-OK "USB ADB device found: $serial"
            return $serial
        }
        Write-Host "   ⏳  (${elapsed}s) No USB ADB device yet..." -ForegroundColor DarkGray
        Start-Sleep -Seconds $PollingInterval
        $elapsed += $PollingInterval
    }

    throw "Wait-AndroidBaseUnitUsbAdb: timeout after ${TimeoutSec}s — no USB ADB device found.`n" +
          "  Check: USB-C connected to laptop-icon port, device booted, USB debugging authorised."
}

# ─────────────────────────────────────────────────────────────────────────────
# Connect-AndroidBaseUnitEthernetAdb
# ─────────────────────────────────────────────────────────────────────────────
function Connect-AndroidBaseUnitEthernetAdb {
    <#
    .SYNOPSIS
        Bootstrap Ethernet ADB on Android BaseUnit using an already-established USB ADB session.

    .DESCRIPTION
        Performs three actions over USB ADB then verifies the Ethernet link:
          1. Assigns 192.168.x.x/24 to eth0 on the device (if not already set).
          2. Sets persist.adb.tcp.port 5555 so adbd listens on TCP after reboot.
          3. Calls `adb connect <IP>:5555` from the host.

        IMPORTANT: Call this BEFORE running Invoke-AndroidBaseUnitMount, because mounting
        the UVC/UAC gadget on USB-C1 kills USB ADB. Ethernet ADB must survive
        that transition.

    .PARAMETER UsbSerial
        Serial returned by Wait-AndroidBaseUnitUsbAdb.  If omitted, auto-detected.

    .PARAMETER DeviceIP
        IP to assign on eth0 and connect to.  Default: 192.168.10.1

    .OUTPUTS
        [bool] $true if Ethernet ADB is connected and responsive.

    .EXAMPLE
        $serial = Wait-AndroidBaseUnitUsbAdb
        $ok = Connect-AndroidBaseUnitEthernetAdb -UsbSerial $serial
    #>
    [CmdletBinding()]
    param(
        [string]$UsbSerial = "",
        [string]$DeviceIP  = "192.168.10.1"
    )

    Write-Step "Bootstrapping Ethernet ADB ($DeviceIP)"

    # Resolve USB serial if not provided
    if (-not $UsbSerial) {
        $lines = & adb devices 2>&1 | Select-Object -Skip 1 |
            Where-Object { $_ -match '\S' -and $_ -notmatch 'offline' }
        $usbLine = $lines | Where-Object { $_ -notmatch '^\d+\.\d+' } | Select-Object -First 1
        if (-not $usbLine) {
            throw "Connect-AndroidBaseUnitEthernetAdb: no USB ADB device available. Run Wait-AndroidBaseUnitUsbAdb first."
        }
        $UsbSerial = ($usbLine -replace '\s.*', '')
        Write-Info "Auto-detected USB serial: $UsbSerial"
    }

    $AdbUsb = @("-s", $UsbSerial)
    $AdbEth = "${DeviceIP}:5555"

    # Step 0 — ensure root access
    & adb @AdbUsb root 2>&1 | Out-Null
    Start-Sleep -Seconds 2

    # Step 1 — assign IP on eth0 (ignore error if already set)
    $ipCmd = "ip addr add ${DeviceIP}/24 dev eth0 2>/dev/null; true"
    & adb @AdbUsb shell $ipCmd | Out-Null

    # Step 2 — persist TCP ADB port
    & adb @AdbUsb shell "setprop persist.adb.tcp.port 5555; setprop service.adb.tcp.port 5555" | Out-Null
    Write-Info "TCP ADB port 5555 set"
    Start-Sleep -Seconds 1

    # Step 3 — connect from host
    $result = & adb connect $AdbEth 2>&1
    Write-Info "adb connect: $result"
    Start-Sleep -Seconds 1

    # Step 4 — verify
    $ping = & adb -s $AdbEth shell "echo ok" 2>&1
    if ($ping -match 'ok') {
        Write-OK "Ethernet ADB responsive at $AdbEth"
        return $true
    }

    Write-Warn "Ethernet ADB connection attempt succeeded but device did not respond."
    Write-Info "Ensure host NIC has 192.168.10.x/24 address on the same LAN segment."
    return $false
}

# ─────────────────────────────────────────────────────────────────────────────
# Invoke-AndroidBaseUnitReboot
# ─────────────────────────────────────────────────────────────────────────────
function Invoke-AndroidBaseUnitReboot {
    <#
    .SYNOPSIS
        Reboot Android BaseUnit safely and optionally wait for USB ADB + Ethernet ADB to recover.

    .DESCRIPTION
        Uses the best available ADB transport (USB preferred, Ethernet fallback).
        After issuing the reboot command:
          • USB ADB disappears (device is rebooting).
          • UVC/UAC gadget is gone — USB ADB returns once Android is back in State A.
          • Ethernet ADB is lost until re-bootstrapped.

        When -WaitForRecovery is set (default), the function:
          1. Waits for USB ADB to reappear (Wait-AndroidBaseUnitUsbAdb).
          2. Requests root.
          3. Re-bootstraps Ethernet ADB (Connect-AndroidBaseUnitEthernetAdb).
        Returns the recovered USB serial.

    .PARAMETER DeviceIP
        Ethernet IP of the device.  Default: 192.168.10.1

    .PARAMETER UsbSerial
        USB ADB serial to use.  Auto-detected if omitted.

    .PARAMETER WaitForRecovery
        If set, block until USB + Ethernet ADB are both healthy after reboot.
        Default: $true

    .PARAMETER RecoveryTimeoutSec
        Seconds to wait for USB ADB to come back after reboot.  Default: 180

    .OUTPUTS
        [string] USB serial after recovery (if WaitForRecovery), or $null.

    .EXAMPLE
        # Simple reboot without waiting
        Invoke-AndroidBaseUnitReboot -WaitForRecovery:$false

        # Reboot and re-establish both ADB paths
        $serial = Invoke-AndroidBaseUnitReboot -DeviceIP "192.168.10.1"
    #>
    [CmdletBinding()]
    param(
        [string]$DeviceIP            = "192.168.10.1",
        [string]$UsbSerial           = "",
        [switch]$WaitForRecovery,       # default $false without explicit set
        [int]   $RecoveryTimeoutSec  = 180
    )

    # Default WaitForRecovery to $true when not explicitly set
    if (-not $PSBoundParameters.ContainsKey('WaitForRecovery')) {
        $WaitForRecovery = $true
    }

    Write-Step "Rebooting Android BaseUnit ($DeviceIP)"

    # Determine best transport
    $adbArgs = @()
    if ($UsbSerial) {
        $adbArgs = @("-s", $UsbSerial)
        Write-Info "Using USB ADB: $UsbSerial"
    } else {
        $AdbEth = "${DeviceIP}:5555"
        $state = Get-AndroidBaseUnitAdbState -DeviceIP $DeviceIP

        if ($state.UsbSerial) {
            $adbArgs = @("-s", $state.UsbSerial)
            Write-Info "Using USB ADB: $($state.UsbSerial)"
        } elseif ($state.EthConnected) {
            $adbArgs = @("-s", $AdbEth)
            Write-Warn "USB ADB not available, using Ethernet ADB: $AdbEth"
            Write-Warn "After reboot, USB ADB will reappear and Ethernet ADB will be lost."
        } else {
            throw "Invoke-AndroidBaseUnitReboot: no ADB transport available. Connect USB or ensure Ethernet ADB is alive."
        }
    }

    & adb @adbArgs reboot 2>&1 | ForEach-Object { Write-Info $_ }
    Write-OK "Reboot command sent"

    if (-not $WaitForRecovery) {
        Write-Info "WaitForRecovery not set — returning immediately."
        return $null
    }

    Write-Info "Waiting for device to come back (USB ADB, up to ${RecoveryTimeoutSec}s)..."
    Start-Sleep -Seconds 5   # give device a moment to actually start rebooting

    $serial = Wait-AndroidBaseUnitUsbAdb -TimeoutSec $RecoveryTimeoutSec -PollingInterval 5
    Write-Info "Device back on USB ADB: $serial"

    # Request root (adbd restarts — serial may change, re-detect)
    Write-Info "Requesting root..."
    & adb -s $serial root 2>&1 | ForEach-Object { Write-Info $_ }
    Start-Sleep -Seconds 3

    # Re-detect USB serial post-root
    $lines = & adb devices 2>&1 | Select-Object -Skip 1 |
        Where-Object { $_ -match '\S' -and $_ -notmatch 'offline' }
    $usbLine = $lines | Where-Object { $_ -notmatch '^\d+\.\d+' } | Select-Object -First 1
    if ($usbLine) { $serial = ($usbLine -replace '\s.*', '') }

    # Re-bootstrap Ethernet
    $ethOk = Connect-AndroidBaseUnitEthernetAdb -UsbSerial $serial -DeviceIP $DeviceIP
    if ($ethOk) {
        Write-OK "Recovery complete: USB=$serial  Eth=${DeviceIP}:5555"
    } else {
        Write-Warn "Recovery: USB ADB OK but Ethernet ADB not confirmed. Check host NIC config."
    }

    return $serial
}

# ─────────────────────────────────────────────────────────────────────────────
# Invoke-AndroidBaseUnitMount
# ─────────────────────────────────────────────────────────────────────────────
function Invoke-AndroidBaseUnitMount {
    <#
    .SYNOPSIS
        Safely mount the UVC/UAC/HID composite gadget on Android BaseUnit.

    .DESCRIPTION
        Implements the full state-aware mount logic:

          SAFE CHECK — reads vendor.usb.adb.uvc before touching anything.

          Case 1: adb.uvc == "99"  (gadget already mounted — State C)
              → USB ADB is dead. Uses Ethernet ADB only.
              → Kills uvc_camera_forward / uvc_still_frame and waits for fd cleanup.
              → Restarts stream processes without touching UDC (no kernel panic risk).
              → DOES NOT run setup_uvc.sh.

          Case 2: adb.uvc != "99"  (gadget not mounted — State A or B)
              → Ensures Ethernet ADB is bootstrapped (calls Connect-AndroidBaseUnitEthernetAdb).
              → Optionally pushes binaries and setup_uvc.sh to the device.
              → Launches setup_uvc.sh in background on device.
              → USB ADB will break during step3 of setup_uvc.sh — expected.
              → Monitors /data/local/tmp/setup_uvc.log via Ethernet ADB until "DONE".

    .PARAMETER DeviceIP
        Ethernet IP of Android BaseUnit.  Default: 192.168.10.1

    .PARAMETER UsbSerial
        USB ADB serial (needed for file push if UVC not yet mounted). Auto-detected if empty.

    .PARAMETER RepoRoot
        Path to the local gadget repo root (where binaries and setup_uvc.sh live).
        Default: parent directory of this module file.

    .PARAMETER SkipPush
        Skip pushing binaries to device (use when files are already present).

    .PARAMETER MacOSMode
        Enable macOS compatibility mode (sets maxburst=0). Default: Windows mode (maxburst=7).

    .PARAMETER MonitorTimeoutSec
        Seconds to wait for setup_uvc.sh to complete.  Default: 90

    .OUTPUTS
        [bool] $true if mount completed successfully (log contains "DONE").

    .EXAMPLE
        # Full mount from scratch (Windows default)
        $serial = Wait-AndroidBaseUnitUsbAdb
        Connect-AndroidBaseUnitEthernetAdb -UsbSerial $serial
        Invoke-AndroidBaseUnitMount -RepoRoot "C:\repo\gadget"

        # macOS mode
        Invoke-AndroidBaseUnitMount -MacOSMode

        # Restart streams on already-mounted device
        Invoke-AndroidBaseUnitMount -SkipPush
    #>
    [CmdletBinding()]
    param(
        [string]$DeviceIP           = "192.168.10.1",
        [string]$UsbSerial          = "",
        [string]$RepoRoot           = "",
        [switch]$SkipPush,
        [switch]$MacOSMode,
        [int]   $MonitorTimeoutSec  = 90
    )

    # Default RepoRoot to the directory containing this module
    if (-not $RepoRoot) {
        $RepoRoot = Split-Path $PSScriptRoot -Parent   # skills/.. → repo root
        if (-not (Test-Path "$RepoRoot\setup_uvc.sh")) {
            $RepoRoot = $PSScriptRoot | Split-Path | Split-Path   # fallback two levels up
        }
    }

    $AdbEth    = "${DeviceIP}:5555"
    $DeviceTmp = "/data/local/tmp"

    Write-Step "Invoke-AndroidBaseUnitMount — checking UVC state"

    # ── Detect current state ───────────────────────────────────────────────────
    $state = Get-AndroidBaseUnitAdbState -DeviceIP $DeviceIP

    # Resolve USB serial
    if (-not $UsbSerial -and $state.UsbSerial) {
        $UsbSerial = $state.UsbSerial
    }
    $AdbUsb = if ($UsbSerial) { @("-s", $UsbSerial) } else { @() }

    # ── Case 1: gadget already mounted (adb.uvc=99) ──────────────────────────
    if ($state.UvcMounted) {
        Write-Warn "UVC gadget already mounted (adb.uvc=99) — safe stream restart only."
        Write-Info "USB ADB is dead; using Ethernet ADB: $AdbEth"

        if (-not $state.EthConnected) {
            throw "Invoke-AndroidBaseUnitMount: gadget mounted but Ethernet ADB unreachable at $AdbEth.`n" +
                  "  USB ADB is also gone. Cannot recover without physical reboot."
        }

        # Build restart script inline (mirrors start-wired-roomdock.ps1 restart path)
        $restartScript = @'
#!/bin/sh
GADGET_VIDEO=$(ls -la /proc/$(pgrep uvc_camera_forward 2>/dev/null | head -1)/fd 2>/dev/null \
    | grep /dev/video | grep -v video0 | awk '{print $NF}' | head -1)
[ -z "$GADGET_VIDEO" ] && \
    GADGET_VIDEO=$(ls /sys/class/video4linux/ | sort -t o -k2 -n | tail -1 | sed 's|^|/dev/|')
echo "gadget_device=$GADGET_VIDEO"
kill -9 $(pgrep uvc_camera_forward) 2>/dev/null
kill -9 $(pgrep uvc_still_frame)    2>/dev/null
sleep 3
nohup /data/local/tmp/uvc_camera_forward /dev/video0 $GADGET_VIDEO \
    > /data/local/tmp/uvc_stream.log 2>&1 &
echo "restarted PID=$! -> $GADGET_VIDEO"
'@
        $tmpScript = "$env:TEMP\android_baseunit_restart_uvc_$([System.IO.Path]::GetRandomFileName()).sh"
        $restartScript | Out-File -FilePath $tmpScript -Encoding ascii -NoNewline
        & adb -s $AdbEth push $tmpScript "$DeviceTmp/restart_uvc.sh" | Out-Null
        Remove-Item $tmpScript -Force -ErrorAction SilentlyContinue

        $out = & adb -s $AdbEth shell "chmod +x $DeviceTmp/restart_uvc.sh && $DeviceTmp/restart_uvc.sh" 2>&1
        $out | ForEach-Object { Write-Info $_ }
        Write-OK "Stream processes restarted (UDC untouched)"
        return $true
    }

    # ── Case 2: gadget not mounted — full setup_uvc.sh flow ──────────────────
    Write-Info "UVC gadget not mounted. Running full setup flow."

    # Ensure Ethernet ADB is ready before USB breaks
    if (-not $state.EthConnected) {
        if (-not $UsbSerial) {
            throw "Invoke-AndroidBaseUnitMount: no USB ADB device and Ethernet ADB not connected.`n" +
                  "  Run: `$serial = Wait-AndroidBaseUnitUsbAdb; Connect-AndroidBaseUnitEthernetAdb -UsbSerial `$serial"
        }
        Write-Info "Ethernet ADB not connected — bootstrapping via USB ADB..."
        $ethOk = Connect-AndroidBaseUnitEthernetAdb -UsbSerial $UsbSerial -DeviceIP $DeviceIP
        if (-not $ethOk) {
            Write-Warn "Ethernet ADB bootstrap did not confirm. Continuing anyway."
        }
    }

    # Push files unless SkipPush
    if (-not $SkipPush) {
        Write-Step "Pushing files to device"
        $filesToPush = @(
            @{ Local = "$RepoRoot\setup_uvc.sh";        Remote = "$DeviceTmp/setup_uvc.sh" }
            @{ Local = "$RepoRoot\uvc_camera_forward";  Remote = "$DeviceTmp/uvc_camera_forward" }
            @{ Local = "$RepoRoot\uvc_still_frame";     Remote = "$DeviceTmp/uvc_still_frame" }
            @{ Local = "$RepoRoot\hid_monitor";         Remote = "$DeviceTmp/hid_monitor" }
            @{ Local = "$RepoRoot\uac2_audio_bridge";   Remote = "$DeviceTmp/uac2_audio_bridge" }
            @{ Local = "$RepoRoot\uac2_monitor";        Remote = "$DeviceTmp/uac2_monitor" }
            @{ Local = "$RepoRoot\static_frame.jpg";    Remote = "$DeviceTmp/static_frame.jpg"; Optional = $true }
        )
        foreach ($f in $filesToPush) {
            if (-not (Test-Path $f.Local)) {
                if ($f.ContainsKey('Optional') -and $f.Optional) {
                    Write-Info "Optional file missing, skipping: $($f.Local)"
                } else {
                    throw "Required file not found: $($f.Local).`n  Build with: zig cc -target aarch64-linux-musl -static ..."
                }
                continue
            }
            Write-Info "Pushing $([System.IO.Path]::GetFileName($f.Local)) ..."
            & adb @AdbUsb push $f.Local $f.Remote
            if ($LASTEXITCODE -ne 0) { throw "Push failed: $($f.Local)" }
        }
        & adb @AdbUsb shell "chmod +x $DeviceTmp/setup_uvc.sh $DeviceTmp/uvc_camera_forward $DeviceTmp/uvc_still_frame $DeviceTmp/hid_monitor $DeviceTmp/uac2_audio_bridge $DeviceTmp/uac2_monitor 2>/dev/null; true"
        Write-OK "Files pushed and permissions set"
    }

    # Launch setup_uvc.sh on device (background — USB ADB will drop mid-way)
    Write-Step "Launching setup_uvc.sh on device"
    Write-Info "Ensuring root access..."
    & adb @AdbUsb root 2>&1 | Out-Null
    Start-Sleep -Seconds 2
    Write-Warn "USB ADB will disconnect ~3-10s into setup (expected — UDC being reconfigured)"
    $setupCmd = "nohup $DeviceTmp/setup_uvc.sh > $DeviceTmp/setup_uvc.log 2>&1 &"
    & adb @AdbUsb shell $setupCmd 2>&1 | Out-Null
    Write-OK "setup_uvc.sh launched in background"

    # Monitor log via Ethernet ADB
    Write-Step "Monitoring setup_uvc.log via Ethernet ADB ($AdbEth)"
    Write-Info "Waiting for USB drop then switching to Ethernet ADB..."
    Start-Sleep -Seconds 8

    $elapsed = 0
    $interval = 3
    $lastLog = ""
    $done = $false

    while ($elapsed -lt $MonitorTimeoutSec) {
        # Try to re-connect Ethernet ADB if needed
        $ethCheck = & adb devices 2>&1 | Select-String $AdbEth
        if (-not $ethCheck) {
            & adb connect $AdbEth 2>&1 | Out-Null
        }

        $log = & adb -s $AdbEth shell "cat $DeviceTmp/setup_uvc.log 2>/dev/null" 2>&1
        if ($log -and $log -ne $lastLog) {
            $newLines = ($log -join "`n") -replace ([regex]::Escape(($lastLog -join "`n"))), ""
            $newLines -split "`n" | Where-Object { $_.Trim() } | ForEach-Object { Write-Info $_ }
            $lastLog = $log
        }
        if (($log -join "`n") -match "DONE") {
            $done = $true
            break
        }
        Start-Sleep -Seconds $interval
        $elapsed += $interval
    }

    if ($done) {
        Write-OK "setup_uvc.sh completed — gadget mounted (State C)"
    } else {
        Write-Warn "Monitor timeout after ${MonitorTimeoutSec}s. Last log:"
        $lastLog | Select-Object -Last 5 | ForEach-Object { Write-Info $_ }
    }

    return $done
}

# ─────────────────────────────────────────────────────────────────────────────
# Set-AndroidBaseUnitOsd
# ─────────────────────────────────────────────────────────────────────────────
function Set-AndroidBaseUnitOsd {
    <#
    .SYNOPSIS
        Enable, disable, or configure the OSD overlay on a running Android BaseUnit UVC stream.

    .DESCRIPTION
        Writes /data/local/tmp/uvc_osd.conf on the device then restarts
        uvc_camera_forward so the new config is picked up on the next STREAMON.

        OSD displays 5 lines (green text, right-center, dark background):
            HostOS:  Windows / macOS / Linux / Unknown
            USB:     SuperSpeed (5 Gbps) / HighSpeed (480 Mbps) / FullSpeed
            Time:    2026-06-17 10:44:34 TZ
            UC App:  <Teams/Zoom call state from hid_monitor>
            Vid:     640x480x30.0 MJPEG

        Config values for Frames:
            0      — disabled (default at startup if no config file)
            1-N    — show for N frames then stop  (~30 frames = 1 second)
            99999  — always on (OSD_ALWAYS_ON sentinel)

        Safe on a mounted gadget (State C): restarts only the userspace process,
        never touches the UDC — no kernel panic risk.

    .PARAMETER DeviceIP
        Ethernet IP of Android BaseUnit.  Default: 192.168.10.1

    .PARAMETER Frames
        Number of frames to show OSD.  Use 99999 for always-on.  Use 0 to disable.
        Default: 99999 (always on)

    .PARAMETER Disable
        Convenience switch — equivalent to -Frames 0.

    .EXAMPLE
        # Always-on OSD
        Set-AndroidBaseUnitOsd

        # Show OSD for first 300 frames (~10 s at 30 fps) after each stream start
        Set-AndroidBaseUnitOsd -Frames 300

        # Turn OSD off
        Set-AndroidBaseUnitOsd -Disable
    #>
    [CmdletBinding(DefaultParameterSetName = 'Frames')]
    param(
        [string]$DeviceIP = "192.168.10.1",
        [Parameter(ParameterSetName = 'Frames')]
        [int]   $Frames   = 99999,
        [Parameter(ParameterSetName = 'Disable')]
        [switch]$Disable
    )

    if ($Disable) { $Frames = 0 }

    $AdbEth    = "${DeviceIP}:5555"
    $ConfigPath = "/data/local/tmp/uvc_osd.conf"
    $DeviceTmp  = "/data/local/tmp"

    Write-Step "Set-AndroidBaseUnitOsd — OSD_DISPLAY_FRAMES=$Frames"

    # Verify Ethernet ADB is reachable
    $ping = & adb -s $AdbEth shell "echo ok" 2>&1
    if ($ping -notmatch 'ok') {
        throw "Set-AndroidBaseUnitOsd: Ethernet ADB not reachable at $AdbEth.`n" +
              "  Run Connect-AndroidBaseUnitEthernetAdb first, or check device state with Get-AndroidBaseUnitAdbState."
    }

    # Write config file on device
    & adb -s $AdbEth shell "echo 'OSD_DISPLAY_FRAMES=$Frames' > $ConfigPath"
    $verify = (& adb -s $AdbEth shell "cat $ConfigPath" 2>&1).Trim()
    Write-Info "Config written: $verify"

    # Restart uvc_camera_forward via watchdog — kill it; setup_uvc.sh watchdog loop restarts it
    # SAFE: we are NOT touching UDC. Watchdog is the 'while true' loop in setup_uvc.sh step9.
    Write-Info "Restarting uvc_camera_forward (watchdog will revive it in ~2s)..."
    $restartCmd = @'
GADGET_VIDEO=$(ls -la /proc/$(pgrep uvc_camera_forward 2>/dev/null | head -1)/fd 2>/dev/null \
    | grep /dev/video | grep -v video0 | awk '{print $NF}' | head -1)
[ -z "$GADGET_VIDEO" ] && \
    GADGET_VIDEO=$(ls /sys/class/video4linux/ | sort -t o -k2 -n | tail -1 | sed 's|^|/dev/|')
echo "gadget=$GADGET_VIDEO pid_before=$(pgrep uvc_camera_forward)"
kill $(pgrep uvc_camera_forward) 2>/dev/null
sleep 3
echo "pid_after=$(pgrep uvc_camera_forward)"
'@
    $tmpScript = "$env:TEMP\android_baseunit_osd_restart_$([System.IO.Path]::GetRandomFileName()).sh"
    $restartCmd | Out-File -FilePath $tmpScript -Encoding ascii -NoNewline
    & adb -s $AdbEth push $tmpScript "$DeviceTmp/osd_restart.sh" | Out-Null
    Remove-Item $tmpScript -Force -ErrorAction SilentlyContinue

    $out = & adb -s $AdbEth shell "chmod +x $DeviceTmp/osd_restart.sh && $DeviceTmp/osd_restart.sh" 2>&1
    $out | ForEach-Object { Write-Info $_ }

    if ($Frames -eq 0) {
        Write-OK "OSD disabled — takes effect on next stream start"
    } elseif ($Frames -ge 99999) {
        Write-OK "OSD always-on enabled — visible on next stream start"
    } else {
        Write-OK "OSD enabled for $Frames frames (~$([math]::Round($Frames/30))s at 30fps) per stream start"
    }
}

# ─── Export surface ───────────────────────────────────────────────────────────
Export-ModuleMember -Function @(
    'Get-AndroidBaseUnitAdbState',
    'Wait-AndroidBaseUnitUsbAdb',
    'Connect-AndroidBaseUnitEthernetAdb',
    'Invoke-AndroidBaseUnitReboot',
    'Invoke-AndroidBaseUnitMount',
    'Set-AndroidBaseUnitOsd'
)
