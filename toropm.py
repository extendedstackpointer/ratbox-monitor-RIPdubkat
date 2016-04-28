#!/usr/bin/env python2

'''
torOPM - Rid your IRC Server of TOR Exit Nodes.
Copyright (C) 2015-2016 Dan Reidy <dubkat+irc@gmail.com>

This program is free software: However, it is NOT for redistribution.
If you have been granted access to this code, it has been with the intention
you will use it to protect YOUR irc network or server from the abuses of
open proxies, partiuclarly The Onion Router Anonimizing network.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

'''

from modules.ircbot import SingleServerIRCBot
from modules.irclib import nm_to_n, nm_to_h, irc_lower, ip_numstr_to_quad, ip_quad_to_numstr
from collections import OrderedDict
import urllib2, sys, os, time
import sqlite3 as sql


class TorBot(SingleServerIRCBot):
    def __init__(self, channel, nickname, server, port=6667):
        SingleServerIRCBot.__init__(self, [(server, port)], nickname, "EFnet Onion Router Ban Hammer")
        self.channel = channel

    def on_nicknameinuse(self, c, e):
        c.nick(c.get_nickname() + "_")

    def on_welcome(self, c, e):
        c.oper( str(options.get('oper')), str(options.get('pass')) )
        c.send_raw("AWAY :I am network service. Find a real oper with /stats p")
        c.join(self.channel)
        c.execute_delayed(2, self.scrub_list, [c])
        c.execute_delayed(30 , self.banish_list, [c, e ] )

    def db_connect(self, c):
        try:
            con = sql.connect(str(options.get('database')))
            return con
        except sql.Error, e:
            c.privmsg(self.channel, "[ERROR] failed to connect to the database: %s" % e)
            sys.exit(1)

    def scrub_list(self, c):
        con = self.db_connect(c)
        cur = con.cursor()
        now = int(time.time())
        delta = now - (int(options.get('expire_time')) * 60 )
        count_sql = "SELECT count() AS count FROM node_state WHERE stamp <= '%d'" % delta
        #print "SQL: %s" % count_sql
        cur.execute(count_sql)
        result = cur.fetchall()
        count = result[0][0]
        if count:
            msg = "[status] %d klines are set to expire. flushing them from database." % count
            c.privmsg(self.channel, msg)
            cur.execute("DELETE FROM node_state WHERE stamp <= '%d'" % delta)
        else:
            msg = "[status] no klines are ready to expire. next list scrub is in 1 hour."
            c.privmsg(self.channel, msg)
            con.close()
            c.execute_delayed(3600, self.scrub_list, [c])

    def known_node(self, c, ip):
        query = "SELECT count() AS count FROM node_state WHERE address='%s'" % ip
        #print "SQL: %s" % query
        con = self.db_connect(c)
        cur = con.cursor()
        cur.execute(query)
        res = cur.fetchall()
        return int(res[0][0])

    def whitelisted_address(self, c, ip):
        query = "SELECT count() AS count FROM node_state WHERE address='%s'" % ip
        #print "SQL: %s" % query
        con = self.db_connect(c)
        cur = con.cursor()
        cur.execute(query)
        res = cur.fetchall()
        return (int(res[0][0]))

    def banish_list(self, c, e):
        ip_list = self.fetchTorlist()
        ip_size = len(ip_list)
        action = str(options.get('action_string'))
        now = int(time.time())
        con = self.db_connect(c)
        cur = con.cursor()
        i = 0
        for ip in ip_list:
            if not self.whitelisted_address(c, ip):
                if not self.known_node(c, ip):
                    insert = "INSERT INTO node_state VALUES(%d, '%s')" % (now, ip)
                    #print "SQL: %s" % insert
                    cur.execute(insert)
                    cmd = action.replace("%ip%", ip)
                    cmd = cmd.replace("%expire_time%", str(options.get('expire_time')))
                    msg = "TOR PROXY -> toropm@%s (TOR)" % (ip)
                    #print "PRIVMSG: %s" % msg
                    #print "COMMAND: %s" % cmd
                    c.privmsg(self.channel, msg)
                    c.send_raw(cmd)
                    i = i + 1
                    try:
                        con.commit()
                    except sql.Error, e:
                        c.privmsg(self.channel, "[error] an sql error has occured. rolling back." )
                    finally:
                        if con:
                            con.close()
                            status = "[status] Finished processing %d exit nodes active in the last 16 hours, of which %d are newly discovered on this pass." % (ip_size, i)
                            c.privmsg(self.channel, status)
                            c.execute_delayed(float(options.get('fetch_delay')) * 60 * 60, self.banish_list, [c, e])

    def fetchTorlist(self):
        l = []
        f = open(options.get('serverlist'))
        for server in f:
            response = urllib2.urlopen(options.get('torlist') + server )
            data = response.read().split("\n")
            for line in data[:-1]:
                if line[0] != '#':
                    l.append(line)
                    response.close()
                    f.close()
                    return list(OrderedDict.fromkeys(l))

    def parse_config(filename):
        options = {}
        f = open(filename)
        for line in f:
            # First, remove comments:
            '''
            if COMMENT_CHAR in line:
                # split on comment char, keep only the part before
                line, comment = line.split(COMMENT_CHAR, 1)
                '''
                # Second, find lines with an option=value:
                if OPTION_CHAR in line:
                    # split on option char:
                    option, value = line.split(OPTION_CHAR, 1)
                    # strip spaces:
                    option = option.strip()
                    value = value.strip()
                    # store in dictionary:
                    options[option] = value
                    f.close()
                    return options

    def db_init_setup():
        try:
            con = sql.connect(str(options.get('database')))
            cur = con.cursor()
            cur.execute('SELECT SQLITE_VERSION()')
            data = cur.fetchone()
            print "SQLite version: %s" % data
            cur.execute("CREATE TABLE IF NOT EXISTS node_state(stamp INT, address TEXT)")
            cur.execute("CREATE TABLE IF NOT EXISTS whitelist(stamp INT, address TEXT, oper TEXT)")
            con.commit()
            con.close()

        except sql.Error, e:
            sys.exit(1)

        finally:
            if con:
                con.close()

    def main():
        if len(sys.argv) != 2:
            print "Usage: toropm.py config"
            sys.exit(1)

            os.environ['TZ'] = 'UTC'
            time.tzset()

            nick = str(options.get('nick'))
            server = str(options.get('server'))
            port = int(options.get('port'))
            oper = str(options.get('oper'))
            passwd = str(options.get('pass'))
            channel = str(options.get('channels'))
            statedb = str(options.get('database'))

            print "server: " + server
            print "port: " + str(port)
            print "nick: " + nick
            print "oper: " + oper
            print "pass: " + passwd
            print "channels: " + channel
            print "klining exit nodes for %d minutes" % int(options.get('expire_time'))
            print "updating list ever %d hours" % float(options.get('fetch_delay'))

            db_init_setup()

            if os.fork():
                sys.exit()

                bot = TorBot(channel, nick, server, port)
                bot.start()




COMMENT_CHAR = '#'
OPTION_CHAR = '='
options = parse_config(sys.argv[1])
ip_list = {}

if __name__ == "__main__":
    main()
