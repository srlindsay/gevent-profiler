"""
Profiler for gevent
"""
import os
import sys
import time
import gevent
import signal
import inspect

_gls = {}
_curr_gl = None
_states = {}
_curr_states = {}

_stats_output_file = sys.stdout
_summary_output_file = sys.stdout
_trace_output_file = sys.stdout

_print_percentages = False
_time_blocking = False

_attach_expiration = None
_attach_duration = 60

_trace_began_at = None

class _State:
	def __init__(self):
		self.modulename = None
		self.co_name = None
		self.filename = None
		self.line_no = None
		self.start_time = None
		self.full_class = None
		self.elapsed = 0.0
		self.depth = 0
		self.calls = []
		self.parent = None
	def __str__(self):
		first = self.modulename
		if self.full_class:
			true_class = self.full_class
			# use inspect to find the method's true class
			for cls in inspect.getmro(self.full_class):
				if self.co_name in cls.__dict__:
					fnc = cls.__dict__[self.co_name]
					if hasattr(fnc, "func_code") and fnc.func_code.co_filename == self.filename and fnc.func_code.co_firstlineno == self.line_no:
						true_class = cls
			first = "%s.%s" % (true_class.__module__, true_class.__name__)
		return "%s.%s" % (first, self.co_name)

def _modname(path):
    """Return a plausible module name for the path."""

    base = os.path.basename(path)
    filename, ext = os.path.splitext(base)
    return filename

def _globaltrace(frame, event, arg):
	global _curr_gl

	if _attach_expiration is not None and time.time() > _attach_expiration:
		detach()
		return

	gl = gevent.greenlet.getcurrent()
	if gl not in _states:
		_states[gl] = _State()
		_curr_states[gl] = _states[gl]

	if _curr_gl is not gl:
		if _curr_gl is not None:
			_stop_timing(_curr_gl)
		_curr_gl = gl
		_start_timing(_curr_gl)

	code = frame.f_code
	filename = code.co_filename
	if filename:
		modulename = _modname(filename)
		if modulename is not None:
			_print_trace("[%s] call: %s: %s\n" % (gl, modulename, code.co_name))
	state = _State()
	_curr_states[gl].calls.append(state)
	state.parent = _curr_states[gl]
	_curr_states[gl] = state

	state.modulename = modulename
	state.filename = filename
	state.line_no = code.co_firstlineno
	state.co_name = code.co_name
	state.start_time = time.time()
	if 'self' in frame.f_locals:
		state.full_class = type(frame.f_locals['self'])

	tracefunc = _getlocaltrace(state)
	state.localtracefunc = tracefunc

	if modulename == 'hub' and code.co_name == 'switch' and not _time_blocking:
		_stop_timing(gl)

	return tracefunc

def _getlocaltrace(state):
	return lambda f, e, a: _localtrace(state, f, e, a)

def _localtrace(state, frame, event, arg):
	if _attach_expiration is not None and time.time() > _attach_expiration:
		detach()
		return

	gl = gevent.greenlet.getcurrent()
	code = frame.f_code
	filename = code.co_filename
	modulename = None
	if filename:
		modulename = _modname(filename)
	if event == 'return':
		if modulename is not None:
			_print_trace("[%s] return: %s: %s: %s\n" % (gl, modulename, code.co_name, code.co_firstlineno))
		if state.start_time is not None:
			state.elapsed += time.time() - state.start_time
		assert _curr_states[gl].parent is not None
		_curr_states[gl] = _curr_states[gl].parent
		return None
	
	return state.localtracefunc

def _stop_timing(gl):

	def _stop_timing_r(state):
		if state.start_time is not None:
			state.elapsed += time.time() - state.start_time
			state.start_time = None
		if state.parent is not None:
			_stop_timing_r(state.parent)

	if gl not in _curr_states:
		#if we're reattaching later, it's possible to call stop_timing
		#without a full set of current state
		return
	curr_state = _curr_states[gl]
	_stop_timing_r(curr_state)

def _start_timing(gl):

	def _start_timing_r(state):
		state.start_time = time.time()
		if state.parent is not None:
			_start_timing_r(state.parent)

	if gl not in _curr_states:
		#if we're reattaching later, it's possible to call start_timing
		#without a full set of current state
		return
	curr_state = _curr_states[gl]
	_start_timing_r(curr_state)

class _CallSummary:
	def __init__(self, name):
		self.name = name
		self.cumulative = 0.0
		self.count = 0
		self.own_cumulative = 0.0
		self.children_cumulative = 0.0

def _sum_calls(state, call_summaries):
	key = str(state)
	if key in call_summaries:
		call = call_summaries[key]
	else:
		call = _CallSummary(key)
		call_summaries[key] = call

	call.count += 1

	child_exec_time = 0.0
	for child in state.calls:
		child_exec_time += _sum_calls(child, call_summaries)
	
	call.cumulative += state.elapsed
	call.own_cumulative += state.elapsed - child_exec_time
	call.children_cumulative += child_exec_time
	return state.elapsed

def _maybe_open_file(f):
	if f is None:
		return None
	else:
		return open(f, 'w')

def _maybe_write(output_file, message):
	if output_file is not None:
		output_file.write(message)

def _maybe_flush(f):
	if f is not None:
		f.flush()

def _print_trace(msg):
	_maybe_write(_trace_output_file, msg)

def _print_stats_header(header):
	_maybe_write(_stats_output_file, "%40s %5s %12s %12s %12s\n" % header)
	_maybe_write(_stats_output_file, "="*86 + "\n")

def _print_stats(stats):
	_maybe_write(_stats_output_file, "%40s %5d %12f %12f %12f\n" % stats)

def _print_state(state, depth=0):
	_maybe_write(_summary_output_file, "%s %s %f\n" % ("."*depth, str(state), state.elapsed))
	for call in state.calls:
		_print_state(call, depth+2)

def _print_output(duration):
	call_summaries = {}
	for gl in _states.keys():
		_sum_calls(_states[gl], call_summaries)

	call_list = []
	for name in call_summaries:
		cs = call_summaries[name]
		call_list.append( (cs.cumulative, cs) )
	call_list.sort(reverse=True)

	output = []

	col_names = ["Call Name", "Count", "Cumulative", "Own Cumul", "Child Cumul", "Per Call", "Own/Total"]

	output.append(col_names)

	for _,c in call_list:
		cumulative = c.cumulative
		own_cumulative = c.own_cumulative
		children_cumulative = c.children_cumulative
		per_call = cumulative / c.count
		if cumulative == 0:
			own_ratio = "inf"
		else:
			own_ratio = "%6.2f" % (own_cumulative / cumulative * 100)

		col_data = [c.name, "%d" % c.count, "%12f" % cumulative, "%12f" % own_cumulative, "%12f" % children_cumulative, "%12f" % per_call, own_ratio]
		if _print_percentages:
			col_data[2] += " (%6.2f)" % (cumulative * 100 / duration)
			col_data[3] += " (%6.2f)" % (own_cumulative * 100 / duration)
			col_data[4] += " (%6.2f)" % (children_cumulative * 100 / duration)

		output.append(col_data)

	# max widths
	widths = [max([len(row[x]) for row in output]) for x in xrange(len(output[0]))]
	# build row strings
	fmt_out = [" ".join([x.ljust(widths[i]) for i, x in enumerate(row)]) for row in output]
	# insert col separation row
	fmt_out.insert(1, " ".join([''.ljust(widths[i], '=') for i in xrange(len(widths))]))
	# write them!
	map(lambda x: _maybe_write(_stats_output_file, "%s\n" % x), fmt_out)

	_maybe_flush(_stats_output_file)

	for gl in _states.keys():
		_maybe_write(_summary_output_file, "%s\n" % gl)
		_print_state(_states[gl])
		_maybe_write(_summary_output_file, "\n")
	_maybe_flush(_summary_output_file)

def attach():
	"""
	Start execution tracing
	"""
	global _attach_expiration
	global _attach_duration
	global _trace_began_at
	if _attach_expiration is not None:
		return
	now = time.time()
	_attach_expiration = now + _attach_duration
	_trace_began_at = now
	sys.settrace(_globaltrace)

def detach():
	"""
	Finish execution tracing, print the results and reset internal state
	"""
	global _gls
	global current_gl
	global _states
	global _curr_states
	global _attach_expiration
	global _trace_began_at

	# do we have a current trace?
	if not _trace_began_at:
		return

	duration = time.time() - _trace_began_at
	_attach_expiration = None
	sys.settrace(None)
	_maybe_flush(_trace_output_file)
	_print_output(duration)
	_gls = {}
	_curr_gl = None
	_states = {}
	_curr_states = {}
	_trace_began_at = None
	curr_state = None

def profile(func, *args, **kwargs):
	"""
	Takes a function and the arguments to pass to that function and runs it
	with profiling enabled.  On completion of that function, the profiling 
	results are printed.
	"""
	sys.settrace(_globaltrace)
	trace_began_at = time.time()
	func(*args, **kwargs)
	sys.settrace(None)
	_maybe_flush(_trace_output_file)
	_print_output(time.time() - trace_began_at)

def set_stats_output(f):
	"""
	Takes a filename and will write the call timing statistics there
	"""
	global _stats_output_file
	_stats_output_file = _maybe_open_file(f)

def set_summary_output(f):
	"""
	Takes a filename and will write the execution summary there
	"""
	global _summary_output_file
	_summary_output_file = _maybe_open_file(f)

def set_trace_output(f):
	"""
	Takes a filename and writes the execution trace information there
	"""
	global _trace_output_file
	_trace_output_file = _maybe_open_file(f)

def print_percentages(enabled=True):
	"""
	Pass True if you want statistics to be output as percentages of total
	run time instead of absolute measurements.
	"""
	global _print_percentages
	_print_percentages = enabled

def time_blocking(enabled=True):
	"""
	Pass True if you want to count time blocking on IO towards the execution
	totals for each function.  The default setting for this is False, which
	is probably what you're looking for in most cases.
	"""
	global _time_blocking
	_time_blocking = enabled

def _sighandler(signum, frame):
	attach()

def attach_on_signal(signum=signal.SIGUSR1, duration=60):
	"""
	Sets up signal handlers so that, upon receiving the specified signal,
	the process starts outputting a full execution trace.  At the expiration
	of the specified duration, a summary of all the greenlet activity during
	that period is output.
	See set_summary_output and set_trace_output for information about how
	to configure where the output goes.
	By default, the signal is SIGUSR1.
	"""
	signal.signal(signum, _sighandler)
	global _attach_duration
	_attach_duration = duration

if __name__ == "__main__":
	from optparse import OptionParser
	parser = OptionParser()
	parser.add_option("-a", "--stats", dest="stats",
			help="write the stats to a file",
			metavar="STATS_FILE")
	parser.add_option("-s", "--summary", dest="summary",
			help="write the summary to a file",
			metavar="SUMMARY_FILE")
	parser.add_option("-t", "--trace", dest="trace",
			help="write the trace to a file",
			metavar="TRACE_FILE")
	parser.add_option("-p", "--percentages", dest="percentages",
			action='store_false',
			help="print stats as percentages of total runtime")
	parser.add_option("-b", "--blocking", dest="blocking",
			action='store_false',
			help="count blocked time toward execution totals")
	(options, args) = parser.parse_args()
	if options.stats is not None:
		set_stats_output(options.stats)
	if options.summary is not None:
		set_summary_output(options.summary)
	if options.trace is not None:
		set_trace_output(options.trace)
	if options.percentages is not None:
		print_percentages()
	if options.blocking is not None:
		time_blocking()
	if len(args) < 1:
		print "what file should i be profiling?"
		sys.exit(1)
	file = args[0]

	trace_began_at = time.time()
	sys.settrace(_globaltrace)
	execfile(file)
	sys.settrace(None)
	_print_output(time.time() - trace_began_at)
