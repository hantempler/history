import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from auto_run_masterpiece import run_pipeline

if __name__ == "__main__":
    target = sys.argv[1].strip() if len(sys.argv) > 1 else None
    run_pipeline(target)
