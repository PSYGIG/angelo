from __future__ import absolute_import
from __future__ import unicode_literals

import os, base64, configparser, yaml

class UserConfig:

    def __init__(self):
        conf_path = 'angelo.yml'
        self.config = self.__read_conf(conf_path)

    def __read_conf(self, conf_path):
        with open(conf_path, 'r') as f:
            config = f.read()
            encoded_config = yaml.safe_load(config.encode('utf-8'))
            return encoded_config 

class SystemConfig:

    def __init__(self):
        # TODO: check the flag indicating the current context
        self.context = 'app.psygig.com'
        conf_path = os.path.expanduser("~") + "/.angelo/angelo.conf" 
        self.config = self.__read_conf(conf_path)

    def switch(self, context):
        """
        Switch context of conf file (future feature)
        Add a flag to indicate the current context
        """
        return

    def __read_conf(self, conf_path):

        config = configparser.ConfigParser()
        config.read(conf_path)
        
        if self.context not in config.sections():
            raise RuntimeError('Unable to find the context {} inside angelo config'.format(self.context))
        elif config.options(self.context) == []:
            raise RuntimeError('Your device is not registered.')

        return config[self.context]