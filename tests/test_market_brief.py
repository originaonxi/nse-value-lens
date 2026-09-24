import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import patch, Mock

import pandas as pd

from jev_client import Client, JevError, MODEL, validate_answers
from market_sources import parse_rss, parse_ics, safe_url
from market_brief import archive_payload, forward_return, slot_at, technical_rows, choice, judge_stocks

ROOT = Path(__file__).resolve().parents[1]


class MarketTests(unittest.TestCase):
    def test_response_validation_rejects_nan_missing_and_unknown_choice(self):
        q = {"q":choice("Classify", {"yes":"Support", "no":"Oppose"})}
        valid = {"model":MODEL, "answers":{"q":{"type":"choice", "choice":"yes", "confidence":.8, "probabilities":{"yes":.9, "no":.1}}}, "usage":{"input_tokens":10, "output_tokens":0}}
        self.assertEqual(validate_answers(valid, q)["q"]["choice"], "yes")
        for key, value in (("confidence", float("nan")), ("choice", "maybe"), ("probabilities", {"yes":1.0}), ("confidence", True)):
            bad = copy.deepcopy(valid)
            bad["answers"]["q"][key] = value
            with self.assertRaises(JevError):
                validate_answers(bad, q)
        bad = copy.deepcopy(valid);bad["answers"] = {}
        with self.assertRaises(JevError):
            validate_answers(bad, q)

    @patch("jev_client.requests.post")
    def test_no_retry_auth_or_response_body_leak(self, post):
        post.return_value = Mock(status_code=401, text="secret-value-must-not-escape")
        with self.assertRaisesRegex(JevError, "^Jev HTTP 401$"):
            Client("test-only").ask({}, {"q":choice("test", {"x":"x"})})
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], "https://api.typesafe.ai/v1/systemone")
        self.assertFalse(post.call_args.kwargs["allow_redirects"])

    @patch("jev_client.requests.post")
    @patch("jev_client.time.sleep")
    def test_overload_retry_is_bounded(self, sleep, post):
        post.return_value = Mock(status_code=529)
        with self.assertRaisesRegex(JevError, "529"):
            Client("test-only").ask({}, {})
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_rss_rejects_future_dates_and_unsafe_links(self):
        xml = '''<rss><channel><item><title>Known</title><link>https://example.org/a</link><pubDate>Thu, 24 Sep 2026 10:00:00 +0530</pubDate></item><item><title>Future</title><link>https://example.org/b</link><pubDate>Fri, 25 Sep 2026 10:00:00 +0530</pubDate></item><item><title>Bad</title><link>javascript:alert(1)</link><pubDate>Thu, 24 Sep 2026 10:00:00 +0530</pubDate></item></channel></rss>'''
        now = datetime(2026, 9, 24, 8, tzinfo=timezone.utc)
        self.assertEqual([r["title"] for r in parse_rss(xml, now, "Test", "US")], ["Known"])
        self.assertIsNone(safe_url("https://secret:password@example.org"))

    def test_rbi_naive_clock_is_ist_and_bom_bytes_work(self):
        xml = '\ufeff<?xml version="1.0" encoding="utf-8"?><rss><item><title>Release</title><link>http://www.rbi.org.in/a</link><pubDate>Thu, 24 Sep 2026 11:00:00</pubDate></item></rss>'
        now = datetime(2026,9,24,6,tzinfo=timezone.utc)
        rows = parse_rss(xml.encode("utf-8"), now, "RBI press releases", "India")
        self.assertEqual(rows[0]["published_at"], "2026-09-24T05:30:00+00:00")
        self.assertEqual(rows[0]["url"], "https://www.rbi.org.in/a")
        self.assertFalse(parse_rss(xml.encode(), now, "Federal Reserve", "US"))

    def test_calendar_dst_and_date_only(self):
        ics = "BEGIN:VEVENT\nDTSTART;TZID=America/New_York:20260925T083000\nSUMMARY:Release\nEND:VEVENT\nBEGIN:VEVENT\nDTSTART;VALUE=DATE:20260924\nSUMMARY:All day\nEND:VEVENT\nBEGIN:VEVENT\nDTSTART:20260923T123000Z\nSUMMARY:Past\nEND:VEVENT"
        rows = parse_ics(ics, datetime(2026,9,24,16,tzinfo=timezone.utc))
        self.assertEqual(len(rows), 2)
        self.assertIsNone(rows[0]["time"])
        self.assertEqual(rows[1]["time"], "2026-09-25T12:30:00+00:00")

    def test_archive_never_enters_an_already_open_session(self):
        payload = {"id":"x", "as_of":"2026-09-23", "generated_at":"2026-09-24T08:00:00+00:00", "slot":"manual", "audit":{"evidence_hash":"x"}, "rows":[]}
        self.assertEqual(archive_payload(payload)["entry_after_date"], "2026-09-24")
        payload["generated_at"] = "2026-09-24T02:55:00+00:00"
        self.assertEqual(archive_payload(payload)["entry_after_date"], "2026-09-23")
        self.assertEqual(slot_at(datetime(2026,9,24,2,55,tzinfo=timezone.utc)), "preopen")

    def test_forward_dates_cost_and_missing_bar(self):
        dates = ["2026-09-24", "2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30"]
        frame = pd.DataFrame({"Open":[100]*5,"Close":[101,102,103,104,110],"Volume":[1000]*5},index=dates)
        self.assertAlmostEqual(forward_return(frame, dates, "2026-09-23", 5, "2026-09-30"), 9.6)
        self.assertIsNone(forward_return(frame, dates, "2026-09-24", 5, "2026-09-30"))
        self.assertIsNone(forward_return(frame.drop("2026-09-28"), dates, "2026-09-23", 5, "2026-09-30"))
        self.assertIsNone(forward_return(frame, dates, "2026-09-23", 5, "2026-09-29"))

    def test_all200_and_mismatched_scanners(self):
        h = json.loads((ROOT / "docs/hhhl_scan.json").read_text(encoding="utf-8"))
        v = json.loads((ROOT / "docs/vcp_scan.json").read_text(encoding="utf-8"))
        evidence = {"sources":[{"id":key,"state":"unavailable","items":[]} for key in ("nse_announcements","nse_meetings")]}
        rows = technical_rows(h,v,evidence)
        self.assertEqual(len(rows), 200)
        self.assertTrue(all(r["context"] == "insufficient" and r["event_risk"] == "unknown" and not r["judged"] for r in rows))
        v["as_of"] = "1900-01-01"
        with self.assertRaises(ValueError):technical_rows(h,v,evidence)

    def test_missing_company_feeds_cannot_be_ordinary_risk(self):
        rows = [{"symbol":"TEST", "sector":"IT", "price_ready":False,"company_coverage":{"announcements":"unavailable"}}]
        evidence = {"retrieved_at":"2026-09-24", "quotes":[],"sources":[]}
        client = Mock()
        client.ask.return_value = {"s0":{"choice":"supportive", "confidence":.8, "probabilities":{"supportive":.8}}, "r0":{"choice":"ordinary"}, "d0":{"choice":"dollar"}}
        self.assertEqual(judge_stocks(client, rows, evidence), [])
        self.assertEqual(rows[0]["context"], "insufficient")
        self.assertEqual(rows[0]["event_risk"], "unknown")
        supplied = client.ask.call_args.args[0]["stocks"][0]
        self.assertNotIn("context", supplied)
        self.assertNotIn("event_risk", supplied)
        self.assertNotIn("judged", supplied)


if __name__ == "__main__":unittest.main()
