# gevent-profiler

This module provides a simple way to get detailed profiling information
about a Python process that uses the `gevent` library.  The normal Python
profilers are not nearly as useful in this context, due to `gevent`'s
greenlet threading model.

## Installation

```bash
$ sudo python setup.py install
```

## Usage

To generate profiling information for a single function call:

```python
from gevent import monkey
monkey.patch_all()
import gevent_profiler

def my_func(a, b, c):
    print a, b, c

gevent_profiler.profile(my_func, 1, 2, c=3)
```

To generate profiling information for an arbitrary section of code:

```python
from gevent import monkey
monkey.patch_all()
import gevent_profiler

gevent_profiler.attach()
for x in range(42):
    print pow(x, 2)
gevent_profiler.detach()
```

To start generating profiling information when a specific signal is received,
and to stop after a set amount of time has elapsed:

```python
from gevent import monkey
monkey.patch_all()
import gevent_profiler

gevent_profiler.attach_on_signal(signum=signal.SIGUSR1, duration=60)

x = 2
while True:
    print pow(x, 50000)
```

To profile a Python app from the command line:

```bash
$ python gevent_profiler/__init__.py --help
$ python gevent_profiler/__init__.py my_app.py
```

## Options

Set the filename for the stats file.  Defaults to `sys.stdout`.  May be set to `None` to disable.

```python
gevent_profiler.set_stats_output('my-stats.txt')
```

Set the filename for the summary file.  Defaults to `sys.stdout`.  May be set to `None` to disable.

```python
gevent_profiler.set_summary_output('my-summary.txt')
```

Set the filename for the trace file.  Defaults to `sys.stdout`.  May be set to `None` to disable.

```python
gevent_profiler.set_trace_output('my-trace.txt')
```

Print runtime statistics as percentages of total runtime rather than absolute measurements in seconds:

```python
gevent_profiler.print_percentages(True)
```

Count time blocking on IO towards the execution totals for each function:

```python
gevent_profiler.time_blocking(True)
```

By default, there is a timeout of 60 seconds on the `attach`/`detach` methods. Change it or disable by
passing 0 to:

```python
gevent_profiler.set_attach_duration(120)
```

