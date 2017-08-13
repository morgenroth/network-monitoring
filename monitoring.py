#!/usr/bin/python
import MySQLdb
import json
import ping
import socket
import threading
import time
import curses
import urlparse
import paho.mqtt.client as mqtt
import json

from BaseHTTPServer import HTTPServer
from BaseHTTPServer import BaseHTTPRequestHandler


settings = json.load(open('settings.json'))

db = MySQLdb.connect(host=settings['mysql']['host'],
                     user=settings['mysql']['user'],
                     passwd=settings['mysql']['password'],
                     db=settings['mysql']['database'])

mqttc = mqtt.Client()

ignore_result = False
db_lock = threading.Lock()
result_lock = threading.Lock()
results = []


class JSONRequestHandler (BaseHTTPRequestHandler):
    def do_GET(self):
        global result_lock, results, ignore_result, db_lock
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
                db_lock.acquire()
                event_removed(params['tag'][0])
                db.commit()
                db_lock.release()

            result_lock.acquire()
            for device in results:
                if device['tag'] == params['tag'][0]:
                    results.remove(device)
            ignore_result = True
            result_lock.release()

            self.wfile.write(json.dumps({'result': 'ok', 'action': params['action'][0], 'tag': params['tag'][0]}))

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


def calculate_state(data):
    if data['rating'] >= 10.0:
        data['state'] = 'inactive'
    elif data['rating'] >= 5.0:
        data['state'] = 'unstable'
    else:
        data['state'] = 'active'
    return data


def calculate_rating(previous, current):
    if previous['rating'] is None:
        # calculate initial state and rating
        if current['latency'] > 0.05:
            current['rating'] = 5.0
        elif current['latency']:
            current['rating'] = 0.0
        else:
            current['rating'] = 10.0
    else:
        # based on previous rating
        current['rating'] = previous['rating']

        # increase/decrease rating according latency
        if current['latency'] > 0.05:
            current['rating'] = current['rating'] + 0.5
        elif current['latency']:
            current['rating'] = current['rating'] - 1.0
        else:
            current['rating'] = current['rating'] + 1.0

        # apply boundaries
        if current['rating'] < 0.0:
            current['rating'] = 0.0
        elif current['rating'] > 10.0:
            current['rating'] = 10.0

    #print("New rating for %s: %s" %(current['tag'], current['rating']))
    return current


def event_list_updated(data):
    global results

    # create lookup
    lookup = {}
    for item in results:
        lookup[item['tag']] = item

    # clear results
    del results[:]

    for current in data:
        try:
            previous = lookup[current['tag']]
            current = calculate_rating(previous, current)
            current = calculate_state(current)

            if not previous['state'] or previous['state'] != current['state']:
                event_state_changed(current['tag'], current['state'])
        except KeyError:
            event_info_changed(current['tag'], current)
            if current['state']:
                event_state_changed(current['tag'], current['state'])

        # finally use it as new result
        results.append(current)


def event_removed(tag):
    cur = db.cursor()
    cur.execute("""UPDATE `hosts` SET `deployed` = 0 WHERE `tag` = %s""", (tag,))
    cur.close()
    mqttc.publish("monitoring/devices/%s/info" % (tag), "")


def event_deployed(tag):
    cur = db.cursor()
    cur.execute("""UPDATE `hosts` SET `deployed` = 1 WHERE `tag` = %s""", (tag,))
    cur.close()


def event_info_changed(tag, data):
    info_keys = ["ipv4_address", "mac", "group", "name", "management_url", "description"]
    info = {}
    for key in info_keys:
        info[key] = data[key]

    mqttc.publish("monitoring/devices/%s/info" % (tag), json.dumps(info), retain=True)


def event_state_changed(tag, state):
    mqttc.publish("monitoring/devices/%s/state" % (tag), state, retain=True)


def discover():
    global db_lock
    db_lock.acquire()
    # you must create a Cursor object. It will let
    #  you execute all the queries you need
    cur = db.cursor()

    # Use all the SQL you like
    cur.execute(
        "SELECT `tag`, `ipv4_address` " +
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

        if ret:
            event_deployed(row[0])

    cur.close()
    db.commit()
    db_lock.release()


def queryAll():
    global db_lock
    devices = []
    db_lock.acquire()
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

        device = {
            'tag': row[0],
            'name': row[1],
            'description': row[2],
            'mac': row[3],
            'ipv4_address': row[4],
            'management_url': row[5],
            'latency': ret,
            'state': None,
            'group': row[6],
            'rating': None
        }

        if not device['management_url']:
            device['management_url'] = 'http://' + device['ipv4_address'] + '/'

        devices.append(device)

    cur.close()
    db.commit()
    db_lock.release()
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
        except:
            stdscr = None

        try:
            if stdscr:
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

                    result_lock.acquire()
                    if not ignore_result:
                        event_list_updated(ret)
                    else:
                        ignore_result = False
                    result_lock.release()

                    if stdscr:
                        self.report(stdscr, results)

                    time.sleep(1.0)

        finally:
            if stdscr:
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
    mqttc.connect(settings['mqtt']['host'], settings['mqtt']['port'], 60)
    mqttc.loop_start()
    mon = Monitor()
    mon.start()
    try:
        server = HTTPServer(("", settings['port']), JSONRequestHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        mon.stop()
    mon.join()
    mqttc.loop_stop()
