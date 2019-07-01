"""Generic linux daemon base class for python 3.x."""

import sys, os, time, atexit, signal, base64, json
import paho.mqtt.client as mqtt
import errno

class daemon:
    """A generic daemon class.

    Usage: subclass the daemon class and override the run() method."""

    def __init__(self, pidfile):
        self.pidfile = pidfile

    def daemonize(self):
        """Deamonize class. UNIX double fork mechanism."""
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
        # atexit.register(self.delpid)
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


class MqttClient(daemon):
    """
    Subclass of daemon to run mqtt loop as a background process
    """

    def __init__(self, pidfile):
        super().__init__(pidfile)

    def run(self):
        print("Starting MQTT Client...")
        killer = GracefulKiller()
        client = mqtt.Client("test")
        client.username_pw_set("admin", "public")
        client.on_message = self.on_message
        client.connect("localhost", port=1883)
        client.loop_start()
        client.subscribe("config")
        client.publish("config", payload=self.create_config_payload(), qos=1)
        while not killer.kill_now:
            pass
        client.loop_stop()
        client.disconnect()
        self.stop()

    def on_message(self, client, userdata, message):
        response_payload = message.payload.decode("utf-8")
        if (response_payload):
            self.update_config_file(response_payload)


    def create_config_payload(self):
        with open("angelo.yml", 'r') as f:
            config = f.read()
            # decode bytes to string after encoding to b64
            encoded_config = base64.b64encode(config.encode('utf-8')).decode('utf-8')
            payload = {"context": encoded_config, "identifier": "test", "app_id": "", "app_secret": ""}
            string_payload = json.dumps(payload)
            return string_payload

    def update_config_file(self, context):
        data = json.loads(context)["context"]
        new_config = base64.b64decode(data).decode('utf-8')
        with open("angelo.yml", 'w+') as f:
            f.write(new_config)

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
                os.remove(self.pid)
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


class GracefulKiller:
    kill_now = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        self.kill_now = True

if __name__ == "__main__":
    MqttClient("mqtt.pid").start()
    print("stopping")