#!/usr/bin/python
import MySQLdb
import json
import ping
import socket
import threading
import time
import curses

from BaseHTTPServer import HTTPServer
from BaseHTTPServer import BaseHTTPRequestHandler


settings = json.load(open('settings.json'))

db = MySQLdb.connect(host=settings['mysql']['host'],
                     user=settings['mysql']['user'],
                     passwd=settings['mysql']['password'],
                     db=settings['mysql']['database'])

result_lock = threading.Lock()
results = []


class JSONRequestHandler (BaseHTTPRequestHandler):
    def do_GET(self):

        # send response code:
        self.send_response(200)
        # send headers:
        self.send_header("Content-type", "application/json")
        # send a blank line to end headers:
        self.wfile.write("\r\n")
        result_lock.acquire()
        self.wfile.write(json.dumps(results))
        result_lock.release()


def queryAll():
    devices = []

    # you must create a Cursor object. It will let
    #  you execute all the queries you need
    cur = db.cursor()

    # Use all the SQL you like
    cur.execute(
        "SELECT `name`, `description`, `mac`, `ipv4_address`, `management_url` " +
        "FROM hosts " +
        "WHERE `ipv4_address` IS NOT NULL AND `deployed` = 1 " +
        "ORDER BY `name`")

    # print all the first cell of all the rows
    for row in cur.fetchall():
        try:
            ret = ping.do_one(row[3], 0.1)
        except socket.gaierror:
            ret = None

        device = {
            'name': row[0],
            'description': row[1],
            'mac': row[2],
            'ipv4_address': row[3],
            'management_url': row[4],
            'latency': ret
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
        global results
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
                ret = queryAll()
                self.report(stdscr, ret)
                result_lock.acquire()
                results = ret
                result_lock.release()
                time.sleep(0.5)

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
            if xoffset + 40 > dimen[1]:
                continue

            if device['latency'] > 0.05:
                color = curses.color_pair(3)
            elif device['latency']:
                color = curses.color_pair(2)
            else:
                color = curses.color_pair(1)

            stdscr.addstr(yoffset, xoffset, device['name'], color)

            if device['latency']:
                stdscr.addstr(yoffset, xoffset + 30, "%1.0f ms" % (device['latency'] * 1000.0), color)
            else:
                stdscr.addstr(yoffset, xoffset + 30, "lost", color)

            yoffset += 1
            if yoffset > (dimen[0] - 2):
                yoffset = 4
                xoffset += 40

        stdscr.refresh()

if __name__ == '__main__':
    mon = Monitor()
    mon.start()
    try:
        server = HTTPServer(("localhost", settings['port']), JSONRequestHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        mon.stop()
    mon.join()
