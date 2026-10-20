import subprocess
import io
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from services.repository_loader import RepositoryLoader, RepositoryLoadError


class RepositoryLoaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git("init", str(self.source))
        self.git("-C", str(self.source), "config", "user.name", "Test")
        self.git("-C", str(self.source), "config", "user.email", "test@example.com")
        self.first = self.commit("first")
        self.second = self.commit("second")
        self.loader = RepositoryLoader(self.root / "repos")
        self.fetches = 0

        # Реальный Git и локальный remote: тест не обращается к GitHub.
        original_run = subprocess.run

        def local_remote(command, **kwargs):
            command = list(command)
            if "fetch" in command:
                self.fetches += 1
            command = [
                self.source.as_uri() if arg == "https://github.com/owner/repo.git" else arg
                for arg in command
            ]
            return original_run(command, **kwargs)

        mock = patch("services.repository_loader.subprocess.run", side_effect=local_remote)
        mock.start()
        self.addCleanup(mock.stop)

    def git(self, *args):
        return subprocess.run(
            ["git", *args], check=True, capture_output=True, text=True,
        ).stdout.strip()

    def commit(self, content):
        (self.source / "sample.txt").write_text(content, encoding="utf-8")
        self.git("-C", str(self.source), "add", "sample.txt")
        self.git("-C", str(self.source), "commit", "-m", content)
        return self.git("-C", str(self.source), "rev-parse", "HEAD")

    def test_exact_commit_cache_reuse_and_separate_workspaces(self):
        first = self.loader.workspace_path("owner/repo", 1)
        second = self.loader.workspace_path("owner/repo", 2)
        third = self.loader.workspace_path("owner/repo", 3)
        self.assertIsNone(self.loader.load("owner/repo", self.first, first))
        self.assertEqual((first / "sample.txt").read_text(), "first")
        self.assertEqual(self.git("-C", str(first), "rev-parse", "HEAD"), self.first)
        self.loader.load("owner/repo", self.first, second)
        self.assertEqual(self.fetches, 1)
        self.loader.load("owner/repo", self.second, third)
        self.assertEqual(self.fetches, 2)
        self.assertEqual((third / "sample.txt").read_text(), "second")
        (first / "sample.txt").write_text("edited", encoding="utf-8")
        self.assertEqual((second / "sample.txt").read_text(), "first")
        self.assertTrue((self.root / "repos/owner/repo/cache.git/HEAD").is_file())

    def test_repository_paths_include_owner(self):
        self.assertEqual(
            self.loader.workspace_path("owner/repo", 42),
            self.root / "repos/owner/repo/workspaces/task-42",
        )
        self.assertNotEqual(
            self.loader.workspace_path("owner/repo", 42),
            self.loader.workspace_path("other/repo", 42),
        )

    def test_missing_commit_raises_without_creating_workspace(self):
        workspace = self.root / "missing"
        with self.assertRaises(RepositoryLoadError):
            self.loader.load("owner/repo", "f" * 40, workspace)
        self.assertFalse(workspace.exists())

    def test_existing_workspace_is_not_overwritten(self):
        workspace = self.root / "existing"
        workspace.mkdir()
        marker = workspace / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        with self.assertRaises(RepositoryLoadError):
            self.loader.load("owner/repo", self.first, workspace)
        self.assertEqual(marker.read_text(), "keep")
        self.assertEqual(self.fetches, 0)

    def test_invalid_input_is_rejected_before_git(self):
        for repository, sha in [("../repo", self.first), ("owner/repo", "main")]:
            with self.subTest(repository=repository, sha=sha):
                with self.assertRaises(RepositoryLoadError):
                    self.loader.load(repository, sha, self.root / "invalid")
        self.assertEqual(self.fetches, 0)

    def test_worker_does_not_start_session_when_load_fails(self):
        from worker import worker_loop

        db = Mock()
        db.claim_next_task.side_effect = [
            {"id": 42, "repository": "owner/repo", "commit_sha": self.first},
            KeyboardInterrupt,
        ]
        loader = Mock()
        loader.workspace_path.return_value = self.root / "repos/owner/repo/workspaces/task-42"
        loader.load.side_effect = RepositoryLoadError("Download failed")
        with patch("worker.AgentSession") as session, redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                worker_loop(db, Mock(), "test", loader, Mock())
        session.assert_not_called()
        paths = list((self.root / "repos/owner/repo/logs/task-42").glob("*.log"))
        self.assertEqual(len(paths), 1)
        self.assertIn("Download failed", paths[0].read_text(encoding="utf-8"))

    def test_git_token_is_not_in_arguments_or_saved_config(self):
        self.loader = RepositoryLoader(self.root / "repos", token="test-secret")
        workspace = self.loader.workspace_path("owner/repo", 1)
        self.loader.load("owner/repo", self.first, workspace)
        config = (self.root / "repos/owner/repo/cache.git/config").read_text()
        self.assertNotIn("test-secret", config)
        self.assertNotIn("Authorization", config)
        with patch("services.repository_loader.subprocess.run") as run:
            run.return_value.returncode = 0
            self.loader._git("fetch", "https://github.com/owner/repo.git")
        self.assertNotIn("test-secret", str(run.call_args.args))
        env = run.call_args.kwargs["env"]
        self.assertTrue(any(
            key.startswith("GIT_CONFIG_VALUE_") and value.startswith("Authorization: Basic ")
            for key, value in env.items()
        ))

    def test_worker_saves_attempt_logs_before_starting_session(self):
        from worker import worker_loop

        workspace = self.root / "repos/owner/repo/workspaces/task-42"
        workspace.mkdir(parents=True)
        db = Mock()
        db.claim_next_task.side_effect = [
            {"id": 42, "repository": "owner/repo", "commit_sha": self.first,
             "run_id": 123, "run_attempt": 2},
            KeyboardInterrupt,
        ]
        loader = Mock()
        loader.workspace_path.return_value = workspace
        github = Mock()
        github.get_workflow_logs.return_value = "CI failed"
        with patch("worker.AgentSession") as session, redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                worker_loop(db, Mock(), "test", loader, github)
        github.get_workflow_logs.assert_called_once_with("owner/repo", 123, 2)
        self.assertEqual((workspace / "ci.log").read_text(), "CI failed")
        session.return_value.submit.assert_called_once()
        paths = list((self.root / "repos/owner/repo/logs/task-42").glob("*.log"))
        self.assertEqual(len(paths), 1)
        self.assertIn("Сессия задания 42 завершена", paths[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
