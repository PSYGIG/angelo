"""Generic linux daemon base class for python 3.x."""

import sys, os, time, signal, base64, json, configparser, socket
import paho.mqtt.client as mqtt
import errno
import logging
import schedule

class daemon:
    """A generic daemon class.

    Usage: subclass the daemon class and override the run() method."""

    def __init__(self, pidfile, conf):
        self.pidfile = pidfile
        self.conf = conf

    def daemonize(self):
        """Deamonize class. UNIX double fork mechanism."""
        if not os.path.exists(self.conf):
            logging.error("Check that this device is registered and/or ~/.angelo/angelo.conf exists with the correct information.")
            sys.exit(1)

        try:
            pid = os.fork()
            if pid > 0:
                # exit first parent
                sys.exit(0)
        except OSError as err:
            sys.stderr.write('fork #1 failed: {0}\n'.format(err))
            sys.exit(1)

        # decouple from parent environment
        os.setsid()
        os.umask(0)

        # do second fork
        try:
            pid = os.fork()
            if pid > 0:
                # exit from second parent
                sys.exit(0)
        except OSError as err:
            sys.stderr.write('fork #2 failed: {0}\n'.format(err))
            sys.exit(1)
        # redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        si = open(os.devnull, 'r')
        so = open(os.devnull, 'a+')
        se = open(os.devnull, 'a+')
        # os.dup2(si.fileno(), sys.stdin.fileno())
        # os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())
        # write pidfile
        pid = str(os.getpid())
        with open(self.pidfile, 'w+') as f:
            f.write(pid + '\n')

    def delpid(self):
        os.remove(self.pidfile)

    def start(self):
        """Start the daemon."""

        # Check for a pidfile to see if the daemon already runs
        try:
            with open(self.pidfile, 'r') as pf:
                pid = int(pf.read().strip())
        except IOError:
            pid = None

        if pid:
            message = "pidfile {0} already exist. " + \
                      "Daemon already running?\n"
            sys.stderr.write(message.format(self.pidfile))
            sys.exit(1)

        # Start the daemon
        self.daemonize()
        self.run()

    def stop(self):
        """Stop the daemon."""

        # Get the pid from the pidfile
        try:
            with open(self.pidfile, 'r') as pf:
                pid = int(pf.read().strip())
        except IOError:
            pid = None

        if not pid:
            message = "pidfile {0} does not exist. " + \
                      "Daemon not running?\n"
            sys.stderr.write(message.format(self.pidfile))
            return  # not an error in a restart

        # Try killing the daemon process
        try:
            self.delpid()
            while 1:
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.1)
        except OSError as err:
            e = str(err.args)
            if e.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
            else:
                print(str(err.args))
                sys.exit(1)

    def restart(self):
        """Restart the daemon."""
        self.stop()
        self.start()

    def run(self):
        """You should override this method when you subclass Daemon.

        It will be called after the process has been daemonized by
        start() or restart()."""

    def is_running(self):
        pid = self.get_pid()
        if pid is None:
            return False
        # The PID file may still exist even if the daemon isn't running,
        # for example if it has crashed.
        try:
            os.kill(pid, 0)
        except OSError as e:
            if e.errno == errno.ESRCH:
                # In this case the PID file shouldn't have existed in
                # the first place, so we remove it
                os.remove(self.pidfile)
                return False
            # We may also get an exception if we're not allowed to use
            # kill on the process, but that means that the process does
            # exist, which is all we care about here.
        return True

    def get_pid(self):
        try:
            with open(self.pidfile, 'r') as f:
                s = f.read().strip()
                if not s:
                    return None
                return int(s)
        except IOError as e:
            if e.errno == errno.ENOENT:
                return None
            raise

class MqttClient(daemon):
    """
    Subclass of daemon to run mqtt loop as a background process
    """

    def __init__(self, pidfile, conf):
        super().__init__(pidfile, conf)

    def initialize_client(self):
        conf_settings = self.read_conf()
        self.default_payload = {'identifier': conf_settings['identifier'],
                                'app_id': conf_settings['appid'],
                                'app_secret': conf_settings['appsecret'],
                                'source': socket.gethostbyname(socket.gethostname()),
                                'group_id': conf_settings['groupid']}
        self.client = mqtt.Client(self.default_payload['identifier'])
        self.channel_id = conf_settings['channelid']
        broker_host, broker_port = conf_settings['brokertcpurl'].split(':')
        if 'brokerid' in conf_settings and 'brokersecret' in conf_settings:
            self.client.username_pw_set(conf_settings['brokerid'], conf_settings['brokersecret'])
        self.client.on_message = self.on_message
        self.client.connect(broker_host, port=int(broker_port))

    def run(self):
        try:
            logging.debug("Starting MQTT Client...")
            self.initialize_client()
            config_channel = '{}/config'.format(self.channel_id)
            config_sync_channel = '{}/sync'.format(self.channel_id)
            self.client.loop_start()
            self.client.subscribe([(config_channel, 1), (config_sync_channel, 1)])
            killer = GracefulKiller()
            self.publish_presence('connected')
            self.sync_config(config_channel)
            schedule.every(5).seconds.do(self.publish_presence, status='connected')
            while not killer.kill_now:
                schedule.run_pending()
                time.sleep(1)
                pass
            schedule.clear()
            self.publish_presence('disconnected')
            self.client.loop_stop()
            self.client.disconnect()
            self.stop()
        except Exception as e:
            print(e)

    def publish_presence(self, status):
        presence_channel = '{}/presence'.format(self.channel_id)
        presence_payload = self.default_payload.copy()
        presence_payload['status'] = status
        self.client.publish(presence_channel, payload=json.dumps(presence_payload), qos=1)

    def sync_config(self, channel):
        config_payload = self.default_payload.copy()
        config_payload['context'] = self.get_encoded_config()
        self.client.publish(channel, payload=json.dumps(config_payload), qos=1)

    def publish_live(self, method):
        live_channel = '{}/live'.format(self.channel_id)
        live_payload = self.default_payload.copy()
        live_payload['live'] = method
        self.client.publish(live_channel, payload=json.dumps(live_payload), qos=2)

    def publish_event(self, data, type):
        event_channel = '{}/events'.format(self.channel_id)
        event_payload = self.default_payload.copy()
        event_payload['event_data'] = data
        event_payload['type'] = type
        self.client.publish(event_channel, payload=json.dumps(event_payload))

    def publish_metrics(self, data):
        metrics_channel = '{}/metrics'.format(self.channel_id)
        metrics_payload = self.default_payload.copy()
        metrics_payload['payload'] = data
        self.client.publish(metrics_channel, payload=json.dumps(metrics_payload))

    def read_conf(self):
        config = configparser.ConfigParser()
        config.read(self.conf)
        if 'app.psygig.com' not in config.sections():
            logging.error("MQTT Client was not started for the following reasons:")
            logging.error(" - Could not find the correct configs under 'app.psygig.com' the MQTT client.")
            logging.error("\nCheck that this device is registered and/or ~/.angelo/angelo.conf exists with the correct information.")
            try:
                self.delpid()
            except:
                pass
            sys.exit(1)
        elif config.options('app.psygig.com') == []:
            logging.error("MQTT Client was not started for the following reasons:")
            logging.error(" - No configs found inside ~/.angelo/angelo.conf.")
            logging.error("\nCheck that this device is registered and/or ~/.angelo/angelo.conf exists with the correct information.")
            try:
                self.delpid()
            except:
                pass
            sys.exit(1)
        return config['app.psygig.com']

    def on_message(self, client, userdata, message):
        """
        Handle publish response from MQTT broker by overwriting
        the current config file (angelo.yml) if the message source
        is not from the device.
        """
        response_payload = message.payload.decode('utf-8')
        context = json.loads(response_payload)
        if message.topic == "{}/sync".format(self.channel_id):
            self.sync_config("{}/config".format(self.channel_id))
        elif message.topic == "{}/config".format(self.channel_id):
            if response_payload and context['source'] != socket.gethostbyname(socket.gethostname()):
                self.update_config_file(response_payload)
                self.sync_config(message.topic)

    def get_encoded_config(self):
        with open('angelo.yml', 'r') as f:
            config = f.read()
            # decode bytes to string after encoding to b64
            encoded_config = base64.b64encode(config.encode('utf-8')).decode('utf-8')
            return encoded_config

    def update_config_file(self, context):
        data = json.loads(context)['context']
        new_config = base64.b64decode(data).decode('utf-8')
        with open('angelo.yml', 'w+') as f:
            f.write(new_config)



class GracefulKiller:
    kill_now = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        self.kill_now = True
