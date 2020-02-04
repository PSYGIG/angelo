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
import time

from .process import Process
from .supervisor import Supervisor
from .errors import OperationFailedError
from .mqtt import MqttClient

# TODO: Change to staging/production?
DEVICE_REGISTRATION_API_ENDPOINT = "https://staging.app.psygig.com/api/v1/device"
GROUP_SEARCH_ENDPOINT = "https://staging.app.psygig.com/api/v1/user/namespaces"
MARKETPLACE_API_ENDPOINT = "https://staging.app.psygig.com/api/v1/marketplace"

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
            
    def live(self, experimental=False):
        if experimental:
            from .webrtc_experimental import WebRTCClient
            method = 'webrtc-room'
        else:
            from .webrtc import WebRTCClient
            method = 'webrtc'
        self.mqtt_client.initialize_client()
        self.mqtt_client.publish_live(method)
        our_id = "{}:{}".format(self.mqtt_client.default_payload['group_id'], self.mqtt_client.default_payload['identifier'])
        server = 'wss://webrtc-signal-server-staging.app.psygig.com:443/'
        # server = 'ws://localhost:8443'
        room_id = self.mqtt_client.channel_id

        c = WebRTCClient(our_id, room_id, server, 'webrtc.pid', self.angelo_conf)
        if c.is_running():
            logging.error("Webrtc client already running?")
            sys.exit(1)
        c.start()
        asyncio.get_event_loop().run_until_complete(c.connect())
        res = asyncio.get_event_loop().run_until_complete(c.loop())
        sys.exit(res)

    def offline(self):
        from .webrtc_experimental import WebRTCClient
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
            os.remove(c.pidfile)
        except TypeError as e:
            logging.debug("No webrtc client process id found. Already killed?")
            logging.error("This service may have already been stopped.")

    def install(self, module_name, remote=False, version=None):
        from shutil import copyfile
        try:
            module_folder_path = os.path.expanduser("~") + "/.angelo/modules"
            os.makedirs(module_folder_path, exist_ok=True) # caution: only for python >= 3.2
            if remote:
                response = requests.get(MARKETPLACE_API_ENDPOINT, params={'name': module_name, 'version': version})
                if response.status_code == 404:
                    logging.error(json.loads(response.text)['error'])
                    raise FileNotFoundError
                os.makedirs(module_folder_path + "/{}".format(os.path.dirname(module_name)), exist_ok=True) # caution: only for python >= 3.2
                module_file_path = module_folder_path + "/{}.py".format(module_name)
                with open(module_file_path, 'w+') as m:
                    m.write(response.text)
            else:
                abs_module_path = os.path.abspath(module_name)
                # create a ~/.angelo/modules folder if not have
                module_file_name = os.path.basename(abs_module_path)
                module_file_path = "{}/{}".format(module_folder_path, module_file_name)
                # cp the file inside the module (append mode)
                copyfile(abs_module_path, module_file_path)
                # install the dependency if there are dependencies
            module = self.get_module(module_file_path)

            # preinstall hook
            preinstall_hook = getattr(module, '__hook_preinstall', None)
            if (not (preinstall_hook is None)):
                preinstall_hook()

            import sys
            import subprocess
            base_cmd = [sys.executable, '-m', 'pip', 'install']
            module_requirements = getattr(module, '__requirements', [])

            if (len(module_requirements) > 0):
                print("Installing module dependencies")
                subprocess.check_call(base_cmd + module_requirements)
                print("Module dependencies are installed")
                
            # postinstall hook
            postinstall_hook = getattr(module, '__hook_postinstall', None)
            if (not (postinstall_hook is None)):
                postinstall_hook()

            print("Module installed")

        except OSError as e:
            print("Creation of the directory %s failed" % module_folder_path)
            raise e

        except Exception as e:
            print(e)

    def run(self, module_id):
        # check if module is being registered
        from .pipeline import run
        module_folder_path = os.path.expanduser("~") + "/.angelo/modules"
        module_path = "{}/{}.py".format(module_folder_path, module_id)
        try:
            module = self.get_module(module_path)
            run(module)
        except Exception as e:
            print(e) 

    def get_module(self, path):
        import importlib.util
        if os.path.exists(path):
            # dynamically load the module from the registry
            spec = importlib.util.spec_from_file_location("module.name", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        else:
            raise Exception("Module is not yet registered")

    def publish(self, module_name, org=False):
        cwd = os.getcwd()
        module_path = "{}/{}.py".format(cwd, module_name)
        self.mqtt_client.initialize_client()
        if os.path.exists(module_path):
            with open(module_path, 'rb') as m:
                module = self.get_module(module_path)
                try:
                    version = getattr(module, 'VERSION')
                except AttributeError:
                    logging.error("VERSION attribute required in module")
                    return
                tags = getattr(module, 'TAGS', 'None')
                description = getattr(module, 'DESCRIPTION', 'None')
                data = {'app_id': self.mqtt_client.default_payload['app_id'],
                        'app_secret': self.mqtt_client.default_payload['app_secret'],
                        'version': version,
                        'tags': tags,
                        'description': description}
                files = {'module': m}
                if org:
                    data['group_id'] = self.mqtt_client.default_payload['group_id']
                response = requests.post(MARKETPLACE_API_ENDPOINT + "/publish", data=data, files=files)
                response_data = json.loads(response.text)
                if response.status_code == 201:
                    logging.info(response_data)
                else:
                    logging.error(response_data['error'])
        else:
            print("Could not find module in current directory")

    def track(self):
        self.mqtt_client.initialize_client()

        import gps

        gpsd = gps.gps(mode=gps.WATCH_ENABLE|gps.WATCH_NEWSTYLE)

        while True:
            report = gpsd.next()
            if report['class'] == 'TPV':
                payload = {
                    'timestamp' : getattr(report,'time',''),
                    'latitude' : getattr(report,'lat',0.0),
                    'longitude' : getattr(report,'lon',0.0)
                }
                logging.debug(json.dumps(payload))
                self.mqtt_client.publish_metrics(payload)
                time.sleep(1)
        
class NoSuchService(Exception):
    def __init__(self, name):
        if isinstance(name, six.binary_type):
            name = name.decode('utf-8')
        self.name = name
        self.msg = "No such service: %s" % self.name

    def __str__(self):
        return self.msg
