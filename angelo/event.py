from angelo.mqtt import MqttClient
from .configuration import SystemConfig, UserConfig

import os
import logging
import requests
import logging

class Event():
    def __init__(self, base_url):
        # TODO: consolidate the base_url to the context key inside angelo.conf
        self.mqtt = MQTTEvent()
        self.http = HTTPEvent(base_url)

class MQTTEvent():
    """
    TODO: Need to be updated later on
    """
    def __init__(self):
        angelo_conf_path = os.path.expanduser("~") + "/.angelo/angelo.conf"
        self.mqtt_client = MqttClient("mqtt.pid", angelo_conf_path)
        self.mqtt_client.initialize_client()

    def dispatch(self, data):
        self.mqtt_client.publish_event(data, "event")

class HTTPEvent():

    def __init__(self, base_url):
        angelo_config = SystemConfig()                
        self.config = angelo_config.config
        self.event_api = '{}/api/v1/events'.format(base_url)

    def dispatch(self, data={}, files=[]):
        # files should be a list of file path

        # data = {
        #     "type": "human_temperature",
        #     "value": maxTemp,
        # }
        
        headers = {
            'x-app-id': self.config.get('appid'),
            'x-app-secret': self.config.get('appsecret')
        }

        # bind unit id to the request data
        data['unit_id'] = self.config.get('channelid')

        attachments = map(lambda f: ('attachments[]', open(f, 'rb')), files) 

        try:
            # Remarks: always send through multipart to simplify the code base
            r = requests.post(
                url=self.event_api,
                data=data,
                headers=headers,
                files=attachments
            )
            logging.debug("POST response: {} ({})".format(r.text, str(r.status_code)))
						
        except requests.exceptions.RequestException as e:
            logging.error("Error POST'ing to {} ({})".format(args.app_api, e))