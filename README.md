# Angelo
Device Management with Instant Configurations and Alerts

Featuring:
- Instant & secured configurations of software processes and parameters
- Real-time monitoring of device health, including system resource metrics, logs, and events

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

