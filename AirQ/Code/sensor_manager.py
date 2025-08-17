#Import python files
import os
import time
import datetime
import socket

#Import actua modules
import utils.config_manager as cfg
import utils.database_manager as db
import utils.process_manager as pm
#import utils.export_manager as em
import utils.logger_manager as lm
#import utils.command_control_manager as ccm

# logging
filename = os.path.splitext(os.path.basename(__file__))[0]
logger = lm.setup_logger(filename)

# load configuration
cfg_sm_data = cfg.load_sensor_manager_configuration()
FREQUENCY = int( cfg_sm_data['frequency'] )
EXPORT_TIME =  datetime.timedelta(minutes=int(cfg_sm_data['export_time']))

'''
Principal function of the sensor manager
'''
def run():
    logger.info('Starting Sensor Manager...')
    while True:
        # check database
        STATUS_DB = 'OK' if db.check_db() else 'ERROR'
        logger.info("Database status: " + STATUS_DB)
        # check status of all sensors
        list_sensors = cfg.load_llista_sensors()
        for s in list_sensors:
            is_active = pm.is_process_active(s)
            logger.info("Sensor %s is active: %s " % (s, is_active))
            if not is_active:        
                pm.kill_process(s)

        # wait until next iteration
        time.sleep(60*FREQUENCY)

        
def main():
    run()
   
    
if __name__ == '__main__':
    main()
