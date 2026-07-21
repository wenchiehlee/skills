# Configure Android BaseUnit Gadget HID Support
# Use this to enable/disable HID on specific devices

function Set-AndroidBaseUnitHidSupport {
    param(
        [Parameter(Mandatory=$true)]
        [ValidateSet("Enable", "Disable")]
        [string]$Mode,
        
        [string]$DeviceIP = "192.168.10.1"
    )
    
    $adbTarget = "${DeviceIP}:5555"
    
    Write-Host "`n🔧 CONFIGURING HID SUPPORT: $Mode`n" -ForegroundColor Cyan
    
    # Check device connection
    $devices = adb devices
    if ($devices -notmatch $adbTarget) {
        Write-Host "Connecting to $adbTarget...`n" -ForegroundColor Yellow
        adb connect $adbTarget
        Start-Sleep -Seconds 2
    }
    
    # Get root
    adb -s $adbTarget root | Out-Null
    Start-Sleep -Seconds 2
    
    # Get device serial
    $serial = adb -s $adbTarget shell "getprop ro.serialno"
    Write-Host "Device serial: $serial" -ForegroundColor White
    
    if ($Mode -eq "Disable") {
        Write-Host "`n❌ DISABLING HID (MTU3 QMU workaround)`n" -ForegroundColor Red
        adb -s $adbTarget shell "setprop persist.barco.gadget.enable_hid 0"
        
        Write-Host "Reason: Device-specific MTU3 QMU failure" -ForegroundColor Yellow
        Write-Host "  • Kernel panic when HID is active" -ForegroundColor White
        Write-Host "  • Affects: Serial 1882001373 and similar devices" -ForegroundColor White
        Write-Host "  • Solution: UVC + UAC2 only (no HID)`n" -ForegroundColor White
        
    } else {
        Write-Host "`n✅ ENABLING HID (normal operation)`n" -ForegroundColor Green
        adb -s $adbTarget shell "setprop persist.barco.gadget.enable_hid 1"
        
        Write-Host "HID will provide:" -ForegroundColor Yellow
        Write-Host "  • Teams telemetry (Off-Hook/Mute LED)" -ForegroundColor White
        Write-Host "  • UC App detection" -ForegroundColor White
        Write-Host "  • Connected Device features`n" -ForegroundColor White
    }
    
    # Verify setting
    $hidEnabled = adb -s $adbTarget shell "getprop persist.barco.gadget.enable_hid"
    Write-Host "Current setting: persist.barco.gadget.enable_hid = $hidEnabled" -ForegroundColor Cyan
    
    Write-Host "`n⚠️  Change takes effect on next gadget setup (reboot or re-run setup_uvc.sh)`n" -ForegroundColor Yellow
    
    Write-Host "To apply now:" -ForegroundColor Cyan
    Write-Host "  1. Run: .\start-wired-roomdock.ps1 -Force" -ForegroundColor White
    Write-Host "  2. Or reboot device`n" -ForegroundColor White
}

# Export function
Export-ModuleMember -Function Set-AndroidBaseUnitHidSupport

<#
.SYNOPSIS
Configure HID support on Android BaseUnit devices

.DESCRIPTION
Sets persist.barco.gadget.enable_hid property to control whether HID function
is included in the USB gadget configuration. Use "Disable" on devices with
MTU3 QMU HID issues (e.g., serial 1882001373).

.EXAMPLE
Set-AndroidBaseUnitHidSupport -Mode Disable
Disable HID on the default device (192.168.10.1)

.EXAMPLE
Set-AndroidBaseUnitHidSupport -Mode Enable -DeviceIP 192.168.20.5
Enable HID on a specific device
#>
