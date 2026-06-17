"""Pytest configuration for WorldCupBench."""

import os
import sys

# Add repo root and src/ to the import path so tests can import project modules
# as either `src.xxx` (used by the API package) or as bare top-level modules.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
