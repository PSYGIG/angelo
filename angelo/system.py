# -*- coding: utf-8 -*- 
# /*
#  * Copyright (C) 2019 PSYGIG株式会社
#  * Copyright (C) 2019 Docker Inc.
#  *
#  * Licensed under the Apache License, Version 2.0 (the "License");
#  * you may not use this file except in compliance with the License.
#  * You may obtain a copy of the License at
#  *
#  * http://www.apache.org/licenses/LICENSE-2.0
#  *
#  * Unless required by applicable law or agreed to in writing, software
#  * distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.
#  */

import six
import requests
import json
import os
import configparser
import logging
import sys
from signal import SIGTERM
import random
import ssl
import websockets
import asyncio
import argparse

from .process import Process
from .supervisor import Supervisor
from .errors import OperationFailedError
from .mqtt import MqttClient

# TODO: Change to staging/production?
DEVICE_REGISTRATION_API_ENDPOINT = "http://localhost:4000/api/v1/device"
GROUP_SEARCH_ENDPOINT = "http://localhost:4000/api/v1/user/namespaces"

class System(object):
    """
    A system consisting of processes
    """
    def __init__(self, name, services, config_version=None):
        self.name = name
        self.services = services
        self.config_version = config_version
        self.supervisor = Supervisor(services)
        self.angelo_conf = os.path.expanduser("~") + "/.angelo/angelo.conf"
        self.mqtt_client = MqttClient("mqtt.pid", self.angelo_conf)

    @classmethod
    def from_config(cls, name, config_data, default_platform=None):
        """
        Construct a Project from a config.Config object.
        """
        system = cls(name, [], config_data.version)

        for service_dict in config_data.services:
            service_dict = dict(service_dict)

            system.services.append(
                Process(
                    service_dict.pop('name'),
                    pid_mode=None,
                    platform=service_dict.pop('platform', None),
                    default_platform=default_platform,
                    **service_dict)
            )

        return system

    def get_service(self, name):
        """
        Retrieve a service by name. Raises NoSuchService
        if the named service does not exist.
        """
        for service in self.services:
            if service.name == name:
                return service

        raise NoSuchService(name)

    @property
    def service_names(self):
        return [service.name for service in self.services]

    def validate_service_names(self, service_names):
        """
        Validate that the given list of service names only contains valid
        services. Raises NoSuchService if one of the names is invalid.
        """
        valid_names = self.service_names
        for name in service_names:
            if name not in valid_names:
                raise NoSuchService(name)

    def get_services(self, service_names=None, include_deps=False):
        """
        Returns a list of this project's services filtered
        by the provided list of names, or all services if service_names is None
        or [].
        If include_deps is specified, returns a list including the dependencies for
        service_names, in order of dependency.
        Preserves the original order of self.services where possible,
        reordering as needed to resolve dependencies.
        Raises NoSuchService if any of the named services do not exist.
        """
        if service_names is None or len(service_names) == 0:
            service_names = self.service_names

        unsorted = [self.get_service(name) for name in service_names]
        services = [s for s in self.services if s in unsorted]
        """
        if include_deps:
            services = reduce(self._inject_deps, services, [])
        """
        uniques = []
        [uniques.append(s) for s in services if s not in uniques]

        return uniques

    def register(self, identifier=None, id=None, secret=None):
        data = {
            'identifier': identifier,
            'app_id': id,
            'app_secret': secret
        }

        namespace_response = requests.get(GROUP_SEARCH_ENDPOINT, params=data)
        namespace_response_data = json.loads(namespace_response.text)

        if namespace_response.status_code == 200:
            total_namespaces = len(namespace_response_data['namespaces'])
            if total_namespaces > 1:
                print('\n#    Group Name')
                for i, v in enumerate(namespace_response_data['namespaces']):
                    print('{}    {}'.format(i+1, v['name']))
                try:
                    group_identifier = input("\nTarget Group #: ")
                    assert group_identifier != ""
                    assert int(group_identifier) <= total_namespaces
                    data['group_id'] = namespace_response_data['namespaces'][int(group_identifier)-1]['id']
                    group_id = data['group_id']
                except ValueError as e:
                    logging.error("Target Group must be a number.")
                    sys.exit(1)
                except AssertionError as e:
                    logging.error("Target Group must not be empty and correspond with a value in the list.")
                    sys.exit(1)
            elif total_namespaces == 1:
                group_id = namespace_response_data['namespaces'][0]['id']
        elif namespace_response.status_code == 401:
            logging.error(namespace_response_data['message'])
            sys.exit(1)
        
        registration_response = requests.post(DEVICE_REGISTRATION_API_ENDPOINT, data=data)
        registration_response_data = json.loads(registration_response.text)

        if registration_response.status_code == 201:
            config = configparser.ConfigParser()
            config['app.psygig.com'] = {
                                        'AppSecret': secret,
                                        'AppId': id,
                                        'BrokerSecret': registration_response_data['broker_app_secret'],
                                        'BrokerId': registration_response_data['broker_app_id'],
                                        'BrokerTcpUrl': registration_response_data['broker_tcp_url'],
                                        'ChannelId': registration_response_data['channel_id'],
                                        'Identifier': identifier,
                                        'GroupID': group_id}
            with open(self.angelo_conf, 'w+') as f:
                config.write(f)
            logging.info("Device registered.")
        elif registration_response.status_code == 400:
            logging.error(registration_response_data['message'])
        elif registration_response.status_code == 200:
            logging.error(registration_response_data['message'])
        elif registration_response.status_code == 401:
            logging.error(registration_response_data['message'])

    def up(self,
           service_names=None,
           start_deps=True,
           timeout=None,
           detached=False,
           remove_orphans=False,
           ignore_orphans=False,
           scale_override=None,
           rescale=True,
           start=True,
           always_recreate_deps=False,
           reset_container_image=False,
           renew_anonymous_volumes=False,
           silent=False,
           ):

        pid = os.fork()
        if pid == 0:
            if not self.mqtt_client.is_running():
                self.mqtt_client.start()
            return

        if service_names is None or len(service_names) == 0:
            if not self.supervisor.is_running():
                self.supervisor.run_supervisor()

            self.supervisor.start_process()
            return

        if not self.supervisor.is_running():
            raise OperationFailedError("Services must first be started with \'up\' or 'start'")

        services = self.get_services(
            service_names,
            include_deps=start_deps)

        for service in services:
            self.supervisor.start_process(service.name)

    def down(
            self,
            service_names=None,
            remove_orphans=False,
            timeout=None,
            ignore_orphans=False):

        if not self.supervisor.is_running():
            raise OperationFailedError("Services must first be started with \'up\' or 'start'")

        if service_names is None or len(service_names) == 0:
            self.supervisor.stop_process()
            return

        services = self.get_services(
            service_names)

        for service in services:
            self.supervisor.stop_process(service.name)

    def start(self,
           start_deps=True,
           timeout=None,
           detached=False,
           remove_orphans=False,
           ignore_orphans=False,
           scale_override=None,
           rescale=True,
           start=True,
           always_recreate_deps=False,
           reset_container_image=False,
           renew_anonymous_volumes=False,
           silent=False,
           ):

        pid = os.fork()
        if pid == 0:
            if not self.mqtt_client.is_running():
                # Anything after self.mqtt_client.start() will never be executed because parent processes are killed when
                # creating the daemon, daemon blocks the program, and killing the client ends the program.
                # Therefore, by running it in a child process, the supervisor is still able to run
                self.mqtt_client.start()
            return

        if not self.supervisor.is_running():
            # Starting the supervisor starts processes so self.supervisor.start_process() should not be run.
            self.supervisor.run_supervisor()

        if not self.supervisor.is_running():
            raise OperationFailedError("Services must first be started with \'up\' or 'start'")

        self.supervisor.start_process()

    def stop(self, timeout=None):
        if not self.supervisor.is_running() and not self.mqtt_client.is_running:
            raise OperationFailedError("Services must first be started with \'up\' or 'start'")

        try:
            os.kill(self.supervisor.get_pid(), SIGTERM)
            logging.debug('Supervisor shutting down...')
        except ProcessLookupError as e:
            logging.debug("No supervisor running. Removing pid file.")
            os.remove(self.supervisor.pid_file)
        except TypeError as e:
            logging.debug("No supervisor process id found. Already killed?")
            logging.error("This service may have already been stopped.")

        try:
            os.kill(self.mqtt_client.get_pid(), SIGTERM)
            logging.debug('MQTT Client shutting down...')
        except ProcessLookupError as e:
            logging.debug("No MQTT Client running. Removing pid file.")
            self.mqtt_client.delpid()
        except TypeError as e:
            logging.debug("No MQTT Client process id found. Already killed?")
            logging.error("This service may have already been stopped.")

    def reload(self):
        self.supervisor.reload_config()

    def restart(self, service_names=None, timeout=None):
        
        if not self.supervisor.is_running():
            raise OperationFailedError("Services must first be started with \'up\' or 'start'")

        if service_names is None or len(service_names) == 0:
            self.supervisor.restart_process()
            return

        services = self.get_services(
            service_names)

        for service in services:
            self.supervisor.restart_process(service.name)

    def kill(self, service_names=None, signal="SIGKILL"):

        if not self.supervisor.is_running():
            raise OperationFailedError("Services must first be started with \'up\' or 'start'")

        if signal is None:
            signal = "SIGKILL"
                
        if service_names is None or len(service_names) == 0:
            self.supervisor.signal_process("all", signal)
            return

        services = self.get_services(
            service_names)

        for service in services:
            self.supervisor.signal_process(service.name, signal)

    def top(self, service_names=None):
        
        if not self.supervisor.is_running():
            raise OperationFailedError("Services must first be started with \'up\' or 'start'")

        if service_names is None or len(service_names) == 0:
            self.supervisor.get_process_status()
            return

        services = self.get_services(
            service_names)

        for service in services:
            self.supervisor.get_process_status(service.name)

    def logs(self, 
             service_names=None,
             follow=False,
             tail=None):

        if not self.supervisor.is_running():
            raise OperationFailedError("Services must first be started with \'up\' or 'start'")

        if tail is None:
            tail = 1600

        services = self.get_services(
            service_names)

        for service in services:
            self.supervisor.logs(service.name, follow, tail)
            
    def live(self):
        from .webrtc import WebRTCClient
        self.mqtt_client.initialize_client()
        self.mqtt_client.publish_live('webrtc')
        our_id = self.mqtt_client.default_payload['identifier']
        server = 'wss://webrtc-signal-server-staging.app.psygig.com:443/'
        server = 'ws://localhost:8443'
        peerid = self.mqtt_client.channel_id

        c = WebRTCClient(our_id, peerid, server, 'webrtc.pid', self.angelo_conf)
        if c.is_running():
            logging.error("Webrtc client already running?")
            sys.exit(1)
        c.start()
        asyncio.get_event_loop().run_until_complete(c.connect())
        res = asyncio.get_event_loop().run_until_complete(c.loop())
        sys.exit(res)

    def offline(self):
        from .webrtc import WebRTCClient
        self.mqtt_client.initialize_client()
        our_id = random.randrange(10, 10000)
        peerid = self.mqtt_client.channel_id
        server = 'wss://webrtc-signal-server-staging.app.psygig.com:443/'
        server = 'ws://localhost:8443'
        c = WebRTCClient(our_id, peerid, server, 'webrtc.pid', self.angelo_conf)

        if not c.is_running():
            raise OperationFailedError("Video stream must first be started with \'live\'")

        try:
            os.kill(c.get_pid(), SIGTERM)
            self.mqtt_client.publish_live(None)
            c.stop()
            logging.debug("Stopping stream...")
        except ProcessLookupError as e:
            logging.debug("No webrtc client running. Removing pid file.")
            os.remove(c.pid_file)
        except TypeError as e:
            logging.debug("No webrtc client process id found. Already killed?")
            logging.error("This service may have already been stopped.")

class NoSuchService(Exception):
    def __init__(self, name):
        if isinstance(name, six.binary_type):
            name = name.decode('utf-8')
        self.name = name
        self.msg = "No such service: %s" % self.name

    def __str__(self):
        return self.msg
