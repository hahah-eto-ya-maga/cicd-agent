import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from core.session import AgentSession
from services.task_logging import task_logging


class TaskLoggingTests(unittest.TestCase):
    def test_session_logs_prompt_model_and_tool_result_to_file_and_console(self):
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()) as console:
            root = Path(temp)
            content = "tool-result-" + "x" * 500 + "-end"
            (root / "input.txt").write_text(content, encoding="utf-8")
            replies = iter([
                NS(content="Читаю файл", tool_calls=[NS(
                    id="call-1", function=NS(name="read_file", arguments='{"path":"input.txt"}'),
                )]),
                NS(content="Итоговый ответ", tool_calls=[]),
            ])
            client = NS(chat=NS(completions=NS(create=lambda **kw: NS(
                choices=[NS(message=next(replies))],
            ))))
            with task_logging(root / "logs", attempt=2) as logger:
                session = AgentSession(client, "test", root, logger=logger)
                self.assertEqual(session.submit("Проверь файл"), "Итоговый ответ")
            paths = list((root / "logs").glob("attempt-2_*.log"))
            self.assertEqual(len(paths), 1)
            text = paths[0].read_text(encoding="utf-8")
            for expected in ("Проверь файл", "Читаю файл", "read_file", content, "Итоговый ответ"):
                self.assertIn(expected, text)
                self.assertIn(expected, console.getvalue())
            self.assertEqual(logger.handlers, [])

    def test_repeated_runs_have_distinct_files_and_do_not_mix_logs(self):
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()):
            directory = Path(temp)
            with task_logging(directory) as first:
                first.info("first-start")
                with task_logging(directory) as second:
                    second.info("second-only")
                    first.info("first-only")
            paths = list(directory.glob("*.log"))
            self.assertEqual(len(paths), 2)
            contents = [path.read_text(encoding="utf-8") for path in paths]
            self.assertEqual(sum("first-only" in text for text in contents), 1)
            self.assertEqual(sum("second-only" in text for text in contents), 1)
            self.assertFalse(any("first-only" in text and "second-only" in text for text in contents))

    def test_secrets_are_redacted_and_errors_are_saved(self):
        with tempfile.TemporaryDirectory() as temp, redirect_stdout(io.StringIO()) as console:
            with patch.dict("os.environ", {"GITHUB_TOKEN": "fake-github-secret"}):
                with task_logging(Path(temp)) as logger:
                    try:
                        raise ValueError("failure fake-github-secret")
                    except ValueError:
                        logger.exception("Preparation failed")
            text = next(Path(temp).glob("*.log")).read_text(encoding="utf-8")
            self.assertIn("Traceback", text)
            self.assertIn("failure ***", text)
            self.assertNotIn("fake-github-secret", text)
            self.assertNotIn("fake-github-secret", console.getvalue())


if __name__ == "__main__":
    unittest.main()
