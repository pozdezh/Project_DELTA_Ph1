#Import python files
import os
import sys
import socket
import json
import requests

#Import ACTUA modules
import utils.process_manager as pm
import utils.export_manager as em
import utils.logger_manager as lm
import utils.config_manager as cfg

# logging
filename = os.path.splitext(os.path.basename(__file__))[0]
logger = lm.setup_logger(filename)

'''
Funció per fer una crida http i rebre les comandes
'''
def do_http_call():
    try:
        urls = cfg.load_urls()
        payload = {'kit': cfg.get_raspberrypi_name()}
        response = requests.get(urls['commands'], params=payload)
        json = response.json()
        if (json['result']==1):
            manageCommand(json)
        else:
            logger.info('There is no response to be managed')
    except Exception as error:
        logger.info('Unable to acces API with error: ' + str(error))
        
'''
Funció per gestionar les comandes rebudes del servidor
'''
def manageCommand(data):
    actor = data['actor']
    command = data['command']
    value = data['value']
    sensor = cfg.get_sensor_name(actor)
    if (actor == None):
         logger.info('Sense comanda per executar.')
    else: 
        if (actor =='SYSTEM'):  
            if (command == 'reiniciar'):
                llista = cfg.load_llista_sensors()
                for s in llista:
                    pm.kill_process(s)
                    
            elif (command == 'exportar'):
                em.export()
            logger.info('Received command for the SYSTEM: ' + command)
            
        else:
            #Send data to the sensor 
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            PORT = cfg.get_communication_port(actor)
            logger.info('sending on port: '+str(PORT))
            server_address = ('localhost', int(PORT))
            try:
                send = json.dumps(data)
                missatge = bytes(send, encoding="utf-8")
                sent = sock.sendto(missatge, server_address)
                logger.info('sending {!r}'.format(data))
                if (command == 'SET_FREQ'): 
                    cfg.set_sensor_configuration(sensor, "frequency", str(value))
                elif (command == 'ON_OFF'):
                    cfg.set_sensor_configuration(sensor, "active", str(value))
                    if (value == 0):
                        pm.kill_process(sensor)
                    
            except Exception as error:
                logger.error('Error while sending command to the sensor: ' + error)
            finally:
                sock.close()
