"""
    stegoproxy.reloader
    ~~~~~~~~~~~~~~~~~~~

    This module has been taken from werkzeug's `_reloader.py` module
    and adapted for our own needs.

    Werkzeug is released under the BSD License.
"""
import logging
import os
import subprocess
import sys
import threading
import time
from itertools import chain

log = logging.getLogger(__name__)


def _iter_module_files():
    """This iterates over all relevant Python files.  It goes through all
    loaded files from modules, all files in folders of already loaded modules
    as well as all files reachable through a package.
    """
    # The list call is necessary on Python 3 in case the module
    # dictionary modifies during iteration.
    for module in list(sys.modules.values()):
        if module is None:
            continue
        filename = getattr(module, "__file__", None)
        if filename:
            if os.path.isdir(filename) and os.path.exists(
                os.path.join(filename, "__init__.py")
            ):
                filename = os.path.join(filename, "__init__.py")

            old = None
            while not os.path.isfile(filename):
                old = filename
                filename = os.path.dirname(filename)
                if filename == old:
                    break
            else:
                if filename[-4:] in (".pyc", ".pyo"):
                    filename = filename[:-1]
                yield filename


def _find_observable_paths(extra_files=None):
    """Finds all paths that should be observed."""
    rv = set(
        os.path.dirname(os.path.abspath(x))
        if os.path.isfile(x)
        else os.path.abspath(x)
        for x in sys.path
    )

    for filename in extra_files or ():
        rv.add(os.path.dirname(os.path.abspath(filename)))

    for module in list(sys.modules.values()):
        fn = getattr(module, "__file__", None)
        if fn is None:
            continue
        fn = os.path.abspath(fn)
        rv.add(os.path.dirname(fn))

    return _find_common_roots(rv)


def _get_args_for_reloading():
    """Returns the executable."""
    rv = [sys.executable]
    py_script = sys.argv[0]
    rv.append(py_script)
    rv.extend(sys.argv[1:])
    return rv


def _find_common_roots(paths):
    """Out of some paths it finds the common roots that need monitoring."""
    paths = [x.split(os.path.sep) for x in paths]
    root = {}
    for chunks in sorted(paths, key=len, reverse=True):
        node = root
        for chunk in chunks:
            node = node.setdefault(chunk, {})
        node.clear()

    rv = set()

    def _walk(node, path):
        for prefix, child in node.items():
            _walk(child, path + (prefix,))
        if not node:
            rv.add("/".join(path))

    _walk(root, ())
    return rv


class ReloaderLoop(object):
    name = None

    # monkeypatched by testsuite. wrapping with `staticmethod` is required in
    # case time.sleep has been replaced by a non-c function (e.g. by
    # `eventlet.monkey_patch`) before we get here
    _sleep = staticmethod(time.sleep)

    def __init__(self, extra_files=None, interval=1):
        self.extra_files = set(os.path.abspath(x) for x in extra_files or ())
        self.interval = interval

    def run(self):
        pass

    def restart_with_reloader(self):
        """Spawn a new Python interpreter with the same arguments as this one,
        but running the reloader thread.
        """
        while 1:
            log.info("Restarting with %s" % self.name)
            args = _get_args_for_reloading()
            new_environ = os.environ.copy()

            new_environ["STEGOPROXY_RUN_MAIN"] = "true"
            exit_code = subprocess.call(args, env=new_environ, close_fds=False)
            if exit_code != 3:
                return exit_code

    def trigger_reload(self, filename):
        self.log_reload(filename)
        sys.exit(3)

    def log_reload(self, filename):
        filename = os.path.abspath(filename)
        log.info("Detected change in %r, reloading" % filename)


class StatReloaderLoop(ReloaderLoop):
    name = "stat"

    def run(self):
        mtimes = {}
        while 1:
            for filename in chain(_iter_module_files(), self.extra_files):
                try:
                    mtime = os.stat(filename).st_mtime
                except OSError:
                    continue

                old_time = mtimes.get(filename)
                if old_time is None:
                    mtimes[filename] = mtime
                    continue
                elif mtime > old_time:
                    self.trigger_reload(filename)
            self._sleep(self.interval)


class WatchdogReloaderLoop(ReloaderLoop):
    def __init__(self, *args, **kwargs):
        ReloaderLoop.__init__(self, *args, **kwargs)
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        self.observable_paths = set()

        def _check_modification(filename):
            if filename in self.extra_files:
                self.trigger_reload(filename)
            dirname = os.path.dirname(filename)
            if dirname.startswith(tuple(self.observable_paths)):
                if filename.endswith((".pyc", ".pyo", ".py")):
                    self.trigger_reload(filename)

        class _CustomHandler(FileSystemEventHandler):
            def on_created(self, event):
                _check_modification(event.src_path)

            def on_modified(self, event):
                _check_modification(event.src_path)

            def on_moved(self, event):
                _check_modification(event.src_path)
                _check_modification(event.dest_path)

            def on_deleted(self, event):
                _check_modification(event.src_path)

        reloader_name = Observer.__name__.lower()
        if reloader_name.endswith("observer"):
            reloader_name = reloader_name[:-8]
        reloader_name += " reloader"

        self.name = reloader_name

        self.observer_class = Observer
        self.event_handler = _CustomHandler()
        self.should_reload = False

    def trigger_reload(self, filename):
        # This is called inside an event handler, which means throwing
        # SystemExit has no effect.
        # https://github.com/gorakhargosh/watchdog/issues/294
        self.should_reload = True
        self.log_reload(filename)

    def run(self):
        watches = {}
        observer = self.observer_class()
        observer.start()

        try:
            while not self.should_reload:
                to_delete = set(watches)
                paths = _find_observable_paths(self.extra_files)
                for path in paths:
                    if path not in watches:
                        try:
                            watches[path] = observer.schedule(
                                self.event_handler, path, recursive=True
                            )
                        except OSError:
                            # Clear this path from list of watches We don't
                            # want the same error message showing again in the
                            # next iteration.
                            watches[path] = None
                    to_delete.discard(path)
                for path in to_delete:
                    watch = watches.pop(path, None)
                    if watch is not None:
                        observer.unschedule(watch)
                self.observable_paths = paths
                self._sleep(self.interval)
        finally:
            observer.stop()
            observer.join()

        sys.exit(3)


reloader_loops = {"stat": StatReloaderLoop, "watchdog": WatchdogReloaderLoop}

try:
    __import__("watchdog.observers")
except ImportError:
    reloader_loops["auto"] = reloader_loops["stat"]
else:
    reloader_loops["auto"] = reloader_loops["watchdog"]


def ensure_echo_on():
    """Ensure that echo mode is enabled. Some tools such as PDB disable
    it which causes usability issues after reload."""
    # tcgetattr will fail if stdin isn't a tty
    if not sys.stdin.isatty():
        return
    try:
        import termios
    except ImportError:
        return
    attributes = termios.tcgetattr(sys.stdin)
    if not attributes[3] & termios.ECHO:
        attributes[3] |= termios.ECHO
        termios.tcsetattr(sys.stdin, termios.TCSANOW, attributes)


def run_with_reloader(
    main_func, extra_files=None, interval=1, reloader_type="auto"
):
    """Run the given function in an independent python interpreter."""
    import signal

    reloader = reloader_loops[reloader_type](extra_files, interval)
    signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
    try:
        if os.environ.get("STEGOPROXY_RUN_MAIN") == "true":
            ensure_echo_on()
            t = threading.Thread(target=main_func, args=())
            t.setDaemon(True)
            t.start()
            reloader.run()
        else:
            sys.exit(reloader.restart_with_reloader())
    except KeyboardInterrupt:
        pass
