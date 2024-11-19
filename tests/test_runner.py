import contextlib
import os
import sys
import unittest

from waitress import adjustments, runner


def test_valid_socket():
    assert runner._valid_socket("0.0.0.0:42") == ("0.0.0.0", "42")
    assert runner._valid_socket("[2001:db8::1]:42") == ("2001:db8::1", "42")


class Test_run(unittest.TestCase):
    def match_output(self, argv, code, regex):
        argv = ["waitress-serve"] + argv
        with capture() as captured:
            try:
                self.assertEqual(runner.run(argv=argv), code)
            except SystemExit as exit:
                self.assertEqual(exit.code, code)
        self.assertRegex(captured.getvalue(), regex)
        captured.close()

    def test_no_app(self):
        self.match_output([], 1, "^Error: Specify one and only one WSGI application")

    def test_multiple_apps_app(self):
        self.match_output(
            ["--app", "a:a", "--app", "b:b"],
            1,
            "^Error: Specify one and only one WSGI application",
        )

    def test_bad_apps_app(self):
        self.match_output(["--app", "a"], 1, "^Error: No module named 'a'")

    def test_bad_app_module(self):
        self.match_output(
            ["--app", "nonexistent:a"],
            1,
            "^Error: No module named 'nonexistent'",
        )

    def test_cwd_added_to_path(self):
        def null_serve(app, **kw):
            pass

        sys_path = sys.path
        current_dir = os.getcwd()
        try:
            os.chdir(os.path.dirname(__file__))
            argv = [
                "waitress-serve",
                "--app",
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
            "^Error: module 'tests.fixtureapps.runner' has no attribute 'a'",
        )

    def test_simple_call(self):
        from tests.fixtureapps import runner as _apps

        def check_server(app, **kw):
            self.assertIs(app, _apps.app)
            self.assertEqual(kw["port"], 80)

        argv = [
            "waitress-serve",
            "--port=80",
            "--app=tests.fixtureapps.runner:app",
        ]
        self.assertEqual(runner.run(argv=argv, _serve=check_server), 0)

    def test_good_listen(self):
        from tests.fixtureapps import runner as _apps

        def check_server(app, **kw):
            self.assertIs(app, _apps.app)
            adj = adjustments.Adjustments(**kw)
            self.assertListEqual(
                [entry[3] for entry in adj.listen],
                [("127.0.0.1", 80)],
            )

        argv = [
            "waitress-serve",
            "--listen=127.0.0.1:80",
            "--app=tests.fixtureapps.runner:app",
        ]
        self.assertEqual(runner.run(argv=argv, _serve=check_server), 0)

    def test_returned_app(self):
        from tests.fixtureapps import runner as _apps

        def check_server(app, **kw):
            self.assertIs(app, _apps.app)
            self.assertEqual(kw["port"], 80)

        argv = [
            "waitress-serve",
            "--port=80",
            "--call",
            "--app=tests.fixtureapps.runner:returns_app",
        ]
        self.assertEqual(runner.run(argv=argv, _serve=check_server), 0)

    def test_bad_listen(self):
        self.match_output(
            [
                "--listen=foo/bar",
                "--app=tests.fixtureapps.runner:app",
            ],
            2,
            "error: argument --listen: invalid _valid_socket value: 'foo/bar'",
        )

    def test_inet(self):
        self.match_output(
            [
                "--listen=127.0.0.1:8080",
                "--host=127.0.0.1",
                "--app=tests.fixtureapps.runner:app",
            ],
            2,
            "error: argument --host: not allowed with argument --listen",
        )

    def test_inet_and_unix_socket(self):
        self.match_output(
            [
                "--host=127.0.0.1",
                "--unix-socket=/tmp/waitress.sock",
                "--app=tests.fixtureapps.runner:app",
            ],
            2,
            "error: argument --unix-socket: not allowed with argument --host",
        )

    def test_listen_and_unix_socket(self):
        self.match_output(
            [
                "--listen=127.0.0.1:8080",
                "--unix-socket=/tmp/waitress.sock",
                "--app=tests.fixtureapps.runner:app",
            ],
            2,
            "error: argument --unix-socket: not allowed with argument --listen",
        )


@contextlib.contextmanager
def capture():
    from io import StringIO

    fd = StringIO()
    sys.stdout = fd
    sys.stderr = fd
    yield fd
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__
