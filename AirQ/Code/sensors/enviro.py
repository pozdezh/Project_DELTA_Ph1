#Import python files
import os
import sys
import random
import time
from datetime import datetime
import threading
import socket
import json
from bme280 import BME280
from enviroplus import gas
from ltr559 import LTR559


try:
    from smbus2 import SMBus
except ImportError:
    from smbus import SMBus

#Import actua modules
currentdir = os.path.dirname(os.path.realpath(__file__))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)
from utils import database_manager as db, config_manager as cfg, logger_manager as lm

FACTOR_TEMP = -9.35 #Temp, Hum offsets
FACTOR_HUM = 33.4
	
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
    bus = SMBus(1)
    bme280 = BME280(i2c_dev=bus)
    ltr559 = LTR559()
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
    time.sleep(1.0)
    records = read_sensor_value()
    if records is not None:
        db.write_delta_data(records)

'''
Temperatura de la CPU per a fer la compensacio
'''
def get_cpu_temperature():
    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
        temp = f.read()
        temp = int(temp) / 1000.0
    return temp

'''
Implementation of the collection of sensing data using the specific libraries of the device
'''
def read_sensor_value():       
    try:
        factor = 2.25 #temp correction factor, DEcrease to adjust temp DOWN and vice versa

        cpu_temps = [get_cpu_temperature()]*5

        cpu_temp = get_cpu_temperature()
        
        # Smooth out with some averaging to decrease jitter
        cpu_temps = cpu_temps[1:] + [cpu_temp]
        avg_cpu_temp = sum(cpu_temps) / float(len(cpu_temps))

        raw_temp = bme280.get_temperature()

        comp_temp = raw_temp - ((avg_cpu_temp - raw_temp) / factor) + FACTOR_TEMP # REAL adjusted temperature

        pressure = bme280.get_pressure()
        
        raw_hum = bme280.get_humidity()
        
        humidity = raw_hum + FACTOR_HUM # REAL adjusted humidity
        
        #data_gas = gas.read_all()
        #oxidising = data_gas.oxidising
        #reducing = data_gas.reducing
        #nh3 = data_gas.nh3
        lux = ltr559.get_lux()
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        #logger.info('Temperature: %f ; Humidity: %f ' % (comp_temp, humidity))
        
        temp_decimals = round(comp_temp, 2) #again, REAL temperature adjusted
        hum_decimals = round(humidity, 2) #again, REAL humidity adjusted
        pres_decimals = round(pressure, 2)
        #no2_decimals = round(oxidising, 2)
        #co_decimals = round(reducing, 2)
        #nh3_decimals = round(nh3, 2)
        lux_decimals = round(lux, 2)
        

        
        return [
                    (TAG, 'TEMP', temp_decimals, current_time),
                    (TAG, 'HUM', hum_decimals, current_time),
                    (TAG, 'PRES', pres_decimals, current_time),
                    (TAG, 'LLUM', lux_decimals, current_time)
                ]
    
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





