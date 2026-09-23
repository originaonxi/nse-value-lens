from pathlib import Path
import json
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

root=Path(__file__).resolve().parents[1]
(root/"artifacts").mkdir(exist_ok=True)
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={"width":1440,"height":1080},device_scale_factor=1)
    page.on("pageerror",lambda e:errors.append(str(e)))
    page.goto("http://localhost:3217",wait_until="networkidle")
    page.locator("#results").wait_for()
    assert page.locator("#results tr").count()==3
    assert "Cash is a position" in page.locator("#cards").inner_text()
    page.screenshot(path=str(root/"artifacts/swing-desktop.png"),full_page=True)
    page.set_viewport_size({"width":390,"height":844})
    page.screenshot(path=str(root/"artifacts/swing-mobile.png"),full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    # Exercise actual candidate interactions using an explicit synthetic fixture.
    snapshot=json.loads((root/"public/data/swing_desk.json").read_text())
    snapshot["as_of"]=(datetime.now(timezone.utc)+timedelta(hours=5,minutes=30)).date().isoformat()
    snapshot["market"]["risk_on"]=True
    snapshot["candidates"]=[{"symbol":"TEST","name":"Synthetic test only","sector":"Test",
        "strategy":"breakout","hold":20,"close":100,"entry_low":99,"entry_high":101,
        "stop":96,"target":108,"volume_ratio":1.7,"relative_strength":.1,"reason":"Test fixture"}]
    page.route("**/swing_desk.json",lambda route:route.fulfill(json=snapshot))
    page.reload(wait_until="networkidle")
    page.locator(".card").wait_for()
    page.locator("#strategy").select_option("pullback")
    assert "No setup passes" in page.locator("#cards").inner_text()
    page.locator("#strategy").select_option("all")
    page.locator(".sizing summary").click()
    page.locator("#sizing-symbol").select_option("0")
    assert "shares" in page.locator("#size-result").inner_text()
    page.locator("#fill").fill("110")
    assert "Skip this entry" in page.locator("#size-result").inner_text()
    page.locator("#capital").fill("0")
    assert "positive capital" in page.locator("#size-result").inner_text()
    snapshot["as_of"]="2020-01-01"
    page.reload(wait_until="networkidle")
    assert "Wait for a fresh snapshot" in page.locator("#cards").inner_text()
    assert page.locator("#sizing-symbol").is_disabled()
    # A failed snapshot must not leave historical entry plans visible.
    page.unroute("**/swing_desk.json")
    page.route("**/swing_desk.json",lambda route:route.fulfill(status=503,body="unavailable"))
    page.reload(wait_until="networkidle")
    assert "Data unavailable" in page.locator("#cards").inner_text()
    assert not errors, errors
    browser.close()
print("Browser checks passed: desktop, mobile, filters, sizing, stale data, missing data; zero JS errors.")
