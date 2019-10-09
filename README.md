# Angelo
Device Management with Instant Configurations and Alerts

Featuring:
- Instant & secured configurations of software processes and parameters
- Real-time monitoring of device health, including system resource metrics, logs, and events

## Install

Run the install script to install the required dependencies and packages to run angelo.
```
sudo apt install libglib2.0-dev libgirepository1.0-dev libcairo2-dev
sudo install.sh
```

Additional packages that may be required:
```
gir1.2-gstreamer-1.0
gir1.2-gst-plugins-base-1.0
gstreamer-tools
gstreamer1.0-tools
gstreamer1.0-doc
gstreamer1.0-x
libgstreamer1.0-0
libgstreamer1.0-dev
libgstreamer1.0-0-dbg
python-gst-1.0
python3-gst-1.0
```

## Run

```python
bin/angelo
```
## Commands

- **up** [service_name] - Starts service(s) based on the configuration file and connects to PSYGIG's platform if not already connected
- **down** [service_name] - Stops service(s) based on configuration file 
- **start** - Similar to up but only starts ALL services
- **stop** - Similar to down but stops ALL services and kills the connection to PSYGIG's platform
- **register** - Allows you to register the device on PSYGIG's platform (requires your application credentials)
- **reload** - Rereads the configuration file and restarts services based on the newly read configuration file
- **ps**/**top** - View status of services started by angelo
- **live** - Starts a low latency stream
- **offline** - Stops streaming (only for **live**)
- **broadcast** Starts a higher quality, but higher latency stream

## Issues
- The **live** command's experimental version will most likely fail to start the stream when there are 3 or more peers 
already connected.
- The peer that will view the stream on PSYGIG's platform must first be connected before starting the stream when running
the normal **live** command.
    - This requires you to run **live** twice. Once to notify the platform this device is ready and a second time to
    begin the stream.

## Executable

Generate binary executable with PyInstaller via:

```python
venv3/bin/pyinstaller --onefile --exclude-module pycrypto --exclude-module PyInstaller bin/angelo
```
or if angelo.spec is already generated:
```python
venv3/bin/pyinstaller --onefile --exclude-module PyInstaller angelo.spec
```
Run distributable with
```python
dist/angelo
```

