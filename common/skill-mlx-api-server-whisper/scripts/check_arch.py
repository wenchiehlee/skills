import platform
import os
import subprocess

def check_arch():
    print("--- Hardware Info ---")
    print(f"Platform: {platform.platform()}")
    print(f"Machine: {platform.machine()}")
    print(f"Architecture: {platform.architecture()[0]}")
    
    print("\n--- Python Info ---")
    print(f"Python Build Machine: {platform.processor()}")
    print(f"Is 64bit: {platform.architecture()[0] == '64bit'}")
    
    # 檢查是否在 Rosetta 下運行 (macOS only)
    if platform.system() == "Darwin":
        try:
            # sysctl -n sysctl.proc_translated (1 if translated, 0 if native)
            is_translated = subprocess.check_output(["sysctl", "-i", "-n", "sysctl.proc_translated"]).decode().strip()
            if is_translated == "1":
                print("\n--- WARNING: Running under Rosetta 2 (Emulated) ---")
            else:
                print("\n--- Native ARM64 Mode Confirmed ---")
        except Exception:
            # If sysctl doesn't exist or is not supported
            print("\nCould not determine Rosetta status via sysctl.")

if __name__ == "__main__":
    check_arch()
