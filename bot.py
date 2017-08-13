#!/usr/bin/python
import sleekxmpp
import paho.mqtt.client as mqtt
import json
import logging

settings = json.load(open('settings.json'))
mqttc = mqtt.Client()
xmpp = None


class Bot(sleekxmpp.ClientXMPP):

    def __init__(self, jid, password, room, nick):
        sleekxmpp.ClientXMPP.__init__(self, jid, password)

        self.room = room
        self.nick = nick

        self.add_event_handler("session_start", self.start)
        self.add_event_handler("groupchat_message", self.muc_message)

    def start(self, event):
        self.get_roster()
        self.send_presence()
        self.plugin['xep_0045'].joinMUC(self.room,
                                        self.nick,
                                        wait=True)

    def muc_message(self, msg):
        pass


def mqtt_message(client, userdata, msg):
    #print(msg.topic + " " + str(msg.payload))
    tag = msg.topic.split('/')[2]
    state = msg.payload
    xmpp.send_message(mto=settings['bot']['room'],
                      mbody="Device %s changed to *%s*" % (tag, state),
                      mtype='groupchat')


if __name__ == '__main__':
    # Setup logging.
    logging.basicConfig(level=logging.INFO,
                        format='%(levelname)-8s %(message)s')

    try:
        mqttc.on_message = mqtt_message
        mqttc.connect(settings['mqtt']['host'], settings['mqtt']['port'], 60)
        mqttc.subscribe("monitoring/devices/+/state")

        xmpp = Bot(settings['bot']['account'], settings['bot']['password'], settings['bot']['room'], "Monitor")
        xmpp.register_plugin('xep_0030')  # Service Discovery
        xmpp.register_plugin('xep_0045')  # Multi-User Chat
        xmpp.register_plugin('xep_0199')  # XMPP Ping

        if xmpp.connect(reattempt=True):
            mqttc.loop_start()
            xmpp.process(block=True)
            mqttc.loop_stop()
    except KeyboardInterrupt:
        pass
