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

POLL_INTERVAL = 120  # 2 minutes: each push redeploys GitHub Pages (~1 min), so faster only queues deploys
KRONOS_EVERY = 15 * 60  # intraday Kronos re-run cadence (seconds); one run is ~60 s on CPU
_last_kronos = 0.0
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

        # Intraday Kronos (today's live Kotak bar appended) at most every 15 min; it takes ~60 s on CPU.
        global _last_kronos
        if time.time() - _last_kronos >= KRONOS_EVERY:
            kr = subprocess.run(["py", "-3", "kronos_live.py", "--samples", "20"], cwd=Path(__file__).parent,
                                capture_output=True, text=True, timeout=400)
            if kr.returncode == 0:
                _last_kronos = time.time()
                logger.info(kr.stdout.strip().splitlines()[-1])
            else:
                logger.error(f"Live Kronos failed: {kr.stderr[-300:]}")

        # Live trade cards (Kotak legs + payoff maths + Kronos + backtest). Optional: index prices still publish.
        cards = subprocess.run(["py", "-3", "live_cards.py"], cwd=Path(__file__).parent,
                               capture_output=True, text=True, timeout=120)
        if cards.returncode != 0:
            logger.error(f"Live cards failed: {cards.stderr[-400:]}")
        else:
            logger.info(cards.stdout.strip().splitlines()[-1] if cards.stdout.strip() else "Live cards OK")

        # Commit and push to GitHub only if the live files actually changed (avoids identical commits)
        try:
            subprocess.run(["git", "add", "docs/nifty_live.json", "docs/live_cards.json", "docs/kronos_live_nsei.json"],
                           cwd=Path(__file__).parent, capture_output=True, timeout=10, check=False)
            changed = subprocess.run(["git", "diff", "--cached", "--quiet", "docs/nifty_live.json", "docs/live_cards.json", "docs/kronos_live_nsei.json"],
                                     cwd=Path(__file__).parent, capture_output=True, timeout=10, check=False)
            if changed.returncode == 0:
                logger.info("No price change; skip commit")
            else:
                subprocess.run(["git", "commit", "-m", f"chore: live prices + cards @ {datetime.now().isoformat()}"],
                               cwd=Path(__file__).parent, capture_output=True, timeout=10, check=False)
                subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "master"],
                               cwd=Path(__file__).parent, capture_output=True, timeout=60, check=False)
                pushed = subprocess.run(["git", "push", "origin", "HEAD:master"],
                                        cwd=Path(__file__).parent, capture_output=True, text=True, timeout=60, check=False)
                if pushed.returncode == 0:
                    logger.info("Committed and pushed live prices + cards to GitHub")
                else:
                    logger.warning(f"Push failed: {pushed.stderr.strip()[-200:]}")
        except Exception as e:
            logger.warning(f"Git commit/push failed (prices still local): {e}")
        
        return True
    except Exception as e:
        logger.error(f"Exception during refresh: {e}")
        return False


def market_open(now=None):
    """True on NSE trading days between 09:15 and 15:35 IST (5 min after close for the final print)."""
    from datetime import timezone, timedelta
    ist = (now or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=5, minutes=30)))
    try:
        cal = json.loads((Path(__file__).parent / "data" / "hhhl_calendar.json").read_text(encoding="utf-8"))
        holidays = set(cal.get("holidays", []))
    except (OSError, ValueError):
        holidays = set()
    if ist.weekday() >= 5 or ist.date().isoformat() in holidays:
        return False
    minutes = ist.hour * 60 + ist.minute
    return 9 * 60 + 15 <= minutes <= 15 * 60 + 35


def polling_loop():
    """Main polling loop."""
    logger.info("=== Kotak polling service started ===")
    logger.info(f"Interval: {POLL_INTERVAL}s, Output: {OUTPUT_FILE}")
    
    # Write PID
    PID_FILE.write_text(str(os.getpid()))
    logger.info(f"PID: {os.getpid()}")
    
    try:
        while True:
            if not market_open():
                logger.info("NSE market closed (outside 09:15-15:35 IST or holiday); stopping poller")
                break
            t0 = time.time()
            refresh_prices()
            elapsed = time.time() - t0
            sleep_for = max(1, POLL_INTERVAL - elapsed)  # target a true POLL_INTERVAL cycle
            logger.info(f"Cycle took {elapsed:.1f}s; next refresh in {sleep_for:.1f}s (target {POLL_INTERVAL}s cycle)")
            time.sleep(sleep_for)
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
