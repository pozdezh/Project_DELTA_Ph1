# Import python files
import os
import sys
import random
import time
from datetime import datetime
import adafruit_dht
import board
import threading
import socket
import json



# Import actual modules
currentdir = os.path.dirname(os.path.realpath(__file__))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)
from utils import database_manager as db, config_manager as cfg, logger_manager as lm

'''
Load configuration of the sensor
'''
try:
    sensor = os.path.splitext(os.path.basename(__file__))[0]
    cfg_data = cfg.load_sensor_configuration(sensor)
    TAG = cfg_data['tag']
    CONNECTION = int(cfg_data['connection'])  # GPIO pin from sensors.ini
    FREQUENCY = int(cfg_data['frequency'])
    ACTIVE = int(cfg_data['active'])
    PORT = int(cfg_data['port'])
    
    TEMP_OFFSET = -11.05  # Constant temperature offset
    HUM_OFFSET = 29.1 # Constant humidity offset
    
    logger = lm.setup_logger(TAG)
    logger.info("DEVICE CONFIGURATION: Tag: %s , Connected to GPIO %s , Frequency: %d minutes , Active: %d " % (TAG, CONNECTION, FREQUENCY, ACTIVE))

    # Initialize DHT22 sensor
    dht_sensor = adafruit_dht.DHT22(board.D4)

except Exception as error:
    logger = lm.setup_logger(sensor)
    logger.error('Configuration error: %s' % error)
    sys.exit()

'''
Main program
'''
def run():
    time.sleep(random.randint(0, 30))

    while (ACTIVE == 1):
        manage_iteration()
        time.sleep(60 * FREQUENCY)

    sys.exit()

'''
Manage the data collection and writing to DB
'''
def manage_iteration():
    time.sleep(1.0)
    records = read_sensor_value()
    if records is not None:
        db.write_delta_data(records)

'''
Read sensor values from DHT22 and apply temperature offset
'''
def read_sensor_value():
    try:
        temperature = dht_sensor.temperature
        humidity = dht_sensor.humidity
        

        
        
        if humidity is not None and temperature is not None:
            
            # Apply temperature offset
            adjusted_temperature = temperature + TEMP_OFFSET
            
            # Apply humidity offset
            adjusted_humidity = humidity + HUM_OFFSET
            
            logger.info("Raw Temperature: %0.1f C, Adjusted Temperature: %0.1f C, Humidity: %0.1f %%" % 
                       (temperature, adjusted_temperature, adjusted_humidity))
            
            temperature_decimal = round(adjusted_temperature, 2)
            humidity_decimal = round(adjusted_humidity, 2)
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return [
                (TAG, 'TEMP', temperature_decimal, current_time),
                (TAG, 'HUM', humidity_decimal, current_time)
            ]
        else:
            logger.warning('Failed to get reading from DHT22. Trying again...')
            return None

    except Exception as error:
        logger.error('Cannot read sensor value: %s' % error)
        return None

'''
Set the configuration values upon request
'''
def set_parameter(param, val):
    try:
        if (param == 'FREQUENCY'):
            global FREQUENCY
            FREQUENCY = int(val)
        elif (param == 'ACTIVE'):
            global ACTIVE
            ACTIVE = int(val)
        logger.info('Change parameter %s to %s' % (param, val))

        # This will be done by the sensormanager, not the sensor
        cfg.set_sensor_configuration(sensor, param, str(val))

    except Exception as error:
        logger.error('Cannot set parameter %s to %s: %s' % (param, val, error))

'''
Function to listen for commands that can interact with the sensor.
'''
def escoltarComandes():
    # Create a UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = ('localhost', PORT)
    logger.info('starting up on {} port {}'.format(*server_address))
    sock.bind(server_address)

    # Thread should always be listening for incoming commands
    while True:
        data, address = sock.recvfrom(4096)
        logger.info('received {} bytes from {}'.format(len(data), address))
        comanda = json.loads(data.decode(encoding="utf-8"))
        actor, command, value = str(comanda['actor']), str(comanda['command']), str(comanda['value'])
        if (actor == TAG):
            if (command == 'SET_FREQ'):
                set_parameter('FREQUENCY', str(comanda['value']))
                logger.info('FREQUENCY changed correctly:' + str(FREQUENCY))
        else:
            logger.warning('Aquesta comanda no es daquest sensor')

def main():
    fil = threading.Thread(target=escoltarComandes)
    fil.start()
    run()

if __name__ == '__main__':
    main()
