"""Live or local trader dashboard acceptance checks (Playwright Chromium)."""
import argparse
import copy
import json
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import expect, sync_playwright

NEW_RULES = ['vrp_put_ratio', 'trend_call_ratio', 'skew_jade_lizard', 'flat_broken_wing',
             'expiry_week_short_strangle', 'pro_desk_iron_condor']


def run(url, screenshots=None):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        response = context.request.get(urljoin(url, 'nifty_chain.json'))
        assert response.ok, response.status
        data = response.json()
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(url, wait_until='networkidle')
        expect(page.locator('body')).to_have_attribute('data-ready', 'true', timeout=30000)
        expect(page.locator('#decision-summary')).to_be_visible()
        assert page.locator('#decision-summary').bounding_box()['y'] < 700
        cards = page.locator('#setup-cards [data-rule]')
        assert cards.count() == len(data['setups']), (cards.count(), len(data['setups']))
        order = page.evaluate('''data => NiftyMath.rankTradeSetups(data).map(r => r.setup.rule)''', data)
        assert cards.evaluate_all('(cards) => cards.map(c => c.dataset.rule)') == order
        for rule in NEW_RULES:
            card = page.locator(f'#setup-cards [data-rule="{rule}"]')
            assert card.count() == 1, rule
            assert card.locator('table').count() >= 1, rule
            assert card.locator('svg').count() >= 1, rule
            text = card.inner_text() if card.is_visible() else card.text_content()
            assert 'Jev' in text or 'JEV' in text, rule
        body = page.locator('body').inner_text()
        assert 'BEST BY MATHS' not in body
        assert 'NaN' not in page.content() and '>undefined<' not in page.content()
        assert not errors, errors
        # Regression: every visible read-only field uses reference snapshot prices.
        assert 'Live repricing' not in body
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
        market = page.locator('#market-cards .mkt-card')
        assert market.count() == 8
        assert all(box['width'] >= 100 for box in market.evaluate_all('(xs)=>xs.map(x=>({width:x.getBoundingClientRect().width}))'))
        if screenshots:
            Path(screenshots).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(screenshots) / 'nifty-dashboard-desktop.png'), full_page=False)
        # Every filter control must be keyboard reachable and have an accessible label.
        search = page.locator('#setup-search')
        expect(search).to_be_visible()
        search.fill('jade')
        expect(page.locator('#setup-cards [data-rule]:visible')).to_have_count(1)
        search.fill('unlikely-no-such-contract')
        expect(page.locator('#setup-cards [data-rule]:visible')).to_have_count(0)
        search.fill('')
        # Buyer filter must not misclassify short straddles/strangles as purchases.
        page.locator('[data-filter="buyers"]').click()
        visible_rules = page.locator('#setup-cards [data-rule]:visible').evaluate_all('(xs)=>xs.map(x=>x.dataset.rule)')
        by_rule = {s['rule']: s for s in data['setups']}
        assert all(not by_rule[r]['action'].startswith('SHORT') for r in visible_rules)
        page.locator('[data-filter="all"]').click()
        for section in ['chain', 'participants', 'rules', 'constituents', 'comparison', 'jev', 'research', 'method']:
            page.locator(f'#section-{section} > summary').click()
        assert page.locator('#participant-cards .nc-part-card').count() == len(data['participants'])
        assert page.locator('#constituents-wrap tbody tr').count() == data['constituents_count']
        first = sorted(data['constituents'], key=lambda c: c['symbol'])[0]
        assert first['jev']['stance'] in page.locator('#constituents-wrap tbody tr').first.inner_text()
        assert page.locator('#comparison-rows tr').count() == len(data['comparison']['candidates'])
        assert page.locator('#research-body .nc-research-item').count() == sum(len(data['research'][k]) for k in ['institutions', 'strategies', 'evidence', 'github'])
        assert 'matured index reviews' in page.locator('#jev-calibration').inner_text()
        assert '[object Object]' not in page.locator('#method-body').inner_text()
        assert page.locator('#hhhl-chart svg').count() == 1
        assert page.locator('#oi-chart-wrap svg').count() == 1
        page.locator('#expiry-select').select_option(data['expiries'][-1]['expiry'])
        assert page.locator('#chain-table-wrap tbody tr').count() > 0
        for section in ['chain', 'participants', 'rules', 'constituents', 'comparison', 'jev', 'research', 'method']:
            page.locator(f'#section-{section} > summary').click()
        page.evaluate('scrollTo(0,0)')
        # Read model-derived exact risk against rendering; negative EV must never qualify.
        outcome = page.evaluate('''data => {
          const rows = NiftyMath.rankTradeSetups(data);
          return {eligible:rows.filter(r=>r.eligible).length,
            bad:rows.filter(r=>r.eligible && r.setup.exit.exp_pnl_per_lot<=0).length};
        }''', data)
        assert outcome['bad'] == 0
        if not outcome['eligible']:
            assert 'wait' in page.locator('#decision-summary').inner_text().lower()
        page.set_viewport_size({'width': 390, 'height': 844})
        expect(page.locator('#decision-summary')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2')
        assert all(box['width'] >= 120 for box in market.evaluate_all('(xs)=>xs.map(x=>({width:x.getBoundingClientRect().width}))'))
        if screenshots:
            page.screenshot(path=str(Path(screenshots) / 'nifty-dashboard-mobile.png'), full_page=False)
        # Missing Jev remains honestly unknown, and cannot unlock a consider decision.
        missing = copy.deepcopy(data)
        missing['jev'] = {'state': 'skipped', 'message': 'Test: no review'}
        for s in missing['setups']:
            s.pop('jev_priority', None)
        other = context.new_page()
        other.route('**/nifty_chain.json*', lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps(missing)))
        other.goto(url, wait_until='networkidle')
        expect(other.locator('body')).to_have_attribute('data-ready', 'true')
        assert other.evaluate('data => NiftyMath.rankTradeSetups(data).every(r => !r.eligible && !r.jev.available)', missing)
        assert 'wait' in other.locator('#decision-summary').inner_text().lower()
        # Invalid core dataset fails closed and does not leave actionable cards.
        broken = copy.deepcopy(data)
        broken['setups'] = 'invalid'
        bad = context.new_page()
        bad.route('**/nifty_chain.json*', lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps(broken)))
        bad.goto(url, wait_until='networkidle')
        expect(bad.locator('body')).to_have_attribute('data-ready', 'error')
        expect(bad.locator('#notice')).to_be_visible()
        assert bad.locator('#setup-cards [data-rule]').count() == 0
        browser.close()
    print(f'Dashboard browser PASS: {len(data["setups"])} ordered cards, six new setups, desktop/mobile, search, missing Jev, invalid data; {url}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', required=True)
    ap.add_argument('--screenshots')
    args = ap.parse_args()
    run(args.url, args.screenshots)
