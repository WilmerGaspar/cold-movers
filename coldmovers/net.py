"""Calls to outside services that can never freeze the app."""


def call_with_timeout(fn, timeout_s: float, *args, **kwargs):
    """Run fn in a daemon thread; raise TimeoutError if it does not finish in time.

    External archives sometimes stop answering without closing the connection; a page
    must never wait for them forever. Daemon threads also never block the program exit.
    """
    import queue
    import threading

    box = queue.Queue(maxsize=1)

    def run():
        try:
            box.put((True, fn(*args, **kwargs)))
        except Exception as exc:  # passed back to the caller
            box.put((False, exc))

    threading.Thread(target=run, daemon=True, name="external-call").start()
    try:
        ok, value = box.get(timeout=timeout_s)
    except queue.Empty:
        raise TimeoutError(f"no answer within {timeout_s:.0f} s") from None
    if ok:
        return value
    raise value
