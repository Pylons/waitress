import threading
import time

import waitress
from waitress.signals import signals

total_threads_by_server = dict()
busy_threads_by_server = dict()


def app(env, start_response):
    http_status = "200 OK"
    response_headers = [("Content-Type", "text/plain")]
    response_bytes = b"Hello World"
    start_response(http_status, response_headers)
    time.sleep(5)
    return [response_bytes]


@signals.get("server_started").connect
def server_started(server, *args, **kwargs):
    total_threads_by_server[server] = server.adj.threads
    busy_threads_by_server[server] = 0
    print(
        f"Started server listening on {server.addr} with {server.adj.threads} threads"
    )


@signals.get("server_finished").connect
def server_finished(server, *args, **kwargs):
    print(f"Stopped server listening on {server.addr}")


@signals.get("task_started").connect
def task_started(server, *args, task, **kwargs):
    busy_threads_by_server[server] += 1
    print(
        f"Thread {threading.current_thread().name} started task, {busy_threads_by_server[server]}/{total_threads_by_server[server]}"
    )


@signals.get("task_finished").connect
def task_finished(server, *args, task, **kwargs):
    busy_threads_by_server[server] -= 1
    print(
        f"Thread {threading.current_thread().name} finished task, {busy_threads_by_server[server]}/{total_threads_by_server[server]}"
    )


if __name__ == "__main__":
    waitress.serve(app, threads=2)
