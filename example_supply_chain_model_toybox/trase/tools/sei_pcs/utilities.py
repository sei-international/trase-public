import tracemalloc
import linecache
import contextlib
import sys
import functools

from datetime import datetime

import os

# set TRASE_USE_TRACEMALLOC=1 to print memory usage of each model step
USE_TRACEMALLOC = os.environ.get("TRASE_USE_TRACEMALLOC", "") == "1"


@contextlib.contextmanager
def tee(
    filename, mode="a", prefix="[%H:%M:%S] ", open_kwargs=None, stdout=True, stderr=True
):
    """Capture stdout and/or stderr and write to to both a file and to stdout.

    We also prefix every line with a timestamp. By default both stdout and sterr are
    captured, and they are both sent to stdout.

    ## Example

    The following code:

    ```python
    with tee("my_log.txt"):
       print("this is your captain speaking")
    ```

    Will result in the following being written to both the console *and* "my_log.txt"

    ```
    [15:09:08] this is your captain speaking
    ```

    Args:
        filename (str): path to the file that should be opened
        mode (str, optional): file opening mode, e.g "w" or "a"
        open_kwargs (dict, optional): other keyword arguments passed to Python's `open`
            built-in
        prefix (str, optional): an optional prefix that will be passed to
            `datetime.strftime`, or `None` if there should be no prefix
        stdout (bool, optional): whether to capture stdout
        stderr (bool, optional): whether to capture stderr
    """

    # define a "no-op" context manager for later. should use contextlib.nullcontext for
    # Python 3.7+, but here we need to be compatible with DeforestationFree (Python 3.6)
    noop = contextlib.suppress

    # store the terminal output stream. this needs to be done before the call to
    # redirect_stdout
    terminal = sys.stdout

    # open the file
    with open(filename, mode=mode, **(open_kwargs or {})) as file:
        # store the original file_write method
        write_to_file = file.write

        # define a new file write method
        needs_prefix = True

        def new_write_function(text):
            nonlocal needs_prefix

            # add prefix if needed
            if prefix and needs_prefix:
                text = datetime.now().strftime(prefix) + text
                needs_prefix = False

            # write to terminal
            terminal.write(text)

            # write to file
            write_to_file(text)

            # if this string had a newline, the *next* call to write should be prefixed
            if "\n" in text:
                needs_prefix = True

        file.write = new_write_function

        # now capture stdout and/or stderr using the above modified file handle
        with contextlib.redirect_stdout(file) if stdout else noop:
            with contextlib.redirect_stderr(file) if stderr else noop:
                yield


def trace_memory_allocation(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if USE_TRACEMALLOC:
            tracemalloc.start(500)
            try:
                return_value = func(*args, **kwargs)
            finally:
                snapshot = tracemalloc.take_snapshot()
                display_top(snapshot)
                tracemalloc.stop()
            return return_value
        else:
            return func(*args, **kwargs)

    return wrapper


def display_top(snapshot, limit=20):
    top_stats = snapshot.statistics("lineno", cumulative=True)

    print("Memory usage top %s lines" % limit)
    for index, stat in enumerate(top_stats[:limit], 1):
        frame = stat.traceback[0]
        print(
            "#%s: %s:%s: %.1f KiB"
            % (index, frame.filename, frame.lineno, stat.size / 1024)
        )
        line = linecache.getline(frame.filename, frame.lineno).strip()
        if line:
            print("    %s" % line)

    other = top_stats[limit:]
    if other:
        size = sum(stat.size for stat in other)
        print("%s other: %.1f KiB" % (len(other), size / 1024))
    total = sum(stat.size for stat in top_stats)
    print("Total allocated size: %.1f KiB" % (total / 1024))
