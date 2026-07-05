#!/usr/bin/env python3
"""
Wrapper script for skill-revenue-predict.
This script executes the original generate_revenue_predict.py located in the biztrends.TW repository.
It ensures the skill can be run without duplicating the large source code.
"""
import os
import runpy

# Determine the absolute path to the original script
CURRENT_DIR = os.path.abspath(os.path.dirname(__file__))
# Navigate up three levels to the repository root and then into biztrends.TW/scripts
ORIGINAL_SCRIPT = os.path.abspath(os.path.join(CURRENT_DIR, "..", "..", "..", "biztrends.TW", "scripts", "generate_revenue_predict.py"))

if not os.path.isfile(ORIGINAL_SCRIPT):
    raise FileNotFoundError(f"Original script not found at {ORIGINAL_SCRIPT}")

# Execute the original script in its own namespace
runpy.run_path(ORIGINAL_SCRIPT, run_name="__main__")
