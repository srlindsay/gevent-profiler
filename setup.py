from distutils.core import setup, Extension

long_description = """Gevent profiler"""

py_modules = [
		"gevent_profiler.__init__"
		#"gevent_profiler.gevent_profiler"
		]

setup(name = 'python-gevent-profiler',
	  version='0.2',
	  description='profiling utilities for gevent',
	  long_description = long_description,
	  author='meebo',
	  author_email='server@meebo.com',
	  url='http://random.meebo.com',
	  py_modules = py_modules
)

