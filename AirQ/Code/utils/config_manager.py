#Import python files
import os
import sys
from configparser import ConfigParser

#IMPORTANT: Do not remove this lines or actua modules will not be imported
currentdir = os.path.dirname(os.path.realpath(__file__))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

# path to configuration files
CONFIG_SENSORS = 'config/sensors.ini'
CONFIG_GLOBAL  = 'config/global.ini'


'''
Return all the configuration data of a given sensor
'''
def load_sensor_configuration(sensor):
    parser = ConfigParser()
    parser.read(CONFIG_SENSORS)
    return dict(parser.items(sensor))

def load_urls():
    parser = ConfigParser()
    parser.read(CONFIG_GLOBAL)
    return dict(parser.items('urls'))
'''
Return all the configuration data of the database
'''
def load_db_configuration():
    parser = ConfigParser()
    parser.read(CONFIG_GLOBAL)
    return dict(parser.items('db'))

'''
Return all the configuration necessary for the sensor manager
'''
def load_sensor_manager_configuration():
    parser = ConfigParser()
    parser.read(CONFIG_GLOBAL)
    return dict(parser.items('sensor_manager'))

'''
Return the list of available sensors
'''
def load_llista_sensors():
    parser = ConfigParser()
    parser.read(CONFIG_SENSORS)
    return parser.sections()


'''
Return all the configuration necessary of the RPI4.
'''
def get_raspberrypi_name():
    parser = ConfigParser()
    parser.read(CONFIG_GLOBAL)
    var = dict(parser.items('sensor_manager'))
    return var['name']

'''
Returns a dictionary with all the configuration necessary for the logs system
'''
def load_logger_configuration():
    parser = ConfigParser()
    parser.read(CONFIG_GLOBAL)
    return dict(parser.items('logs'))

'''
Return all the configuration necessary for the ftp connection
'''
def load_ftp_configuration():
    parser = ConfigParser()
    parser.read(CONFIG_GLOBAL)
    return dict(parser.items('ftp'))

'''
Sets the state of a sensor
'''
def set_sensor_state(sensor, state):
    parser = ConfigParser()
    parser.read(CONFIG_GLOBAL)
    
    if (parser.has_section('llista_sensors')):
        if (parser.has_option('llista_sensors', sensor)):
            parser.set('llista_sensors', sensor, state)
            with open(CONFIG_GLOBAL, 'w') as configfile:
                parser.write(configfile)   

'''
Modify the configuration data of a given sensor
param sensor, parameter, value must be string 
'''
def set_sensor_configuration(sensor, parameter, value):
    parser = ConfigParser()
    parser.read(CONFIG_SENSORS)
    
    if (parser.has_section(sensor)):
        if (parser.has_option(sensor, parameter)):
            parser.set(sensor, parameter, value)
            with open(CONFIG_SENSORS, 'w') as configfile:
                parser.write(configfile)

'''
Return the comunication PORT of a given TAG
'''
def get_communication_port(TAG):
    parser = ConfigParser()
    parser.read(CONFIG_SENSORS)
    for key in parser.sections():
        trobar= dict(parser.items(key))
        if (str(trobar['tag'])==TAG):
            return trobar['port']
    return 555

'''
Return the name of the sensor of a given TAG
'''
def get_sensor_name(TAG):
    parser = ConfigParser()
    parser.read(CONFIG_SENSORS)
    for key in parser.sections():
        trobar= dict(parser.items(key))
        if (str(trobar['tag'])==TAG):
            return key
    return ('not_found')