import io
import json
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from services.github_client import GitHubClient, GitHubError


def response(status, content=b"", headers=None):
    result = requests.Response()
    result.status_code = status
    result._content = content
    result._content_consumed = True
    result.headers.update(headers or {})
    return result


class GitHubClientTests(unittest.TestCase):
    def setUp(self):
        self.client = GitHubClient(token="test-secret")
        self.addCleanup(self.client.close)

    def test_downloads_exact_attempt_and_does_not_forward_token(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as logs:
            logs.writestr("job/step.txt", "AssertionError: test failed")
        redirect = response(302, headers={"Location": "https://logs.example/archive.zip"})
        with patch.object(self.client.session, "request", return_value=redirect) as api:
            with patch("services.github_client.requests.get", return_value=response(200, archive.getvalue())) as download:
                text = self.client.get_workflow_logs("owner/repo", 42, 2)
        self.assertIn("AssertionError: test failed", text)
        self.assertIn("=== job/step.txt ===", text)
        self.assertEqual(api.call_args.args[1], "https://api.github.com/repos/owner/repo/actions/runs/42/attempts/2/logs")
        self.assertFalse(api.call_args.kwargs["allow_redirects"])
        self.assertEqual(self.client.session.headers["Authorization"], "Bearer test-secret")
        self.assertNotIn("headers", download.call_args.kwargs)
        self.assertNotIn("auth", download.call_args.kwargs)

    def test_api_failure_does_not_expose_token(self):
        with patch.object(self.client.session, "request", return_value=response(403)):
            with self.assertRaises(GitHubError) as error:
                self.client.get_workflow_run("owner/repo", 42)
        self.assertIn("403", str(error.exception))
        self.assertNotIn("test-secret", str(error.exception))

    def test_invalid_archive_is_reported(self):
        redirect = response(302, headers={"Location": "https://logs.example/archive.zip"})
        with patch.object(self.client.session, "request", return_value=redirect):
            with patch("services.github_client.requests.get", return_value=response(200, b"not zip")):
                with self.assertRaises(GitHubError):
                    self.client.get_workflow_logs("owner/repo", 42, 1)

    def test_creates_draft_pr_with_explicit_branches(self):
        result = {"number": 1, "html_url": "https://github.com/owner/repo/pull/1"}
        with patch.object(self.client.session, "request", return_value=response(201, json.dumps(result).encode())) as api:
            self.assertEqual(
                self.client.create_pull_request("owner/repo", "Fix CI", "fix/ci", "main"),
                result,
            )
        self.assertEqual(api.call_args.kwargs["json"]["head"], "fix/ci")
        self.assertEqual(api.call_args.kwargs["json"]["base"], "main")
        self.assertTrue(api.call_args.kwargs["json"]["draft"])

    def test_repository_validation(self):
        with patch.object(self.client.session, "request") as api:
            with self.assertRaises(GitHubError):
                self.client.get_workflow_run("../repo", 42)
        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
