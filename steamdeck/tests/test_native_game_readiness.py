"""The native fixture must synchronize observer startup without masking failure."""
import asyncio
import gc
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch


spec = importlib.util.spec_from_file_location("native_game_fixture", Path(__file__).with_name("native-game-obs.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class WatcherReadiness(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.output_patch = patch.object(fixture, "OUT", self.output)
        self.output_patch.start()
        self.addCleanup(self.output_patch.stop)
        self.clip = asyncio.get_running_loop().create_future()
        self.addCleanup(self.clip.cancel)
        self.now = 0

    async def tick(self, delay):
        self.now += delay
        await asyncio.sleep(0)

    def status(self, watching=False, recording=True, known=True):
        return {"recording": recording, "output_known": known, "state": "stopped",
                "video": {"state": "game", "watching": watching, "updated": "2026-11-22T17:57:32Z"},
                "settings": {"stream_key": "private-fixture", "server": "https://private.invalid"},
                "diagnostics": [{"message": "Recording ten seconds locally. Nothing is being broadcast."},
                                {"message": "private-fixture https://private.invalid"}]}

    def evidence(self):
        text = (self.output / "local-watcher-readiness.json").read_text()
        self.assertNotIn("private-fixture", text)
        self.assertNotIn("private.invalid", text)
        self.assertNotIn("settings", text)
        return json.loads(text)

    async def gate(self, **kwargs):
        return await fixture.wait_local_test_watcher(self.clip, clock=lambda: self.now, sleep=self.tick, **kwargs)

    async def test_delayed_watcher_requires_its_own_observed_readiness(self):
        with patch.object(fixture, "cli", AsyncMock(side_effect=[self.status(), self.status(True)])) as cli:
            proof = await self.gate(timeout=12, interval=1)
        self.assertFalse(self.clip.done())
        self.assertEqual(proof["state"], "passed")
        self.assertFalse(proof["first"]["video"]["watching"])
        self.assertTrue(proof["last"]["video"]["watching"])
        self.assertEqual(proof["last"]["stages"], ["recording.running"])
        self.assertEqual([c.kwargs["timeout"] for c in cli.call_args_list], [12, 11])
        self.assertTrue(all(c.args == ("status",) and c.kwargs["cleanup_timeout"] == 0 for c in cli.call_args_list))
        self.assertEqual(self.evidence(), proof)

    async def test_permanently_unready_watcher_fails_at_the_total_deadline(self):
        with patch.object(fixture, "cli", AsyncMock(return_value=self.status())) as cli:
            with self.assertRaisesRegex(AssertionError, "3-second startup budget"):
                await self.gate(timeout=3, interval=1)
        self.assertEqual(cli.await_count, 3)
        self.assertEqual(self.evidence()["elapsed_seconds"], 3)
        self.assertEqual(self.evidence()["state"], "failed")

    async def test_stopped_or_unknown_output_fails_without_waiting_or_accepting_watcher(self):
        for status in (self.status(True, recording=False), self.status(True, known=False)):
            with self.subTest(status=status["output_known"]), patch.object(fixture, "cli", AsyncMock(return_value=status)) as cli:
                with self.assertRaisesRegex(AssertionError, "stopped or became unconfirmed"):
                    await self.gate()
                self.assertEqual(cli.await_count, 1)
                self.assertEqual(self.evidence()["state"], "failed")

    async def test_clip_completion_during_status_probe_cannot_qualify_readiness(self):
        async def ended(*args, **kwargs):
            self.clip.set_result({"recording": False})
            return self.status(True)
        with patch.object(fixture, "cli", AsyncMock(side_effect=ended)):
            with self.assertRaisesRegex(AssertionError, "clip completed before watcher readiness"):
                await self.gate()
        self.assertEqual(self.evidence()["state"], "failed")

    async def test_cli_failure_is_not_retried_or_retained_as_private_text(self):
        with patch.object(fixture, "cli", AsyncMock(side_effect=AssertionError("private-fixture"))) as cli:
            with self.assertRaisesRegex(AssertionError, "status probe failed"):
                await self.gate()
        self.assertEqual(cli.await_count, 1)
        self.assertEqual(self.evidence()["state"], "failed")

    async def test_simultaneous_clip_end_and_probe_error_are_both_consumed(self):
        loop = asyncio.get_running_loop()
        previous = loop.get_exception_handler()
        errors = []
        loop.set_exception_handler(lambda loop, context: errors.append(context))
        try:
            async def ended_with_error(*args, **kwargs):
                self.clip.set_result(None)
                raise AssertionError("private-fixture")
            with patch.object(fixture, "cli", AsyncMock(side_effect=ended_with_error)):
                with self.assertRaisesRegex(AssertionError, "clip completed before watcher readiness"):
                    await self.gate()
            gc.collect()
            await asyncio.sleep(0)
            self.assertEqual(errors, [])
            self.assertEqual(self.evidence()["state"], "failed")
        finally:
            loop.set_exception_handler(previous)

    async def test_hung_probe_is_cancelled_at_its_remaining_budget(self):
        cancelled = asyncio.Event()
        async def hung(*args, **kwargs):
            try:
                await asyncio.sleep(100)
            finally:
                cancelled.set()
        started = time.monotonic()
        with patch.object(fixture, "cli", AsyncMock(side_effect=hung)):
            with self.assertRaisesRegex(AssertionError, "startup budget"):
                await fixture.wait_local_test_watcher(self.clip, timeout=.03)
        self.assertTrue(cancelled.is_set())
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(self.evidence()["state"], "failed")
