#!/opt/Python-2.7.12/bin/python
import sys, os
import logging
import cStringIO
logging.basicConfig(stream=sys.stderr)
sys.path.insert(0,"/var/www/html/comptox.ni.epa.gov/genra-api")
sys.path.reverse()

from apps import app as application
application.secret_key = 'FOOBARBAZ'
#def application(environ, start_response):
#    status = '200 OK'
#    output = b'Hello Big World!'
#
#    response_headers = [('Content-type', 'text/plain'),
#                        ('Content-Length', str(len(output)))]
#    start_response(status, response_headers)
#
#    return [output]
