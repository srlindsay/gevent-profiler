import sys

sys.path = ['.'] + sys.path

import time
import gevent
import gevent_profiler
from gevent import monkey

def eat_up_cpu():
	for x in range(100):
		for y in range(100):
			z = x * y

def eat_up_some_more_cpu():
	for x in range(100):
		for y in range(100):
			z = x * y

def task():
	time.sleep(3)
	eat_up_cpu()
	eat_up_some_more_cpu()
	print "hi!"

def main():
	monkey.patch_all()

	tasks = []

	gevent_profiler.attach_on_signal(duration=5)

	while True:
		for x in range(3):
			y = gevent.spawn(task)
			tasks.append(y)
		
		gevent.joinall(tasks)

if __name__ == "__main__":
	main()

