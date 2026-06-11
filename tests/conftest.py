"""Pytest configuration for WorldCupBench."""

import os
import sys

# Add src/ to the import path so tests can import project modules.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))
