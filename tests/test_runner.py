import contextlib
import os
import sys
import unittest

from waitress import runner


class Test_run(unittest.TestCase):
    def match_output(self, argv, code, regex):
        argv = ["waitress-serve"] + argv
        with capture() as captured:
            self.assertEqual(runner.run(argv=argv), code)
        self.assertRegex(captured.getvalue(), regex)
        captured.close()

    def test_bad(self):
        self.match_output(["--bad-opt"], 1, "^Error: option --bad-opt not recognized")

    def test_help(self):
        self.match_output(["--help"], 0, "^Usage:\n\n    waitress-serve")

    def test_no_app(self):
        self.match_output([], 1, "^Error: Specify an application")

    def test_multiple_apps_app(self):
        self.match_output(["a:a", "b:b"], 1, "^Error: Provide only one WSGI app")
        self.match_output(["--app=a:a", "b:b"], 1, "^Error: Provide only one WSGI app")

    def test_bad_apps_app(self):
        self.match_output(["a"], 1, "No module named 'a'")

    def test_bad_app_module(self):
        self.match_output(["nonexistent:a"], 1, "No module named 'nonexistent'")

    def test_cwd_added_to_path(self):
        def null_serve(app, **kw):
            pass

        sys_path = sys.path
        current_dir = os.getcwd()
        try:
            os.chdir(os.path.dirname(__file__))
            argv = [
                "waitress-serve",
                "fixtureapps.runner:app",
            ]
            self.assertEqual(runner.run(argv=argv, _serve=null_serve), 0)
        finally:
            sys.path = sys_path
            os.chdir(current_dir)

    def test_bad_app_object(self):
        self.match_output(
            ["tests.fixtureapps.runner:a"],
            1,
            "module 'tests.fixtureapps.runner' has no attribute 'a'",
        )

    def test_simple_call(self):
        from tests.fixtureapps import runner as _apps

        def check_server(app, **kw):
            self.assertIs(app, _apps.app)
            self.assertDictEqual(kw, {"port": "80"})

        argv = [
            "waitress-serve",
            "--port=80",
            "tests.fixtureapps.runner:app",
        ]
        self.assertEqual(runner.run(argv=argv, _serve=check_server), 0)

    def test_returned_app(self):
        from tests.fixtureapps import runner as _apps

        def check_server(app, **kw):
            self.assertIs(app, _apps.app)
            self.assertDictEqual(kw, {"port": "80"})

        argv = [
            "waitress-serve",
            "--port=80",
            "--call",
            "tests.fixtureapps.runner:returns_app",
        ]
        self.assertEqual(runner.run(argv=argv, _serve=check_server), 0)


@contextlib.contextmanager
def capture():
    from io import StringIO

    fd = StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = fd
    sys.stderr = fd
    try:
        yield fd
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
