"""Download public CC0 research data, checking the publisher's checksum."""
from pathlib import Path
import hashlib
import requests
ROOT=Path(__file__).resolve().parents[2]
URL='https://zenodo.org/api/records/10899828/files/Nifty%20spot%20and%20futures%20data.zip/content'
MD5='240aecc77a7275ec2f05a092b976bf91'
def main():
    path=ROOT/'.cache/social_nifty/spot_futures.zip'
    if path.exists() and hashlib.md5(path.read_bytes()).hexdigest()==MD5:
        print('Verified cached archive');return
    response=requests.get(URL,timeout=120);response.raise_for_status()
    assert hashlib.md5(response.content).hexdigest()==MD5,'Publisher checksum mismatch'
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(response.content)
    print('Downloaded and verified 2017-2020 Nifty archive; see https://zenodo.org/records/10899828')
if __name__=='__main__':main()
