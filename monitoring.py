#!/usr/bin/python
import MySQLdb
import json
import ping
import socket
import threading
import time
import curses
import urlparse

from BaseHTTPServer import HTTPServer
from BaseHTTPServer import BaseHTTPRequestHandler


settings = json.load(open('settings.json'))

db = MySQLdb.connect(host=settings['mysql']['host'],
                     user=settings['mysql']['user'],
                     passwd=settings['mysql']['password'],
                     db=settings['mysql']['database'])

ignore_result = False
result_lock = threading.Lock()
results = []


class JSONRequestHandler (BaseHTTPRequestHandler):
    def do_GET(self):
        global result_lock, results, ignore_result
        url = urlparse.urlparse(self.path)
        params = urlparse.parse_qs(url.query)
        if url.path == "/modify":
            # send response code:
            self.send_response(200)
            # send headers:
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header("Content-type", "application/json")
            # send a blank line to end headers:
            self.wfile.write("\r\n")
            if params['action'][0] == 'undeploy':
                undeploy(params['mac'][0])
                db.commit()

            result_lock.acquire()
            for device in results:
                if device['mac'] == params['mac'][0]:
                    results.remove(device)
            ignore_result = True
            result_lock.release()

            self.wfile.write(json.dumps({'result': 'ok', 'action': params['action'][0], 'mac': params['mac'][0]}))

        elif self.path == "/":
            # send response code:
            self.send_response(200)
            # send headers:
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header("Content-type", "application/json")
            # send a blank line to end headers:
            self.wfile.write("\r\n")
            result_lock.acquire()
            self.wfile.write(json.dumps(results))
            result_lock.release()
        else:
            self.send_response(500)

    def log_message(self, format, *args):
        return


def undeploy(mac):
    cur = db.cursor()
    cur.execute("""UPDATE `hosts` SET `deployed` = 0 WHERE `mac` = %s""", (mac,))
    cur.close()


def deploy(mac):
    cur = db.cursor()
    cur.execute("""UPDATE `hosts` SET `deployed` = 1 WHERE `mac` = %s""", (mac,))
    cur.close()


def discover():
    # you must create a Cursor object. It will let
    #  you execute all the queries you need
    cur = db.cursor()

    # Use all the SQL you like
    cur.execute(
        "SELECT `mac`, `ipv4_address` " +
        "FROM hosts " +
        "WHERE `ipv4_address` IS NOT NULL AND `deployed` = 0 " +
        "ORDER BY `name`")

    # print all the first cell of all the rows
    for row in cur.fetchall():
        try:
            ret = ping.do_one(row[1], 0.1)
        except socket.error:
            ret = None
        except socket.gaierror:
            ret = None

        deploy(row[0])

    cur.close()
    db.commit()


def queryAll():
    devices = []

    # you must create a Cursor object. It will let
    #  you execute all the queries you need
    cur = db.cursor()

    # Use all the SQL you like
    cur.execute(
        "SELECT `tag`, `name`, `description`, `mac`, `ipv4_address`, `management_url`, `group` " +
        "FROM hosts " +
        "WHERE `ipv4_address` IS NOT NULL AND `deployed` = 1 " +
        "ORDER BY `name`")

    # print all the first cell of all the rows
    for row in cur.fetchall():
        try:
            ret = ping.do_one(row[4], 0.1)
        except socket.error:
            ret = None
        except socket.gaierror:
            ret = None

        if ret > 0.05:
            state = 'unstable'
        elif ret:
            state = 'active'
        else:
            state = 'inactive'

        device = {
            'tag': row[0],
            'name': row[1],
            'description': row[2],
            'mac': row[3],
            'ipv4_address': row[4],
            'management_url': row[5],
            'latency': ret,
            'state': state,
            'group': row[6]
        }

        if not device['management_url']:
            device['management_url'] = 'http://' + device['ipv4_address'] + '/'

        devices.append(device)

    cur.close()
    db.commit()
    return devices


class Monitor(threading.Thread):
    def __init__(self):
        ''' Constructor. '''

        threading.Thread.__init__(self)
        self.stop_signal = False

    def run(self):
        global result_lock, results, ignore_result
        try:
            stdscr = curses.initscr()

            # initialize curses colors
            curses.start_color()
            curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
            curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
            curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)

            curses.noecho()
            curses.cbreak()

            while not self.stop_signal:
                discover()
                time.sleep(1.0)

                for i in range(0, 10):
                    if self.stop_signal:
                        break

                    ret = queryAll()
                    self.report(stdscr, ret)
                    result_lock.acquire()
                    if not ignore_result:
                        results = ret
                    else:
                        ignore_result = False
                    result_lock.release()
                    time.sleep(1.0)

        finally:
            curses.echo()
            curses.nocbreak()
            curses.endwin()

    def stop(self):
        self.stop_signal = True

    def report(self, stdscr, ret):
        yoffset = 4
        xoffset = 2
        stdscr.clear()
        dimen = stdscr.getmaxyx()

        stdscr.addstr(0, 0, "########################")
        stdscr.addstr(1, 0, "## Network Monitoring ##")
        stdscr.addstr(2, 0, "########################")

        for device in ret:
            if xoffset + 41 > dimen[1]:
                continue

            if device['latency'] > 0.05:
                color = curses.color_pair(3)
            elif device['latency']:
                color = curses.color_pair(2)
            else:
                color = curses.color_pair(1)

            stdscr.addstr(yoffset, xoffset, device['tag'], color)

            if device['latency']:
                stdscr.addstr(yoffset, xoffset + 32, "%1.0f ms" % (device['latency'] * 1000.0), color)
            else:
                stdscr.addstr(yoffset, xoffset + 32, "lost", color)

            yoffset += 1
            if yoffset > (dimen[0] - 2):
                yoffset = 4
                xoffset += 41

        stdscr.refresh()

if __name__ == '__main__':
    mon = Monitor()
    mon.start()
    try:
        server = HTTPServer(("", settings['port']), JSONRequestHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        mon.stop()
    mon.join()
