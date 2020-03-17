from angelo.mqtt import MqttClient
import os

class Event():
    def __init__(self):
        angelo_conf_path = os.path.expanduser("~") + "/.angelo/angelo.conf"
        self.mqtt_client = MqttClient("mqtt.pid", angelo_conf_path)
        self.mqtt_client.initialize_client()

    def dispatch(self, data):
        self.mqtt_client.publish_event(data, "event")
