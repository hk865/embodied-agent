"""Offline tests: no SSH connections, GPU allocations, or package installation."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import cloudctl
import remote_job


class CloudPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="cloud-tools-")
        self.root = Path(self.temporary.name)
        self.configuration = self.root / "config.json"
        self.data = {"ssh_host": "vla-gpu", "remote_root": "/srv/VLA space'$(touch exploit)", "remote_python": "python3"}
        self.write_config()
        self.config = cloudctl.Config.read(self.configuration, self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_config(self) -> None:
        self.configuration.write_text(json.dumps(self.data))

    def build(self, *arguments: str) -> list[list[str]]:
        args = cloudctl.make_parser().parse_args(list(arguments))
        return cloudctl.build_commands(self.config, args)

    def test_invalid_aliases_and_roots_are_rejected(self) -> None:
        for host in ("-oProxyCommand=touch exploit", "root@server", "server;touch exploit", "server\nother"):
            with self.subTest(host=host):
                self.data["ssh_host"] = host
                self.write_config()
                with self.assertRaises(ValueError):
                    cloudctl.Config.read(self.configuration, self.root)
        self.data["ssh_host"] = "vla-gpu"
        for root in ("/", "relative", "/srv/../outside"):
            self.data["remote_root"] = root
            self.write_config()
            with self.assertRaises(ValueError):
                cloudctl.Config.read(self.configuration, self.root)

    def test_push_excludes_runtime_credentials_and_never_deletes(self) -> None:
        commands = self.build("push")
        rsync = commands[-1]
        self.assertIn("--dry-run", rsync)
        self.assertNotIn("--delete", rsync)
        self.assertIn("--protect-args", rsync)
        for excluded in (".codex/", ".ssh/", ".env.*", "*.local.json", "*.key", "/workspace/vla_baselines/repos/", "/workspace/vla_baselines/checkpoints/"):
            self.assertIn("--exclude=" + excluded, rsync)
        self.assertIn("StrictHostKeyChecking=yes", commands[0])
        self.assertIn("BatchMode=yes", commands[0])

    def test_paths_and_option_programs_are_rejected(self) -> None:
        for path in ("../outside", "/absolute", "nested/../../outside", "logs/*", "logs\nother", ".ssh/id_rsa", "test-secrets.txt"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.build("pull", path)
        with self.assertRaises(ValueError):
            self.build("exec", "--", "-c", "bad")
        with self.assertRaises(ValueError):
            self.build("job-start", "--id", "../escape", "--", "python3")

    def test_ssh_command_quotes_root_and_each_argument(self) -> None:
        arguments = ["python3", "path with spaces", "a';touch exploit;echo '", "$(touch exploit)"]
        ssh = cloudctl.ssh_command(self.config, arguments)
        self.assertEqual(shlex.split(ssh[-1]), arguments)
        command = self.build("exec", "--", "printf", "%s", arguments[-1])[0]
        parsed = shlex.split(command[-1])
        self.assertEqual(parsed[parsed.index("--root") + 1], self.config.remote_root)
        self.assertEqual(parsed[-3:], ["printf", "%s", arguments[-1]])

    def test_planning_performs_no_subprocess_and_no_artifact_creation(self) -> None:
        with mock.patch.object(sys, "argv", ["cloudctl", "--config", str(self.configuration), "--local-root", str(self.root), "pull", "logs"]), mock.patch("cloudctl.subprocess.run", side_effect=AssertionError("plan tried to execute")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cloudctl.main(), 0)
        self.assertFalse((self.root / "workspace").exists())

    def test_pull_rejects_existing_local_symlink(self) -> None:
        destination = self.root / "workspace" / "vla_baselines" / "artifacts"
        destination.parent.mkdir(parents=True)
        destination.symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.build("pull", "logs")

    def test_missing_local_tool_fails_before_any_remote_mutation(self) -> None:
        with mock.patch.object(sys, "argv", ["cloudctl", "--config", str(self.configuration), "--local-root", str(self.root), "--execute", "push"]), mock.patch("cloudctl.shutil.which", side_effect=lambda value: "/usr/bin/ssh" if value == "ssh" else None), mock.patch("cloudctl.subprocess.run") as run, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cloudctl.main(), 1)
            run.assert_not_called()

    def test_tunnel_binds_only_loopback_and_rejects_bad_ports(self) -> None:
        tunnel = self.build("tunnel", "--local-port", "8000", "--remote-port", "8001")[0]
        self.assertIn("127.0.0.1:8000:127.0.0.1:8001", tunnel)
        self.assertIn("ExitOnForwardFailure=yes", tunnel)
        with self.assertRaises(ValueError):
            self.build("tunnel", "--local-port", "0", "--remote-port", "8001")

    @unittest.skipUnless(shutil.which("rsync"), "rsync unavailable locally")
    def test_repeated_relative_directory_pull_never_nests(self) -> None:
        source = self.root / "remote"
        directory = source / "workspace" / "logs"
        directory.mkdir(parents=True)
        (directory / "metrics.json").write_text("first")
        destination = self.root / "artifacts"
        destination.mkdir()
        for value in ("first", "second"):
            (directory / "metrics.json").write_text(value)
            subprocess.run(["rsync", "-a", "--relative", str(source) + "/./workspace/logs", str(destination) + "/"], check=True, capture_output=True)
        self.assertEqual((destination / "workspace/logs/metrics.json").read_text(), "second")
        self.assertFalse((destination / "workspace/logs/logs").exists())
        self.assertIn("--relative", self.build("pull", "workspace/logs")[-1])


class RemoteWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="job space' ")
        self.root = Path(self.temporary.name)
        self.worker = str(Path(remote_job.__file__).resolve())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_job(self, job_id: str, argv: list[str], cwd: str | None = None) -> Path:
        directory = remote_job.job_path(self.root, job_id)
        directory.mkdir(parents=True)
        remote_job.atomic_json(directory / "spec.json", {"job_id": job_id, "argv": argv, "cwd": cwd or str(self.root)})
        remote_job.atomic_json(directory / "status.json", {"job_id": job_id, "state": "queued"})
        return directory

    def worker_command(self, operation: str, job_id: str) -> list[str]:
        return [sys.executable, self.worker, "--root", str(self.root), operation, "--id", job_id]

    def test_wrapper_preserves_literal_args_and_success(self) -> None:
        values = ["$(touch exploit)", "a';echo pwned;#", "line\nsecond"]
        directory = self.make_job("ok", [sys.executable, "-c", "import json,sys;print(json.dumps(sys.argv[1:]))", *values])
        result = subprocess.run(self.worker_command("_run", "ok"), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((directory / "console.log").read_text()), values)
        self.assertEqual(remote_job.read_status(directory)["state"], "succeeded")
        self.assertFalse((self.root / "exploit").exists())

    def test_wrapper_records_failure_and_missing_program(self) -> None:
        for job_id, argv, expected in (("fail", [sys.executable, "-c", "print('failure');raise SystemExit(7)"], 7), ("missing", ["/program-does-not-exist"], 127)):
            directory = self.make_job(job_id, argv)
            result = subprocess.run(self.worker_command("_run", job_id), capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, expected)
            status = remote_job.read_status(directory)
            self.assertEqual((status["state"], status["exit_code"]), ("failed", expected))

    def test_queued_stop_cancels_command_and_missing_cwd_is_failed(self) -> None:
        directory = self.make_job("queued", [sys.executable, "-c", "from pathlib import Path;Path('should-not-run').touch()"])
        self.assertTrue(remote_job.stop(directory)["stop_requested"])
        result = subprocess.run(self.worker_command("_run", "queued"), capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 143)
        self.assertFalse((self.root / "should-not-run").exists())
        self.assertEqual(remote_job.read_status(directory)["state"], "stopped")
        failed = self.make_job("badcwd", [sys.executable, "-c", "pass"], str(self.root / "deleted"))
        result = subprocess.run(self.worker_command("_run", "badcwd"), capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(remote_job.read_status(failed)["state"], "failed")

    def test_scoped_paths_reject_external_symlinks(self) -> None:
        (self.root / "outside").symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            remote_job.scoped_path(self.root, "outside")
        with self.assertRaises(ValueError):
            remote_job.scoped_path(self.root, "../other")
        result = subprocess.run([sys.executable, self.worker, "--root", str(self.root), "exec", "--cwd", "outside", "--", "true"], capture_output=True)
        self.assertNotEqual(result.returncode, 0)

    def test_tmux_start_quotes_wrapper_and_refuses_duplicate_job(self) -> None:
        args = type("Args", (), {"argv": ["--", sys.executable, "-c", "pass"], "cwd": ".", "id": "new"})()
        with mock.patch("remote_job.shutil.which", return_value="/usr/bin/tmux"), mock.patch("remote_job.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
            self.assertEqual(remote_job.start(self.root, args)["state"], "queued")
            tmux = run.call_args.args[0]
            self.assertEqual(tmux[:5], ["/usr/bin/tmux", "new-session", "-d", "-s", "ea-new"])
            self.assertEqual(shlex.split(tmux[-1])[-3:], ["_run", "--id", "new"])
            self.assertIn(str(self.root), shlex.split(tmux[-1]))
            with self.assertRaises(FileExistsError):
                remote_job.start(self.root, args)

    def test_stop_does_not_signal_a_reused_pid(self) -> None:
        directory = self.make_job("stale", ["true"])
        remote_job.atomic_json(directory / "status.json", {"job_id": "stale", "state": "running", "runner_pid": 1234, "runner_start_ticks": "old"})
        with mock.patch("remote_job.process_identity", return_value="new"), mock.patch("remote_job.os.kill") as kill:
            self.assertFalse(remote_job.stop(directory)["stop_requested"])
            kill.assert_not_called()
        self.assertEqual(remote_job.read_status(directory)["state"], "interrupted")

    def test_stop_cleans_term_resistant_grandchild(self) -> None:
        grandchild_code = "import os,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);open('grandchild.ready','w').write(str(os.getpid()));time.sleep(60)"
        leader_code = "import pathlib,subprocess,sys,time;subprocess.Popen([sys.executable,'-c',sys.argv[1]]);\nwhile not pathlib.Path('grandchild.ready').exists(): time.sleep(.02)\ntime.sleep(60)"
        directory = self.make_job("stop", [sys.executable, "-c", leader_code, grandchild_code])
        runner = subprocess.Popen(self.worker_command("_run", "stop"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / "grandchild.ready").exists() and time.monotonic() < deadline:
                if runner.poll() is not None:
                    self.fail("runner quit before starting grandchild: " + str(runner.communicate()))
                time.sleep(0.02)
            self.assertTrue((self.root / "grandchild.ready").exists())
            grandchild_pid = int((self.root / "grandchild.ready").read_text())
            self.assertTrue(remote_job.stop(directory)["stop_requested"])
            _out, error = runner.communicate(timeout=12)
            self.assertEqual(runner.returncode, 143, error)
            self.assertEqual(remote_job.read_status(directory)["state"], "stopped")
            deadline = time.monotonic() + 1
            while remote_job.process_identity(grandchild_pid) is not None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertIsNone(remote_job.process_identity(grandchild_pid), "grandchild is still running")
        finally:
            status = json.loads((directory / "status.json").read_text())
            child_pid = status.get("child_pid")
            if child_pid:
                try:
                    os.killpg(child_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if runner.poll() is None:
                runner.kill()
            runner.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
