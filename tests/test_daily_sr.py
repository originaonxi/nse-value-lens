import threading
import unittest

import pandas as pd

from daily_sr import volume_poc


def run_with_deadline(fn, seconds=5):
    result = {}
    worker = threading.Thread(target=lambda: result.setdefault("value", fn()), daemon=True)
    worker.start()
    worker.join(seconds)
    return worker.is_alive(), result.get("value")


class VolumePocTests(unittest.TestCase):
    def test_terminates_when_one_side_has_only_empty_bins(self):
        # 60% of volume sits at the top of the range (the POC bin) and 40% at the
        # bottom, with empty bins between. The POC alone is below the 70% value
        # area, the upper side is exhausted and the next lower bin is empty: this
        # shape previously walked the upper index past the end forever.
        rows = [dict(High=100.0, Low=99.0, Close=99.5, Volume=400_000.0 / 89)] * 89
        rows.append(dict(High=200.0, Low=199.9, Close=200.0, Volume=600_000.0))
        hung, value = run_with_deadline(lambda: volume_poc(pd.DataFrame(rows)))
        self.assertFalse(hung, "volume_poc did not terminate")
        poc, vah, val = value
        self.assertLessEqual(val, poc)
        self.assertLessEqual(poc, vah)
        self.assertLessEqual(vah, 200.0 + 1e-6)

    def test_value_area_brackets_poc_for_normal_data(self):
        rows = [dict(High=100 + i % 7, Low=95 + i % 7, Close=98 + i % 7, Volume=1000 + 10 * i)
                for i in range(90)]
        hung, value = run_with_deadline(lambda: volume_poc(pd.DataFrame(rows)))
        self.assertFalse(hung)
        poc, vah, val = value
        self.assertTrue(val <= poc <= vah)


if __name__ == "__main__":
    unittest.main()
