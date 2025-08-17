#Import python files
import os
import sys
import random
import time
from datetime import datetime
from scd30_i2c import SCD30
import threading
import socket
import json

#Import actua modules
currentdir = os.path.dirname(os.path.realpath(__file__))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)
from utils import database_manager as db, config_manager as cfg, logger_manager as lm


'''
Load configuration of the sensor
'''
try:
    sensor = os.path.splitext(os.path.basename(__file__))[0]
    cfg_data   = cfg.load_sensor_configuration(sensor)
    TAG        = cfg_data['tag']
    CONNECTION = int( cfg_data['connection'] )
    FREQUENCY  = int( cfg_data['frequency'] )
    ACTIVE     = int( cfg_data['active'] )
    PORT       = int( cfg_data['port'] )
    logger = lm.setup_logger(TAG)
    logger.info("DEVICE CONFIGURATION: Tag: %s , Connected to %s , Frequency: %d minutes , Active: %d " % (TAG,CONNECTION, FREQUENCY, ACTIVE ))
    
    scd30 = SCD30()
    scd30.set_temperature_offset(9.0) #compensating for heating
    scd30.set_measurement_interval(2)
    scd30.start_periodic_measurement()
except Exception as error:
    logger = lm.setup_logger(sensor)
    logger.error('Configuration error: %s' % error)
    sys.exit()


'''
Main program
'''
def run():
        
    time.sleep(random.randint(0,30))
       
    while (ACTIVE == 1):
        manage_iteration()
        time.sleep(60*FREQUENCY)
        
    sys.exit()

'''
Manage the data collection and writing to DB
'''
def manage_iteration():
    time.sleep(1.0)
    records = read_sensor_value()
    if records is not None:
        db.write_delta_data(records)


def read_sensor_value():
    try:
        if scd30.get_data_ready():
            m = scd30.read_measurement()
            if m is not None:
                #logger.info("CO2: "+str(m[0])+"ppm, temp: "+str(m[1])+"C, rh: "+str(m[2])+"%")
                co2 = m[0]
                air_temperature = m[1]
                air_humidity = m[2]
                co2_decimal = round(co2, 2)
                air_temperature_decimal = round(air_temperature, 2)
                air_humidity_decimal = round(air_humidity, 2)
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                return [
                            (TAG, 'TEMP', air_temperature_decimal, current_time),
                            (TAG, 'HUM', air_humidity_decimal, current_time),
                            (TAG, 'CO2', co2_decimal, current_time)
                        ]
       
    except Exception as error: 
        logger.error(error)
        
        
        
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
        #    ACTIVE = int(val)
        logger.info('Change parameter %s to %s' % (param, val))
        
        ## aixo ho fara el sensormanager, no sensor
        cfg.set_sensor_configuration(sensor, param, str(val))
        
    except Exception as error:
        logger.error('Cannot set parameter %s to %s: %s' % (param, val, error))

'''
Funció per escoltar les comandes que poden interactuar amb el sensor.
'''
def escoltarComandes():
    # Create a UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_address = ('localhost', PORT)
    logger.info('starting up on {} port {}'.format(*server_address))
    sock.bind(server_address)
    
    #Thread should always be listening for income commands
    while True:
        data, address = sock.recvfrom(4096) 
        logger.info('received {} bytes from {}'.format(len(data), address))
        comanda = json.loads(data.decode(encoding="utf-8"))
        actor, command, value  = str(comanda['actor']), str(comanda['command']), str(comanda['value'])
        if (actor==TAG):
            if (command == 'SET_FREQ'):
                set_parameter('FREQUENCY', str(comanda['value']))
                logger.info('FREQUENCY changed correctly:'+str(FREQUENCY))
        else:
            logger.warning('Aquesta comanda no es daquest sensor')
            
def main():
    fil = threading.Thread(target=escoltarComandes)
    fil.start()
    run()
    ## here open socket and create thread
    
if __name__ == '__main__':
    main()
