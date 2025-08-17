
#Import python files
import os
import sys
import random
import time
from datetime import datetime

import threading
import socket
import json
import numpy as np
from pms5003 import PMS5003, ReadTimeoutError



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
    # logging   (el nom que li passarem al logger sera el TAG, no el nom de fitxer)
    logger = lm.setup_logger(TAG)
    logger.info("DEVICE CONFIGURATION: Tag: %s , Connected to %s , Frequency: %d minutes , Active: %d " % (TAG,CONNECTION, FREQUENCY, ACTIVE ))
    
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
    records = read_sensor_value()
    if records is not None:
        db.write_delta_data(records)

'''
Implementation of the collection of sensing data using the specific libraries of the device
'''
def read_sensor_value():       
    try:
        time.sleep(1.0)
        pm1 = 0
        pm25 = 0
        pm10 = 0
        um03 = 0
        um05 = 0
        um1 = 0
        um25 = 0
        um5 = 0
        um10 = 0

        dadespm1 = np.array([])
        dadespm25 = np.array([])
        dadespm10 = np.array([])
        dades03 = np.array([])
        dades05 = np.array([])
        dades1 = np.array([])
        dades25 = np.array([])
        dades5 = np.array([])
        dades10 = np.array([])


        contador=True
        temps = 40
        try:
            pms5003 = PMS5003()
            inici = time.time()
            while (contador):
                try:
                    readings = pms5003.read()
                    
                    #Manipulació de matrius
                    dadespm1 = np.append(dadespm1, readings.pm_ug_per_m3(1.0))
                    dadespm25 = np.append(dadespm25, readings.pm_ug_per_m3(2.5))
                    dadespm10 = np.append(dadespm10, readings.pm_ug_per_m3(10))
                    dades03 = np.append(dades03, readings.pm_per_1l_air(0.3))
                    dades05 = np.append(dades05, readings.pm_per_1l_air(0.5))
                    dades1 = np.append(dades1, readings.pm_per_1l_air(1.0))
                    dades25 = np.append(dades25, readings.pm_per_1l_air(2.5))
                    dades5 = np.append(dades5, readings.pm_per_1l_air(5))
                    dades10 = np.append(dades10, readings.pm_per_1l_air(10))

                    #We need to test the time
                    fi = time.time()
                    if ((fi-inici)>temps):
                        contador = False
                except ReadTimeoutError:
                    pms5003 = PMS5003()
                                
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            #logger.info('Temperature: %f ; Humidity: %f ' % (temperature, humidity))
            pm1_send = round(np.mean(dadespm1), 2)
            pm25_send = round(np.mean(dadespm25), 2)
            pm10_send = round(np.mean(dadespm10), 2)
            um03_send = round(np.mean(dades03), 2)
            um05_send = round(np.mean(dades05), 2)
            um1_send = round(np.mean(dades1), 2)
            um25_send = round(np.mean(dades25), 2)
            um5_send = round(np.mean(dades5), 2)
            um10_send = round(np.mean(dades10), 2)
            return [
                        (TAG, 'PM1', pm1_send, current_time),
                        (TAG, 'PM25', pm25_send, current_time),
                        (TAG, 'PM10', pm10_send, current_time),
                        (TAG, 'UM03', um03_send, current_time),
                        (TAG, 'UM05', um05_send, current_time),
                        (TAG, 'UM1', um1_send, current_time),
                        (TAG, 'UM25', um25_send, current_time),
                        (TAG, 'UM5', um5_send, current_time),
                        (TAG, 'UM10', um10_send, current_time)
                    ]
                

        except KeyboardInterrupt:
            pass
        

    
    except RuntimeError as error:
        logger.warning('RuntimeError: %s ' % error)
        time.sleep(2.0)
        
    except Exception as error:
        logger.error('Cannot read sensor value: %s' % error)
    
 

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
    if (ACTIVE == 0):
       sys.exit()
    else:
        fil = threading.Thread(target=escoltarComandes)
        fil.start()
        run()
    
if __name__ == '__main__':
    main()



