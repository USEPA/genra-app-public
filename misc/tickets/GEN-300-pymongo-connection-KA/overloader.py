"""Here as part of work for GEN-300, just in case.
Makes multithreaded requests to `/testEp/`, and gets
the number of distinct id(DB). Run with command `Python3 overloader.py`.
Since the endpoint sleeps for 10 seconds, the goal is that this will
keep the "request" busy as other simultaneous requests are made.
By lowering the number of workers to 1, it can be seen that id(DB)
are all the same. Meanwhile, Lowering the number of threads to 1
(and letting number of workers be 5, for example) we see 5 distinct
id(DB). This confirms gunicorn doesn't share its Pymongo connection
with other workers, but does share with threads in a given worker."""

import json
import threading

import requests


class MyThread(threading.Thread):

    request_url = "http://127.0.0.1:31000/testEp/"

    def __init__(self, thread_id, results):
        threading.Thread.__init__(self)
        self.thread_id = thread_id
        self.request_url = "http://127.0.0.1:31000/testEp/"
        self.results = results

    def run(self):
        resp = requests.get(self.request_url)
        data = resp.json()
        dbid = data["dbid"]
        self.results[self.thread_id] = dbid


thread_count = 30
final_results = {}
thread_list = []

for idx in range(thread_count):
    thread_list.append(MyThread(idx, final_results))
for thread in thread_list:
    thread.start()
for thread in thread_list:
    thread.join()

id_count = {}
for thread_id, dbid in final_results.items():
    id_count[dbid] = id_count.get(dbid, 0) + 1

print("dbid and their count:")
print(json.dumps(id_count, indent=4))
