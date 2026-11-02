"""Offline contracts for the evaluation plan and provider selection."""
from __future__ import annotations

import copy
import contextlib
import io
import json
from pathlib import Path
import pickle
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import benchmark_harness as benchmark
from init_state_shape import initial_state_shape
import run_harness


class BenchmarkContracts(unittest.TestCase):
    def setUp(self):
        self.config = benchmark.load_config(benchmark.WORKSPACE / "configs/deepseek-libero-pro.json")

    def test_standard_matrix_has_all_2000_nonempty_saved_initial_states(self):
        plan = benchmark.make_plan(benchmark.load_config(benchmark.DEFAULT_CONFIG))
        self.assertEqual(plan["selected_episodes"], 2000)
        self.assertEqual(plan["blocked_episodes"], 0)
        self.assertTrue(all(a["init_count"] == 50 for a in plan["assets"].values()))

    def test_all_downloaded_adds_4500_pretraining_diagnostic_episodes(self):
        config = benchmark.load_config(benchmark.WORKSPACE / "configs/deepseek-libero-all-downloaded.json")
        plan = benchmark.make_plan(config)
        self.assertEqual(plan["selected_episodes"], 6500)
        self.assertEqual(plan["blocked_episodes"], 0)
        self.assertEqual(sum(c["suite"] == "libero_90" for c in plan["cells"]), 4500)

    def test_full_matrix_keeps_empty_assets_in_denominator(self):
        plan = benchmark.make_plan(self.config)
        self.assertEqual(len(plan["cells"]), 800)
        self.assertEqual(len({c["id"] for c in plan["cells"]}), 800)
        blocked_tasks = {(c["suite"], c["task"]) for c in plan["cells"] if c["status"] == "blocked"}
        self.assertEqual(blocked_tasks, {("libero_spatial_task", 3), ("libero_spatial_task", 7), ("libero_10_task", 2)})
        self.assertEqual(plan["blocked_episodes"], 30)
        self.assertEqual(plan["preflight"], "blocked")

    def test_pilot_selection_is_explicit_and_not_a_full_benchmark(self):
        plan = benchmark.make_plan(self.config, ["libero_object_swap:2:0"])
        self.assertEqual(plan["selected_episodes"], 1)
        self.assertEqual(plan["blocked_episodes"], 0)
        self.assertFalse(plan["complete_matrix_selected"])
        self.assertEqual(plan["cells"][0]["init_index"], 0)
        with self.assertRaisesRegex(ValueError, "outside"):
            benchmark.make_plan(self.config, ["libero_object_swap:20:0"])

    def test_config_rejects_endpoint_change_and_loss_of_visual_feedback(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            for field, value in (("base_url", "https://unapproved.invalid"), ("images", False), ("reset_during_evaluation", True)):
                changed = copy.deepcopy(self.config)
                changed[field] = value
                path.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):
                    benchmark.load_config(path)

    def test_long_timeout_and_provider_reach_the_single_episode_launcher(self):
        cell = {"suite": "libero_10_task", "task": 0, "seed": 4}
        command = benchmark.episode_command(self.config, cell, Path("/tmp/not-executed"), {})
        self.assertEqual(command[command.index("--planner-timeout-s") + 1], "5000")
        args = run_harness.build_parser().parse_args(command[2:])
        planner = run_harness.planner_command(args, Path("/tmp/not-executed"), {"env": "http://127.0.0.1:1"})
        self.assertIn(str(benchmark.ROOT / "scripts/harness/deepseek_api.py"), planner)
        self.assertEqual(planner[planner.index("--model") + 1], "deepseek:deepseek-flash")
        self.assertEqual(planner[planner.index("--seed") + 1], "4")
        self.assertNotIn("--no-images", planner)
        self.assertNotIn("--explore", planner)

    def test_cache_cost_is_counted_once(self):
        cost = benchmark.usage_cost({"total_input_tokens": 1_000_000, "total_cached_input_tokens": 750_000, "total_output_tokens": 100_000}, self.config)
        self.assertAlmostEqual(cost, 0.1995)

    def test_single_episode_refuses_unapproved_endpoint_before_creating_output(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "must-not-exist"
            argv = ["run_harness.py", "--output-dir", str(destination), "--planner", "api", "--model", "deepseek:deepseek-flash", "--base-url", "https://unapproved.invalid", "--max-cost-usd", "2"]
            with patch("sys.argv", argv), patch("subprocess.Popen") as start, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    run_harness.main()
                start.assert_not_called()
            self.assertFalse(destination.exists())

    def test_standard_source_environment_points_to_standard_assets(self):
        sys.path.insert(0, str(benchmark.ROOT / "scripts/harness"))
        from smoke_environment import source_environment
        with tempfile.TemporaryDirectory() as folder:
            environment = source_environment(Path(folder), "standard")
            config = json.loads((Path(folder) / "libero-config/config.yaml").read_text())
            self.assertEqual(environment["LIBERO_TYPE"], "standard")
            self.assertEqual(Path(config["benchmark_root"]), benchmark.STANDARD_ROOT)

    def test_blocked_matrix_stops_before_gpu_or_key_access(self):
        with patch("sys.argv", ["benchmark_harness.py", "--config", str(benchmark.WORKSPACE / "configs/deepseek-libero-pro.json"), "--execute"]), patch("subprocess.run") as run, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                benchmark.main()
            self.assertEqual(raised.exception.code, 2)
            run.assert_not_called()

    def test_shape_reader_rejects_unrecognized_pickle_globals(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.pruned_init"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("archive/data.pkl", pickle.dumps(eval))
            with self.assertRaisesRegex(ValueError, "Unsupported pickle global"):
                initial_state_shape(path)

    def test_shape_reader_rejects_corrupt_container(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.pruned_init"
            path.write_bytes(b"not-a-zip")
            with self.assertRaisesRegex(ValueError, "corrupt"):
                initial_state_shape(path)


if __name__ == "__main__":
    unittest.main()
