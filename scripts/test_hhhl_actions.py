"""Run the real HHHL GitHub pipeline sequentially and retain every run's evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time


def gh(*args):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", timeout=90)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--count",type=int,default=10)
    args=parser.parse_args()
    batch=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out=Path("artifacts/hhhl-actions-"+batch);out.mkdir(parents=True,exist_ok=True)
    report={"batch":batch,"requested":args.count,"runs":[]}
    for i in range(1,args.count+1):
        label=f"E2E-{batch}-{i:02d}"
        print(f"Starting full pipeline {i}/{args.count}: {label}",flush=True)
        gh("workflow","run","hhhl_daily.yml","--ref","master","-f","test_label="+label)
        run_id=None
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            runs=json.loads(gh("run","list","--workflow","hhhl_daily.yml","--event","workflow_dispatch",
                              "--limit","25","--json","databaseId,displayTitle"))
            match=next((r for r in runs if r["displayTitle"]=="HHHL refresh "+label),None)
            if match:
                run_id=match["databaseId"];break
            time.sleep(5)
        if run_id is None:
            raise RuntimeError("Dispatched workflow could not be found")
        deadline=time.monotonic()+3000
        last=""
        while time.monotonic()<deadline:
            run=json.loads(gh("run","view",str(run_id),"--json","databaseId,status,conclusion,jobs,url,createdAt,updatedAt,headSha"))
            state=run["status"]+" / "+", ".join(j["name"]+":"+j["status"] for j in run["jobs"])
            if state!=last:
                print(str(run_id)+" "+state,flush=True);last=state
            if run["status"]=="completed":
                break
            time.sleep(15)
        else:
            raise RuntimeError("Workflow timed out")
        record={k:run[k] for k in ["databaseId","conclusion","url","createdAt","updatedAt","headSha"]}
        record["label"]=label
        if run["conclusion"]=="success":
            folder=out/str(run_id)
            gh("run","download",str(run_id),"--name","hhhl-end-to-end","--dir",str(folder))
            record["evidence"]=json.loads((folder/"hhhl-live-report.json").read_text(encoding="utf-8"))
        report["runs"].append(record)
        (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        print(f"Completed {i}/{args.count}: {run['conclusion']} {run['url']}",flush=True)
        if run["conclusion"]!="success":
            raise RuntimeError("End-to-end run failed; inspect it before continuing")
    print("ALL "+str(args.count)+" FULL PIPELINES PASSED. Evidence: "+str(out/"report.json"),flush=True)


if __name__=="__main__":
    main()
