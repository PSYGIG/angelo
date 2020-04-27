# sample-module

# angelo install sample-module.py # install the module
# angelo run sample-module        # run the module

# dependencies that will be installed through pip
# format would be the same as the usage of requirements.txt
__requirements = [
  'websockets==8.0.2'
]

# hook for preinstall
def __hook_preinstall():
  print("preinstall hook")

# hook for postinstall
def __hook_postinstall():
  print("postinstall hook")

# __handle_frame with dependency injection from angelo pipeline
# using event.dispatch to dispatch user defined event
def __handle_frame(frame, event):
  print(frame)