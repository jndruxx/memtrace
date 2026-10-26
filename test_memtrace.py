"""memtrace —— 自检测试。

记录记忆的写入、命中与覆盖过程，说明每条记忆为何被保留。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memtrace  # noqa: E402


class TestMemTrace(unittest.TestCase):
    def setUp(self):
        self.events = [
            memtrace.new_event("write", "user.lang", source="chat#1",
                             reason="explicit_user", content="偏好中文"),
            memtrace.new_event("write", "user.lang", source="chat#9",
                             reason="explicit_user", content="偏好英文"),
            memtrace.new_event("hit", "user.lang"),
            memtrace.new_event("miss", "other.key"),
        ]

    def test_ledger_tracks_overwrite(self):
        ledger = memtrace.build_ledger(self.events)
        entry = ledger["user.lang"]
        self.assertEqual(entry["writes"], 2)
        self.assertEqual(entry["hits"], 1)

    def test_source_is_recorded(self):
        ledger = memtrace.build_ledger(self.events)
        self.assertEqual(ledger["user.lang"]["source"], "chat#9")
        self.assertEqual(ledger["user.lang"]["reason"], "explicit_user")

    def test_history_keeps_both_versions(self):
        ledger = memtrace.build_ledger(self.events)
        self.assertEqual(len(ledger["user.lang"]["history"]), 3)

    def test_unknown_event_kind_rejected(self):
        with self.assertRaises(ValueError):
            memtrace.new_event("nonsense", "k")

    def test_does_not_decide_what_to_remember(self):
        """防呆：工具只记录，不替智能体决定存什么。"""
        before = len(self.events)
        ledger = memtrace.build_ledger(self.events)
        self.assertEqual(len(self.events), before)
        self.assertEqual(len(ledger), 2)

    def test_hit_rate_is_computed(self):
        r = memtrace.analyze(self.events)
        self.assertAlmostEqual(r["hit_rate"], 0.5)
