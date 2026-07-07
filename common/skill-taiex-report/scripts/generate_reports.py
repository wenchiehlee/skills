try:
    import self_update
except ImportError:
    pass


def find_repo_root():
    import os
    curr = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.exists(os.path.join(curr, ".git")) or os.path.exists(os.path.join(curr, "requirements.txt")) or os.path.exists(os.path.join(curr, "CLAUDE.md")):
            return curr
        parent = os.path.dirname(curr)
        if parent == curr:
            return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        curr = parent

def setup_sys_path():
    import os
    import sys
    curr = os.path.dirname(os.path.abspath(__file__))
    repo_root = find_repo_root()
    p1 = os.path.join(repo_root, "scripts")
    if p1 not in sys.path and os.path.exists(p1):
        sys.path.append(p1)
    p2 = os.path.join(repo_root, "skills", "skill-taiex-report", "scripts")
    if p2 not in sys.path and os.path.exists(p2):
        sys.path.append(p2)
    temp = curr
    while temp and os.path.basename(temp) != "skills":
        parent = os.path.dirname(temp)
        if parent == temp:
            break
        temp = parent
    if os.path.basename(temp) == "skills":
        p3 = os.path.join(temp, "common", "skill-taiex-report", "scripts")
        if p3 not in sys.path and os.path.exists(p3):
            sys.path.append(p3)

setup_sys_path()

#!/usr/bin/env python3
import sys
import subprocess

def run(symbol, tag="gemini-cli", period=None):
    # 1. Generate Finguider Report
    cmd1 = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "assembler_finguider.py"), symbol, tag]
    if period: cmd1.append(period)
    print(f"Running: {' '.join(cmd1)}")
    subprocess.run(cmd1)

    # 2. Generate Revenue History
    cmd2 = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "assembler_revenue_history.py"), symbol, tag]
    if period: cmd2.append(period)
    print(f"Running: {' '.join(cmd2)}")
    subprocess.run(cmd2)

    # 3. Update README
    print("Updating README...")
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "update_readme.py")])

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_reports.py <symbol> [tag] [period]")
        sys.exit(1)
    
    symbol = sys.argv[1]
    tag = sys.argv[2] if len(sys.argv) > 2 else "gemini-cli"
    period = sys.argv[3] if len(sys.argv) > 3 else None
    run(symbol, tag, period)