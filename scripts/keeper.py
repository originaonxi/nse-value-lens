"""Data keeper: make every page of the site show the latest NSE session, without relying on cron timing.

On this repository GitHub's `schedule:` trigger starts runs hours late or not at all, while
`workflow_dispatch` runs start within seconds. The keeper is one long job that, every few minutes:

1. works out the latest NSE session whose close should be processed (after 16:05 IST on trading days);
2. checks whether NSE has published that session's official equity and F&O files;
3. reads what the live site shows and what is committed on master;
4. dispatches only the refresh workflows that are behind (with spacing and an attempt cap);
5. republishes the site when committed data is not live, cancelling publish jobs stuck in "waiting";
6. stops when everything is current, and before the job time limit hands over to a new keeper run.

Any one late cron start is enough to begin the day's chain. Standard library only.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
SITE = os.environ.get("KEEPER_SITE", "https://originaonxi.github.io/nse-value-lens/")
REPO = os.environ.get("GITHUB_REPOSITORY", "originaonxi/nse-value-lens")
API = "https://api.github.com"
NSE_EQ = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d:%d%m%Y}.csv"
NSE_FO = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
BOT = "github-actions[bot]"

READY = dtime(16, 5)            # completed daily candles exist after 16:00 IST
SR_FALLBACK = dtime(21, 30)     # run S&R even without the official equity file by this time
GIVE_UP = dtime(9, 0)           # next morning: stop waiting for NSE files that never appeared
LOOP_MINUTES = 8
MAX_ATTEMPTS = 3                # keeper dispatches per workflow per session
SPACING = timedelta(minutes=40)
STUCK = timedelta(minutes=15)   # a publish job waiting this long is blocking the pages queue
PUBLISH_GRACE = timedelta(minutes=10)
DOWNSTREAM_GRACE = timedelta(minutes=6)
MAX_HOPS = 10
BRIDGE = timedelta(hours=30)   # next close within this: hand over instead of waiting for a late cron

WORKFLOWS = {"hhhl": "hhhl_daily.yml", "sr": "daily_sr.yml", "swing": "swing_desk.yml",
             "options": "options_daily.yml", "market": "daily_market.yml", "fno": "fno_daily.yml",
             "global": "global_markets.yml", "pages": "pages.yml", "keeper": "keeper.yml"}
INPUTS = {"hhhl": {"test_label": "keeper"}, "options": {"force": "false"}}
PUBLISHERS = {"hhhl", "market", "fno", "global", "options", "pages"}


def _market_as_of(j):
    parts = [(j.get(k) or {}).get("as_of") for k in ("market", "indices")]
    return min(parts) if all(parts) else None


# (page label, published file, how to read its session, workflow that refreshes it)
PAGES = [
    ("HH/HL", "hhhl_refresh_status.json", lambda j: j.get("as_of"), "hhhl"),
    ("VCP", "vcp_refresh_status.json", lambda j: j.get("as_of"), "hhhl"),
    ("Market brief", "market_brief_refresh_status.json", lambda j: j.get("as_of"), "hhhl"),
    ("F&O stocks", "hhhl_fno.json", lambda j: j.get("as_of"), "fno"),
    ("Daily S&R", "sr_levels.json", lambda j: j.get("as_of"), "sr"),
    ("Momentum30", "momentum30_daily.json", lambda j: j.get("as_of"), "sr"),
    ("Swing desk", "swing_desk.json", lambda j: j.get("as_of"), "swing"),
    ("Options desk", "options_desk.json", lambda j: j.get("as_of"), "options"),
    ("Deals & breadth", "daily_market.json", _market_as_of, "market"),
]


# ---------------------------------------------------------------- calendar
def load_holidays(path=ROOT / "data" / "hhhl_calendar.json"):
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("holidays", []))
    except (OSError, ValueError):
        return set()


def is_trading(d, holidays):
    return d.weekday() < 5 and d.isoformat() not in holidays


def target_session(now, holidays):
    """Latest session whose close should already be processed."""
    local = now.astimezone(IST)
    d = local.date()
    if is_trading(d, holidays) and local.time() >= READY:
        return d
    d -= timedelta(days=1)
    while not is_trading(d, holidays):
        d -= timedelta(days=1)
    return d


def next_ready(now, holidays):
    """When the next session becomes processable (for idling before the close)."""
    local = now.astimezone(IST)
    d = local.date()
    while True:
        if is_trading(d, holidays):
            ready = datetime.combine(d, READY, IST)
            if ready > local:
                return ready
        d += timedelta(days=1)


# ---------------------------------------------------------------- decision (pure, unit-tested)
def plan(v):
    """Decide what to do from one observation.

    v keys: now (aware datetime), target (date), eq/fo (official files exist), live/master
    ({page: session string or None}), live_official/master_official (bool: HH/HL confirmed against the
    official file), active ({wf: bool}), attempts ({wf: int}), last_dispatch/last_done ({wf: datetime|None}),
    publishing (bool), stuck_runs ([run ids]), stale_since ({page: datetime}), global_stale (bool),
    pretend (set of page labels or workflow keys forced stale).
    Returns dict(actions=[...], done=bool, gaps=[...], notes=[...]).
    """
    t = v["target"].isoformat()
    now = v["now"]
    local = now.astimezone(IST)
    pretend = v.get("pretend") or set()
    actions, notes, gaps = [], [], []

    def forced(label, wf):
        return label in pretend or wf in pretend

    behind = lambda value: not value or value < t     # ISO dates compare as strings; newer counts as current
    live_stale, master_stale = {}, {}
    for label, _, _, wf in PAGES:
        live_stale[label] = forced(label, wf) or behind(v["live"].get(label))
        master_stale[label] = forced(label, wf) or behind(v["master"].get(label, v["live"].get(label)))
    if v["eq"]:
        live_stale["HH/HL"] = live_stale["HH/HL"] or not v["live_official"]
        master_stale["HH/HL"] = master_stale["HH/HL"] or not v.get("master_official", v["live_official"])

    after_target_day = local.date() > v["target"]
    fallback_sr = after_target_day or local.time() >= SR_FALLBACK

    def grace_after(wf):
        last = v["last_done"].get(wf)
        return last is None or now - last >= DOWNSTREAM_GRACE

    prereq = {
        "hhhl": (True, ""),
        "swing": (True, ""),
        "sr": (v["eq"] or fallback_sr, "waiting for NSE's official equity file"),
        "options": (v["fo"], "waiting for NSE's F&O file"),
        "market": (v["eq"] and not v["active"].get("hhhl") and grace_after("hhhl"),
                   "waiting for the official equity file and the HH/HL run"),
        "fno": (not master_stale["HH/HL"] and not v["active"].get("hhhl") and grace_after("hhhl"),
                "waiting for HH/HL"),
    }

    # hhhl, sr and swing share GitHub concurrency group "market-data-refresh", which keeps only ONE pending
    # run: a second queued run silently replaces the first. Start at most one of them, and only when none runs.
    shared = ("hhhl", "sr", "swing")
    shared_busy = any(v["active"].get(w) for w in shared)
    for wf in ("hhhl", "sr", "swing", "options", "fno", "market"):
        stale = [label for label, _, _, w in PAGES if w == wf and master_stale[label]]
        if not stale:
            continue
        ok, why = prereq[wf]
        if v["active"].get(wf):
            notes.append(f"{wf}: running")
        elif not ok:
            notes.append(f"{wf}: {why}")
        elif v["attempts"].get(wf, 0) >= MAX_ATTEMPTS:
            gaps.append(f"{wf}: still behind after {MAX_ATTEMPTS} keeper runs ({', '.join(stale)})")
        elif v["last_dispatch"].get(wf) and now - v["last_dispatch"][wf] < SPACING:
            notes.append(f"{wf}: dispatched recently, waiting")
        elif wf in shared and shared_busy:
            notes.append(f"{wf}: waiting for the shared refresh queue")
        else:
            actions.append(("dispatch", wf, f"behind: {', '.join(stale)}"))
            if wf in shared:
                shared_busy = True

    if v.get("global_stale"):
        if v["active"].get("global"):
            notes.append("global: running")
        elif v["attempts"].get("global", 0) >= MAX_ATTEMPTS:
            gaps.append("global: still behind")
        elif not (v["last_dispatch"].get("global") and now - v["last_dispatch"]["global"] < SPACING):
            actions.append(("dispatch", "global", "commodities and forex older than today"))

    unpublished = [label for label in live_stale if live_stale[label] and not master_stale[label]]
    for run_id in v.get("stuck_runs") or []:
        actions.append(("cancel", run_id, "publish job stuck waiting for GitHub Pages"))
    if unpublished:
        waited = all(now - v["stale_since"].get(label, now) >= PUBLISH_GRACE for label in unpublished)
        blocked = v.get("publishing") and not v.get("stuck_runs")
        if v["active"].get("pages") or blocked:
            notes.append("publish: in progress")
        elif v["attempts"].get("pages", 0) >= MAX_ATTEMPTS * 2:
            gaps.append("publish: committed data still not live")
        elif waited or v.get("stuck_runs"):
            actions.append(("dispatch", "pages", f"committed but not live: {', '.join(unpublished)}"))
        else:
            notes.append(f"publish: giving the normal publish {PUBLISH_GRACE.seconds // 60} min")

    files_missing = not (v["eq"] and v["fo"])
    give_up_files = local >= datetime.combine(v["target"] + timedelta(days=1), GIVE_UP, IST)
    if files_missing and give_up_files:
        gaps.append("NSE official files never appeared for " + t)
    all_current = not any(live_stale.values()) and not v.get("global_stale")
    blocked_only = not actions and not any(n.endswith("running") or "in progress" in n or "waiting" in n for n in notes)
    done = (all_current and (not files_missing or give_up_files)) or (bool(gaps) and blocked_only)
    if files_missing and not give_up_files and all_current:
        notes.append("waiting for NSE's official files to confirm prices")
    return dict(actions=actions, done=done, gaps=gaps, notes=notes, live_stale=live_stale, master_stale=master_stale)


# ---------------------------------------------------------------- I/O
class GitHub:
    def __init__(self, token, repo=REPO, dry_run=False):
        self.token, self.repo, self.dry_run = token, repo, dry_run
        self.calls = 0

    def req(self, method, path, body=None, accept="application/vnd.github+json"):
        self.calls += 1
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(API + path, data=data, method=method, headers={
            "Authorization": "Bearer " + self.token, "Accept": accept, "User-Agent": "nse-value-lens-keeper",
            "X-GitHub-Api-Version": "2022-11-28", **({"Content-Type": "application/json"} if data else {})})
        with urllib.request.urlopen(request, timeout=40) as resp:
            raw = resp.read()
        if accept.endswith("raw"):
            return raw
        return json.loads(raw) if raw else {}

    def runs(self):
        return self.req("GET", f"/repos/{self.repo}/actions/runs?per_page=60").get("workflow_runs", [])

    def jobs(self, run_id):
        return self.req("GET", f"/repos/{self.repo}/actions/runs/{run_id}/jobs?per_page=50").get("jobs", [])

    def dispatched_since(self, workflow, since):
        q = f"/repos/{self.repo}/actions/workflows/{workflow}/runs?event=workflow_dispatch&per_page=50&created=%3E%3D{since:%Y-%m-%dT%H:%M:%SZ}"
        runs = self.req("GET", q).get("workflow_runs", [])
        return [r for r in runs if (r.get("triggering_actor") or r.get("actor") or {}).get("login") == BOT]

    def master_json(self, name):
        raw = self.req("GET", f"/repos/{self.repo}/contents/docs/{name}?ref=master", accept="application/vnd.github.raw")
        return json.loads(raw)

    def dispatch(self, workflow, inputs):
        if self.dry_run:
            return
        self.req("POST", f"/repos/{self.repo}/actions/workflows/{workflow}/dispatches", {"ref": "master", "inputs": inputs})

    def cancel(self, run_id):
        if self.dry_run:
            return
        try:
            self.req("POST", f"/repos/{self.repo}/actions/runs/{run_id}/cancel")
        except urllib.error.HTTPError as exc:
            if exc.code != 409:      # 409: already finished
                raise


def fetch_json(url, timeout=30):
    request = urllib.request.Request(url, headers={"User-Agent": "nse-value-lens-keeper", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read())


def nse_file_exists(url):
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, method=method, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-1023"})
        try:
            with urllib.request.urlopen(request, timeout=30) as resp:
                return resp.status in (200, 206)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            if method == "GET":
                return False
        except (urllib.error.URLError, TimeoutError, OSError):
            if method == "GET":
                return False
    return False


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def official_ok(status_json, target):
    oc = (status_json or {}).get("official_stock_close") or {}
    return oc.get("date") == target.isoformat() and not oc.get("error")


def observe(gh, now, holidays, cache, pretend=frozenset()):
    """Collect one observation for plan(). `cache` persists between loops (files found, stale-since times)."""
    target = target_session(now, holidays)
    if cache.get("target") != target:
        cache.clear()
        cache.update(target=target, eq=False, fo=False, stale_since={})
    if not cache["eq"]:
        cache["eq"] = nse_file_exists(NSE_EQ.format(d=target))
    if not cache["fo"]:
        cache["fo"] = nse_file_exists(NSE_FO.format(d=target))
    stamp = int(now.timestamp())
    live, master, raw_live = {}, {}, {}
    for label, name, read, _ in PAGES:
        try:
            raw_live[name] = fetch_json(f"{SITE}{name}?keeper={stamp}")
            live[label] = read(raw_live[name])
        except Exception as exc:  # unreadable page counts as behind
            print(f"  live {name}: {type(exc).__name__}")
            live[label] = None
    for label, name, read, _ in PAGES:
        if live[label] != target.isoformat() or (label == "HH/HL" and cache["eq"]):
            try:
                j = gh.master_json(name)
                master[label] = read(j)
                if label == "HH/HL":
                    cache["master_official"] = official_ok(j, target)
            except Exception as exc:
                print(f"  master {name}: {type(exc).__name__}")
    runs = gh.runs()
    active, last_done, stuck, publishing = {}, {}, [], False
    by_file = {f: k for k, f in WORKFLOWS.items()}
    for r in runs:
        key = by_file.get((r.get("path") or "").rsplit("/", 1)[-1])
        if key is None:
            continue
        if r.get("status") != "completed":
            active[key] = True
            if key in PUBLISHERS:
                for job in gh.jobs(r["id"]):
                    if "publish" not in job.get("name", "").lower() and "deploy" not in job.get("name", "").lower():
                        continue
                    if job.get("status") == "in_progress":
                        publishing = True
                    elif job.get("status") in ("waiting", "queued", "pending"):
                        publishing = True
                        created = parse_time(job.get("created_at")) or parse_time(r.get("updated_at"))
                        if created and now - created >= STUCK and key != "pages":
                            stuck.append(r["id"])
        elif key not in last_done:
            last_done[key] = parse_time(r.get("updated_at"))
    since = datetime.combine(target, dtime(10, 0), UTC)
    attempts, last_dispatch = {}, {}
    for key in ("hhhl", "sr", "swing", "options", "market", "fno", "global", "pages"):
        mine = gh.dispatched_since(WORKFLOWS[key], since)
        attempts[key] = len(mine)
        last_dispatch[key] = max((parse_time(r["created_at"]) for r in mine), default=None)
    gstale = False
    if now.weekday() < 6 and now.hour >= 11:
        try:
            g = fetch_json(f"{SITE}global_markets.json?keeper={stamp}")
            gen = parse_time(g.get("generated_at"))
            gstale = gen is None or gen < datetime.combine(now.date(), dtime(4, 0), UTC)
        except Exception:
            gstale = True
    view = dict(now=now, target=target, eq=cache["eq"], fo=cache["fo"], live=live, master=master,
                live_official=official_ok(raw_live.get("hhhl_refresh_status.json"), target),
                master_official=cache.get("master_official", official_ok(raw_live.get("hhhl_refresh_status.json"), target)),
                active=active, attempts=attempts, last_dispatch=last_dispatch, last_done=last_done,
                publishing=publishing, stuck_runs=sorted(set(stuck)), stale_since=cache["stale_since"],
                global_stale=gstale, pretend=set(pretend))
    for label in live:
        if live[label] == target.isoformat():
            cache["stale_since"].pop(label, None)
        else:
            cache["stale_since"].setdefault(label, now)
    return view


def summary(view, result):
    t = view["target"].isoformat()
    lines = [f"### Keeper check {view['now'].astimezone(IST):%d %b %H:%M} IST: session {t}",
             f"NSE equity file: {'yes' if view['eq'] else 'not yet'} | F&O file: {'yes' if view['fo'] else 'not yet'}", "",
             "| Page | Live | Committed |", "|---|---|---|"]
    for label, *_ in PAGES:
        lines.append(f"| {label} | {view['live'].get(label) or '--'} | {view['master'].get(label) or view['live'].get(label) or '--'} |")
    lines += ["", "Actions: " + ("; ".join(f"{a[0]} {a[1]} ({a[2]})" for a in result["actions"]) or "none"),
              "Notes: " + ("; ".join(result["notes"]) or "none"), "Gaps: " + ("; ".join(result["gaps"]) or "none"),
              f"Done: {result['done']}"]
    return "\n".join(lines)


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is required")
    dry = os.environ.get("KEEPER_DRY_RUN", "false").lower() == "true"
    once = os.environ.get("KEEPER_ONCE", "false").lower() == "true"
    max_minutes = int(os.environ.get("KEEPER_MAX_MINUTES") or 170)
    hop = int(os.environ.get("KEEPER_HOP") or 0)
    pretend = {p.strip() for p in (os.environ.get("KEEPER_PRETEND_STALE") or "").split(",") if p.strip()}
    if pretend and not (once or max_minutes <= 30):
        sys.exit("KEEPER_PRETEND_STALE is a test mode: use it with KEEPER_ONCE=true or KEEPER_MAX_MINUTES<=30")
    fixed_now = os.environ.get("KEEPER_NOW")
    if fixed_now and not dry:
        sys.exit("KEEPER_NOW (simulated clock) is only allowed with KEEPER_DRY_RUN=true")
    clock = (lambda: datetime.fromisoformat(fixed_now).astimezone(UTC)) if fixed_now else (lambda: datetime.now(UTC))
    gh = GitHub(token, dry_run=dry)
    holidays = load_holidays()
    started, cache, done, handed_over = datetime.now(UTC), {}, False, False
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    print(f"keeper hop {hop} dry_run={dry} once={once} max_minutes={max_minutes} pretend={sorted(pretend)}")
    deadline = started + timedelta(minutes=max_minutes)
    try:
        while True:
            now = clock()
            try:
                view = observe(gh, now, holidays, cache, pretend)
                result = plan(view)
            except Exception as exc:
                print(f"observation failed: {type(exc).__name__}: {exc}")
                result = None
            if result:
                text = summary(view, result)
                print(text)
                if out:
                    with open(out, "a", encoding="utf-8") as fh:
                        fh.write(text + "\n\n")
                for kind, what, why in result["actions"]:
                    try:
                        if kind == "dispatch":
                            gh.dispatch(WORKFLOWS[what], INPUTS.get(what, {}))
                        else:
                            gh.cancel(what)
                        print(f"{'[dry run] would ' if dry else ''}{kind} {what}: {why}")
                    except Exception as exc:
                        print(f"{kind} {what} failed: {type(exc).__name__}: {exc}")
                if result["done"] and not once:
                    upcoming = next_ready(datetime.now(UTC), holidays)
                    if upcoming.astimezone(UTC) + timedelta(minutes=LOOP_MINUTES) < deadline:
                        print(f"session {view['target']} complete; sleeping until the next close is processable "
                              f"({upcoming:%d %b %H:%M} IST)")
                        time.sleep(max(0, (upcoming.astimezone(UTC) - datetime.now(UTC)).total_seconds()))
                        continue
                    if upcoming.astimezone(IST).date() == datetime.now(UTC).astimezone(IST).date():
                        # Today's close comes after this job ends: sleep to the limit, then hand over (not done),
                        # so a live keeper is always present at the close instead of waiting for a late cron.
                        print(f"session {view['target']} complete; today's close is processable at {upcoming:%H:%M} IST, "
                              f"after this job; handing over before the time limit")
                        time.sleep(max(0, (deadline - timedelta(minutes=LOOP_MINUTES) - datetime.now(UTC)).total_seconds()))
                        break
                    print(f"session {view['target']} complete" + (" with gaps" if result["gaps"] else "") +
                          f"; next close {upcoming:%d %b %H:%M} IST is another day, the next scheduled keeper will start it")
                    done = True
                    break
            if once:
                done = True
                break
            if datetime.now(UTC) + timedelta(minutes=LOOP_MINUTES + 2) >= deadline:
                break
            time.sleep(LOOP_MINUTES * 60)
    finally:
        if not done and not dry:
            if hop + 1 >= MAX_HOPS:
                print("hop limit reached; the next scheduled keeper will continue")
            else:
                for attempt in range(3):
                    try:
                        gh.dispatch(WORKFLOWS["keeper"], {"hop": str(hop + 1)})
                        handed_over = True
                        print(f"handed over to keeper hop {hop + 1}")
                        break
                    except Exception as exc:
                        print(f"handover attempt {attempt + 1} failed: {type(exc).__name__}")
                        time.sleep(10)
        print(f"API calls used: {gh.calls}; handed_over={handed_over}")


if __name__ == "__main__":
    main()
