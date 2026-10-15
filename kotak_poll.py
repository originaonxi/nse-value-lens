#!/usr/bin/env python3
"""
Kotak Neo live price polling service.
Runs in background, refreshes Nifty 50 / Bank Nifty / India VIX every 5 minutes.
Writes to docs/nifty_live.json for the front-end to read.

Usage:
  py -3 kotak_poll.py          # Start polling (logs to kotak_poll.log)
  py -3 kotak_poll.py --once   # Single refresh and exit
  py -3 kotak_poll.py --stop   # Stop the running polling service
"""

import os
import sys
import json
import time
import signal
import logging
from pathlib import Path
from datetime import datetime
import subprocess

# Setup logging
log_file = Path(__file__).parent / "kotak_poll.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = 30  # 30 seconds — genuine real-time refresh during market hours
PID_FILE = Path(__file__).parent / ".kotak_poll.pid"
OUTPUT_FILE = Path(__file__).parent / "docs" / "nifty_live.json"

def refresh_prices():
    """Call kotak_live.py --refresh, then commit and push nifty_live.json to GitHub."""
    try:
        # Refresh live prices
        result = subprocess.run(
            ["py", "-3", "kotak_live.py", "--refresh"],
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            logger.error(f"Price refresh failed: {result.stderr}")
            return False
        
        logger.info(f"Price refresh OK | {result.stdout.strip()}")
        
        # Commit and push to GitHub only if the live file actually changed (avoids identical 30s commits)
        try:
            subprocess.run(["git", "add", "docs/nifty_live.json"],
                           cwd=Path(__file__).parent, capture_output=True, timeout=10, check=False)
            changed = subprocess.run(["git", "diff", "--cached", "--quiet", "docs/nifty_live.json"],
                                     cwd=Path(__file__).parent, capture_output=True, timeout=10, check=False)
            if changed.returncode == 0:
                logger.info("No price change; skip commit")
            else:
                subprocess.run(["git", "commit", "-m", f"chore: live prices @ {datetime.now().isoformat()}"],
                               cwd=Path(__file__).parent, capture_output=True, timeout=10, check=False)
                subprocess.run(["git", "push", "origin", "master"],
                               cwd=Path(__file__).parent, capture_output=True, timeout=30, check=False)
                logger.info("Committed and pushed nifty_live.json to GitHub")
        except Exception as e:
            logger.warning(f"Git commit/push failed (prices still local): {e}")
        
        return True
    except Exception as e:
        logger.error(f"Exception during refresh: {e}")
        return False


def polling_loop():
    """Main polling loop."""
    logger.info("=== Kotak polling service started ===")
    logger.info(f"Interval: {POLL_INTERVAL}s, Output: {OUTPUT_FILE}")
    
    # Write PID
    PID_FILE.write_text(str(os.getpid()))
    logger.info(f"PID: {os.getpid()}")
    
    try:
        while True:
            refresh_prices()
            logger.info(f"Next refresh in {POLL_INTERVAL}s...")
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        logger.info("=== Polling interrupted by user ===")
    finally:
        if PID_FILE.exists():
            PID_FILE.unlink()

def stop_polling():
    """Stop the running polling service (Windows)."""
    if not PID_FILE.exists():
        logger.info("No polling service running.")
        return
    
    try:
        pid = int(PID_FILE.read_text())
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(1, False, pid)
        ctypes.windll.kernel32.TerminateProcess(handle, -1)
        ctypes.windll.kernel32.CloseHandle(handle)
        PID_FILE.unlink()
        logger.info(f"Polling service (PID {pid}) stopped.")
    except Exception as e:
        logger.error(f"Failed to stop polling: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--once":
            refresh_prices()
            sys.exit(0)
        elif sys.argv[1] == "--stop":
            stop_polling()
            sys.exit(0)
    
    polling_loop()
