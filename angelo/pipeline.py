from .event import Event
from .configuration import UserConfig

def run(module, base_url):

  # ---------------- pipeline ---------------------
  main_process = getattr(module, '__main', None)
  event = Event(base_url)
  user_config = UserConfig()

  if (not (main_process is None)):
    main_process(event, user_config.config)
