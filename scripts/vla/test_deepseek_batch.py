"""Offline contracts for ordering, reuse, accounting and batch recovery."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_deepseek_batch as batch


class BatchContracts(unittest.TestCase):
    def setUp(self):
        batch.activate_configuration(batch.frozen_config(batch.DEFAULT_LEDGER, batch.DEFAULT_PILOT))

    def tearDown(self):
        batch.activate_configuration(batch.frozen_config(batch.DEFAULT_LEDGER, batch.DEFAULT_PILOT))

    def write_episode(self, directory, cell=None, *, native=False, error=None, status="passed", stage="online_task_complete"):
        cell = cell or batch.matrix()[0]
        directory.mkdir(parents=True)
        task = {key: cell[key] for key in ("suite", "task", "seed")}
        task["libero_type"] = "standard"
        (directory / "run-summary.json").write_text(json.dumps({"task": task, "status": status, "stage": stage, "planner_error": error}))
        (directory / "online-task").mkdir()
        (directory / "online-task/states.json").write_text(json.dumps({"steps": [{"terminated": native, "truncated": False}]}))
        return directory

    def test_matrix_covers_each_cell_once_and_seed_zero_first(self):
        cells = batch.matrix()
        self.assertEqual(len(cells), 2000)
        self.assertEqual(len({c["id"] for c in cells}), 2000)
        self.assertTrue(all(c["seed"] == 0 and c["phase"] == "coverage" for c in cells[:40]))
        self.assertTrue(all(c["seed"] > 0 for c in cells[40:]))
        self.assertEqual(sum(c["suite"] == "libero_10" for c in cells), 500)

    def test_pilot_is_native_success_and_profile_matches_without_new_process(self):
        with patch("subprocess.Popen") as spawn:
            result = batch.validate_pilot(batch.DEFAULT_PILOT)
            spawn.assert_not_called()
        self.assertEqual(result["id"], batch.matrix()[0]["id"])
        self.assertEqual(result["outcome"], "success")
        self.assertTrue(result["imported_pilot"])

    def test_long_tasks_keep_the_pilot_timeout_and_shared_ledger(self):
        cell = {"suite": "libero_10", "task": 4, "seed": 2}
        command = batch.episode_command(cell, Path("/tmp/not-started"), Path("/tmp/shared-ledger.json"), {"vla": "http://127.0.0.1:1", "sam3": "http://127.0.0.1:2"})
        for flag, value in (("--planner-timeout-s", "1200"), ("--max-cost-usd", "40"), ("--budget-ledger", "/tmp/shared-ledger.json"), ("--max-turns", "100"), ("--max-tokens", "10000"), ("--configuration-version", "v2-output-10000")):
            self.assertEqual(batch._flag(command, flag), value)
        self.assertIn("--skip-component-checks", command)
        self.assertNotIn("--explore", command)
        self.assertNotIn("--no-images", command)

    def test_budget_uses_persistent_accounted_upper_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "ledger.json"
            p.write_text(json.dumps({"limit_usd": "40", "accounted_upper_bound_usd": "39.6734272", "request_attempts": 12}))
            self.assertTrue(batch.can_start(batch.budget_snapshot(p)))
            p.write_text(json.dumps({"limit_usd": "40", "accounted_upper_bound_usd": "39.6734273"}))
            self.assertFalse(batch.can_start(batch.budget_snapshot(p)))
            p.write_text(json.dumps({"limit_usd": "2", "accounted_upper_bound_usd": "0"}))
            with self.assertRaises(ValueError):
                batch.budget_snapshot(p)

    def test_native_success_can_be_recorded_even_if_planner_finish_failed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.write_episode(Path(folder) / "episode", native=True, error="planner timed out", status="planner_error")
            result = batch.read_result(batch.matrix()[0], root)
        self.assertEqual(result["outcome"], "success")
        self.assertTrue(result["native_trace_valid"])

    def test_timeout_is_failure_but_budget_stop_is_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            first = self.write_episode(Path(folder) / "timeout", error="planner timed out after1200s", status="planner_error")
            second = self.write_episode(Path(folder) / "budget", error="DeepSeek API cost cap reached before HTTP send", status="planner_error")
            self.assertEqual(batch.read_result(batch.matrix()[0], first)["outcome"], "failure")
            self.assertEqual(batch.read_result(batch.matrix()[0], second)["outcome"], "budget_stopped")

    def test_wrong_task_native_flag_is_not_imported_as_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.write_episode(Path(folder) / "episode", native=True)
            another = dict(batch.matrix()[0], task=1)
            self.assertEqual(batch.read_result(another, root)["outcome"], "error")

    def test_counts_do_not_call_notrun_or_budget_stopped_a_failure(self):
        cells = batch.matrix()
        results = {cells[0]["id"]: dict(cells[0], outcome="success", imported_pilot=True), cells[1]["id"]: dict(cells[1], outcome="budget_stopped")}
        summary = batch.make_summary(cells, results, {}, datetime.now(timezone.utc).isoformat(), "budget_stopped")
        self.assertEqual(summary["counts"]["success"], 1)
        self.assertEqual(summary["counts"]["failure"], 0)
        self.assertEqual(summary["counts"]["budget_stopped"], 1)
        self.assertEqual(summary["counts"]["notrun"], 1998)
        self.assertEqual(summary["coverage"]["completed"], 2)

    def test_resume_marks_unfinished_cell_without_resubmitting(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            episode = self.write_episode(root / "episode", stage="online_planner_running", status="starting")
            batch.append_event(root / "events.jsonl", {"event": "started", "cell": batch.matrix()[0], "destination": str(episode), "pid": None})
            with patch("subprocess.Popen") as spawn:
                results = batch.restore_results(root, batch.matrix())
                again = batch.restore_results(root, batch.matrix())
                spawn.assert_not_called()
            self.assertEqual(results[batch.matrix()[0]["id"]]["outcome"], "interrupted")
            self.assertEqual(len(again), 1)

    def test_recover_complete_trace_after_crash_without_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            episode = self.write_episode(root / "episode", native=True)
            batch.append_event(root / "events.jsonl", {"event": "started", "cell": batch.matrix()[0], "destination": str(episode), "pid": None})
            restored = batch.restore_results(root, batch.matrix())
            self.assertEqual(restored[batch.matrix()[0]["id"]]["outcome"], "success")

    def test_partial_last_jsonl_append_is_repaired_before_resume_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.jsonl"
            batch.append_event(path, {"event": "first"})
            with path.open("ab") as handle:
                handle.write(b'{"event":')
            self.assertEqual(batch.load_events(path), [{"event": "first"}])
            batch.append_event(path, {"event": "second"})
            self.assertEqual(len(batch.load_events(path)), 2)

    def test_corrupt_interior_jsonl_is_not_silently_dropped(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.jsonl"
            path.write_text('{"event":"a"}\nnotjson\n{"event":"b"}\n')
            with self.assertRaises(ValueError):
                batch.load_events(path)

    def test_versions_are_separate_and_mixed_success_rate_is_not_pooled(self):
        cells = batch.matrix()
        results = {cells[0]["id"]: dict(cells[0], outcome="failure", configuration_version=batch.LEGACY_CONFIGURATION_VERSION),
                   cells[1]["id"]: dict(cells[1], outcome="success", configuration_version=batch.CONFIGURATION_VERSION)}
        summary = batch.make_summary(cells, results, {}, datetime.now(timezone.utc).isoformat(), "running")
        self.assertIsNone(summary["counts"]["success_rate_valid_completed"])
        self.assertTrue(summary["counts"]["mixed_configuration_versions"])
        old = summary["per_configuration"][batch.LEGACY_CONFIGURATION_VERSION]["counts"]
        new = summary["per_configuration"][batch.CONFIGURATION_VERSION]["counts"]
        self.assertEqual((old["total"], old["completed"], old["notrun"]), (1, 1, 0))
        self.assertEqual(new["total"], 1999)
        self.assertEqual(old["success_rate_valid_completed"], 0)
        self.assertEqual(new["success_rate_valid_completed"], 1)

    def test_output_limit_transition_preserves_events_and_historical_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = batch.frozen_config(batch.DEFAULT_LEDGER, batch.DEFAULT_PILOT)
            old["profile"] = dict(old["profile"], max_tokens=8192)
            old.pop("configuration_version")
            (root / "config.json").write_text(json.dumps(old))
            cell = batch.matrix()[0]
            batch.append_event(root / "events.jsonl", {"event": "result", "result": dict(cell, outcome="success")})
            original_events = (root / "events.jsonl").read_bytes()
            event = batch.migrate_output_limit(root)
            self.assertTrue((root / "events.jsonl").read_bytes().startswith(original_events))
            self.assertEqual(event["effective_first_cell"], batch.matrix()[1])
            self.assertEqual(event["previous_completed"], 1)
            current = json.loads((root / "config.json").read_text())
            self.assertEqual(current["profile"]["max_tokens"], 10000)
            self.assertEqual(current["budget_ledger"], old["budget_ledger"])
            historical = json.loads((root / "configurations/v1-output-8192.json").read_text())
            self.assertEqual(historical, old)
            with self.assertRaises(ValueError):
                batch.migrate_output_limit(root)

    def token_result(self, root, *, maximum=10000, native=False, error="UnexpectedModelBehavior: Model token limit (10000) exceeded before any response was generated."):
        episode = self.write_episode(root / "episode", native=native, error=error, status="planner_error")
        path = episode / "run-summary.json"
        report = json.loads(path.read_text())
        report.update(max_tokens=maximum, configuration_version=next(v for v, n in batch.VERSION_LIMITS.items() if n == maximum))
        path.write_text(json.dumps(report))
        return batch.read_result(batch.matrix()[0], episode)

    def test_only_explicit_failed_v2_output_limit_is_a_trigger(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.token_result(Path(folder))
            evidence = batch.token_limit_trigger(result)
            self.assertEqual(evidence["cell"], batch.matrix()[0]["id"])
            self.assertIn("Model token limit (10000) exceeded", evidence["planner_error"])
            self.assertEqual(len(evidence["run_summary_sha256"]), 64)

    def test_physics_network_timeout_success_and_old_caps_do_not_trigger(self):
        cases = [
            {"error": "CUDA out of memory"},
            {"error": "HTTP401 Unauthorized"},
            {"error": "planner timed out after1200s"},
            {"error": "target dropped during placement"},
            {"error": "10000 tokens were supplied as input"},
            {"maximum": 8192, "error": "Model token limit (8192) exceeded"},
            {"native": True},
        ]
        for options in cases:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as folder:
                self.assertIsNone(batch.token_limit_trigger(self.token_result(Path(folder), **options)))

    def test_arm_policy_preserves_v2_until_a_qualifying_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = batch.frozen_config(batch.DEFAULT_LEDGER, batch.DEFAULT_PILOT)
            (root / "config.json").write_text(json.dumps(config))
            original = b'{"event":"existing-history"}\n'
            (root / "events.jsonl").write_bytes(original)
            armed = batch.arm_conditional_upgrade(root)
            self.assertIsNone(armed["upgrade_event"])
            active = json.loads((root / "config.json").read_text())
            self.assertEqual(active["profile"]["max_tokens"], 10000)
            self.assertEqual(active["configuration_version"], "v2-output-10000")
            self.assertEqual(active["budget_ledger"], config["budget_ledger"])
            self.assertEqual(active["cost_limit_usd"], "40")
            self.assertTrue((root / "events.jsonl").read_bytes().startswith(original))
            self.assertEqual(json.loads((root / "conditional-upgrade.json").read_text())["status"], "armed")
            self.assertFalse((root / "configurations/v3-output-32000.json").exists())

    def test_existing_qualifying_failure_upgrades_once_at_next_pending_cell(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = batch.frozen_config(batch.DEFAULT_LEDGER, batch.DEFAULT_PILOT)
            (root / "config.json").write_text(json.dumps(old))
            result = self.token_result(root)
            batch.append_event(root / "events.jsonl", {"event": "result", "result": result})
            before = (root / "events.jsonl").read_bytes()
            armed = batch.arm_conditional_upgrade(root)
            event = armed["upgrade_event"]
            self.assertEqual(event["effective_first_cell"], batch.matrix()[1])
            self.assertEqual(event["new_max_tokens"], 32000)
            self.assertEqual(event["trigger"]["cell"], result["id"])
            active = json.loads((root / "config.json").read_text())
            self.assertEqual(active["configuration_version"], "v3-output-32000")
            self.assertEqual(active["profile"], dict(old["profile"], max_tokens=32000))
            self.assertTrue((root / "events.jsonl").read_bytes().startswith(before))
            self.assertEqual(batch.digest(batch.config_for_resume(root, batch.DEFAULT_LEDGER, batch.DEFAULT_PILOT)), batch.digest(active))
            after = (root / "events.jsonl").read_bytes()
            same, second = batch.maybe_upgrade_output(root, active, {result["id"]: result})
            self.assertIsNone(second)
            self.assertEqual(same, active)
            self.assertEqual((root / "events.jsonl").read_bytes(), after)
            batch.activate_configuration(active)
            command = batch.episode_command(batch.matrix()[1], root / "future", batch.DEFAULT_LEDGER, {})
            self.assertEqual(batch._flag(command, "--max-tokens"), "32000")
            self.assertEqual(batch._flag(command, "--configuration-version"), "v3-output-32000")
            self.assertEqual(batch.RESERVATION, Decimal("0.3529728"))
            self.assertTrue(batch.can_start({"limit_usd": "40", "accounted_upper_bound_usd": "39.6470272"}))
            self.assertFalse(batch.can_start({"limit_usd": "40", "accounted_upper_bound_usd": "39.6470273"}))

    def test_armed_live_boundary_detects_new_failure_and_keeps_config_scores_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = batch.frozen_config(batch.DEFAULT_LEDGER, batch.DEFAULT_PILOT, conditional_upgrade=True)
            (root / "config.json").write_text(json.dumps(config))
            failed = self.token_result(root)
            next_config, event = batch.maybe_upgrade_output(root, config, {failed["id"]: failed})
            self.assertIsNotNone(event)
            batch.activate_configuration(next_config)
            cells = batch.matrix()
            results = {failed["id"]: failed, cells[1]["id"]: dict(cells[1], outcome="success", configuration_version="v3-output-32000", max_tokens=32000)}
            summary = batch.make_summary(cells, results, {}, datetime.now(timezone.utc).isoformat(), "running")
            self.assertIsNone(summary["counts"]["success_rate_valid_completed"])
            self.assertEqual(summary["per_configuration"]["v2-output-10000"]["max_tokens"], 10000)
            self.assertEqual(summary["per_configuration"]["v3-output-32000"]["max_tokens"], 32000)
            self.assertEqual(summary["conditional_output_upgrade"]["status"], "triggered")

    def test_third_systemic_error_token_limit_still_runs_next_episode_at_32000(self):
        cells = batch.matrix()[:5]
        commands = []
        owner = self

        class Services:
            def __init__(self, path):
                pass
            def start(self):
                return {}
            def alive(self):
                return True
            def close(self):
                pass

        class Process:
            def __init__(self, command, **kwargs):
                commands.append(command)
                self.pid = 900000 + len(commands)
                destination = Path(batch._flag(command, "--output-dir"))
                cell = cells[len(commands)]
                error = "Model token limit (10000) exceeded" if len(commands) == 3 else "temporary RPC failure" if len(commands) < 3 else None
                episode = owner.write_episode(destination, cell, native=len(commands) == 4, error=error,
                                              status="planner_error" if error else "passed")
                path = episode / "run-summary.json"
                report = json.loads(path.read_text())
                report.update(max_tokens=int(batch._flag(command, "--max-tokens")),
                              configuration_version=batch._flag(command, "--configuration-version"))
                path.write_text(json.dumps(report))
            def poll(self):
                return 0

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            args = SimpleNamespace(output_dir=root / "batch", budget_ledger=root / "ledger.json", pilot=root / "pilot", resume=False)
            config = batch.frozen_config(args.budget_ledger, args.pilot, conditional_upgrade=True)
            pilot = dict(cells[0], outcome="success", configuration_version=batch.LEGACY_CONFIGURATION_VERSION,
                         max_tokens=8192, imported_pilot=True)
            budget = {"limit_usd": "40", "accounted_upper_bound_usd": "0"}
            with patch.object(batch, "matrix", return_value=cells), patch.object(batch, "validate_pilot", return_value=pilot), \
                 patch.object(batch, "budget_snapshot", return_value=budget), patch("subprocess.Popen", Process), \
                 patch.dict("sys.modules", {"shared_model_services": SimpleNamespace(SharedModelServices=Services)}), \
                 contextlib.redirect_stdout(io.StringIO()):
                result = batch.run(args, config)
            self.assertEqual(result, 0)
            self.assertEqual(len(commands), 4)
            self.assertEqual([batch._flag(command, "--max-tokens") for command in commands], ["10000", "10000", "10000", "32000"])
            summary = json.loads((args.output_dir / "summary.json").read_text())
            self.assertEqual(summary["status"], "completed")
            self.assertEqual(summary["counts"]["failure"], 3)
            self.assertEqual(summary["counts"]["success"], 2)


if __name__ == "__main__":
    unittest.main()
