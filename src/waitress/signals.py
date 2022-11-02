from typing import Optional


class SignalsRegistry:
    """Registry for signals used by waitress.

    The registry is mostly useful to gracefully switch to signals
    being no-ops when the blinker library is not available.
    """

    def __init__(self):
        try:
            import blinker
        except ImportError:
            self._blinker = None
        else:
            self._blinker = blinker

        self._signals = dict()

    def create(self, name: str, doc: Optional[str] = None):
        """Create a named signal."""
        if self._blinker is None:
            return

        self._signals[name] = self._blinker.NamedSignal(name, doc=doc)

    def get(self, name: str):
        """Retrieve a signal by its name."""
        if self._blinker is None:
            raise RuntimeError(
                "Signals cannot be used without the 'blinker' library installed"
            )

        if name not in self._signals:
            raise ValueError(f"Signal named '{name}' does not exist")

        return self._signals[name]

    def send(self, name: str, *args, **kwargs):
        if self._blinker is None:
            return []

        return self._signals[name].send(*args, **kwargs)


signals = SignalsRegistry()

signals.create(
    "channel_added",
    doc="""\
Sent by the event loop when a channel has been added.

Signal handlers receive:

- `server` :class:`BaseWSGIServer` that added the channel.
- `channel` :class:`Channel` being added.
""",
)

signals.create(
    "channel_deleted",
    doc="""\
Sent by the event loop when a channel has been deleted.

Signal handlers receive:

- `server` :class:`BaseWSGIServer` that deleted the channel.
- `channel` :class:`Channel` being deleted.
""",
)

signals.create(
    "server_started",
    doc="""\
Sent by the event loop when a server is started.

Signal handlers receive:

- `server` :class:`BaseWSGIServer` server being started.
""",
)

signals.create(
    "server_finished",
    doc="""\
Sent by the event loop when a server is finishing.

Signal handlers receive:

- `server` :class:`BaseWSGIServer` server stopping.
""",
)

signals.create(
    "task_started",
    doc="""\
Sent by a worker thread when a task is started.

Signal handlers receive:

- `server` :class:`BaseWSGIServer` that handles the task.
- `task` :class:`Task` being started.
""",
)

signals.create(
    "task_finished",
    doc="""\
Sent by a worker thread when a task is finished.

Signal handlers receive:

- `server` :class:`BaseWSGIServer` that handles the task.
- `task` :class:`Task` being finished.
""",
)
