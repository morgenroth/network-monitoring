#!/usr/bin/python
import MySQLdb
import json
import socket
import hashlib

files = ['bridges.txt', 'hosts.txt', 'stations.txt', 'cams.txt']
dhcp_files = ['dhcpd.hosts', 'dhcpd.stations']

settings = json.load(open('settings.json'))

db = MySQLdb.connect(host=settings['mysql']['host'],
                     user=settings['mysql']['user'],
                     passwd=settings['mysql']['password'],
                     db=settings['mysql']['database'])

for f in files:
    fd = open(f)
    for line in fd.readlines():
        data = line.split()
        print(data)
        try:
            if len(data) == 2:
                c = db.cursor()
                c.execute("""INSERT INTO `hosts` (`mac`, `tag`) VALUES (LOWER(%s), %s)""", (data[1], data[0]))
                c.close()
            elif len(data) == 4:
                c = db.cursor()
                c.execute("""INSERT INTO `hosts` (`mac`, `tag`, `ipv4_address`) VALUES (LOWER(%s), %s, %s)""", (data[1], data[2], data[0]))
                c.close()
            else:
                print("Unknown format: " + str(data))
        except MySQLdb.IntegrityError:
            if len(data) == 2:
                c = db.cursor()
                c.execute("""UPDATE `hosts` SET `name` = %s WHERE `mac` = %s""", (data[0], data[1]))
                c.close()
            elif len(data) == 4:
                c = db.cursor()
                c.execute("""UPDATE `hosts` SET `tag` = %s, `ipv4_address` = %s WHERE `mac` = %s""", (data[2], data[0], data[1]))
                c.close()
    fd.close()

for f in dhcp_files:
    fd = open(f)
    host = None
    mac = None
    ipv4_address = None
    for line in fd.readlines():
        data = line.split()
        if len(data) > 1:
            if data[0] == 'host':
                host = data[1]
            elif data[0] == 'hardware':
                mac = data[2].strip(";")
            elif data[0] == 'fixed-address':
                try:
                    ipv4_address = socket.gethostbyname(data[1].strip(";"))
                except socket.gaierror:
                    ipv4_address = data[1].strip(";")

        if host and mac and ipv4_address:
            print("dhcp", host, mac, ipv4_address)
            try:
                c = db.cursor()
                c.execute("""INSERT INTO `hosts` (`mac`, `tag`, `name`, `ipv4_address`) VALUES (LOWER(%s), %s, %s, %s)""", (mac, host, host, ipv4_address))
                c.close()
            except MySQLdb.IntegrityError:
                c = db.cursor()
                c.execute("""UPDATE `hosts` SET `name` = %s, `ipv4_address` = %s WHERE `mac` = %s AND `tag` != NULL""", (host, ipv4_address, mac))
                c.execute("""UPDATE `hosts` SET `tag` = %s, `name` = %s, `ipv4_address` = %s WHERE `mac` = %s AND `tag` = NULL""", (host, host, ipv4_address, mac))
                c.close()
            host = None
            mac = None
            ipv4_address = None

    fd.close()

fd = open("event.zone")
for line in fd.readlines():
    data = line.split()
    if len(data) > 2:
        if data[2] == 'A':
            if data[0].startswith(';'):
                continue

            m = hashlib.md5()
            for d in data:
                m.update(d)

            mac = "00:00:00:" + m.hexdigest()[:8]
            host = data[0]
            ipv4_address = data[3]

            print("bind", host, mac, ipv4_address)
            try:
                c = db.cursor()
                c.execute("""INSERT INTO `hosts` (`mac`, `tag`, `name`, `ipv4_address`) VALUES (LOWER(%s), %s, %s, %s)""", (mac, host, host, ipv4_address))
                c.close()
            except MySQLdb.IntegrityError:
                c = db.cursor()
                c.execute("""UPDATE `hosts` SET `name` = %s, `ipv4_address` = %s WHERE `tag` = %s""", (host, ipv4_address, host))
                c.close()
fd.close()

db.commit()
