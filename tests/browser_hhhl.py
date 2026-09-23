"""Check the current HH/HL UI without date-specific fixture assumptions."""
import argparse
import requests
import sys
import verify_hhhl_live as verify

parser=argparse.ArgumentParser()
parser.add_argument("--url",default="http://localhost:3219/hhhl.html")
args=parser.parse_args()
base=args.url.rsplit("/",1)[0]+"/"
source="" if "github.io/" in base else "data/"
status=requests.get(base+source+"hhhl_refresh_status.json",timeout=20).json()
verify.SITES=[("browser",base,source)]
sys.argv=["verify","--run-id",str(status["run_id"]),"--timeout","60"]
verify.main()
