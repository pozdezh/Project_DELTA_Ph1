#Import python files
import os
import sys
import datetime
import time
import sqlite3
import pandas as pd

#Import actua modules
import utils.config_manager as cfg
import utils.logger_manager as lm


# logging
filename = os.path.splitext(os.path.basename(__file__))[0]
logger = lm.setup_logger(filename)


# load configuration
cfg_data = cfg.load_db_configuration()
DB_NAME  = cfg_data['path']
cfg_raspi = cfg.get_raspberrypi_name()
IDRASPI = cfg_raspi


'''
Verify if database is created. If not, create it
Verify if all tables are created. If not, create them
'''
def check_db():
    STATUS = False
    conn, c = None, None
    
    try:
        conn = sqlite3.connect(DB_NAME)
        if conn is not None:
            c = conn.cursor()
            
            # table monicat_data
            c.execute('''SELECT COUNT(name) FROM sqlite_master WHERE type='table' AND name='delta_data' ''')
            if c.fetchone()[0]==1:
                pass
            else:
                c.execute('''CREATE TABLE delta_data(
                                id_sensor TEXT NOT NULL,
                                id_parameter TEXT NOT NULL,
                                value REAL NOT NULL,
                                created_at TEXT NOT NULL
                             )
                          ''')
                logger.info('Table delta_data created')
                
            STATUS = True
            
        else:
            logger.error('Cannot connect to the database')
            
    except Exception as err:
        logger.error('Cannot check health status: %s' % err.args[0])
        
    finally:
        if c:
            c.close()
        if conn:
            conn.close()
            
        return STATUS


'''
Write data from the sensors to table monicat:data
Parameter records needs to be an array
'''
def write_delta_data(records):
    conn, c = None, None
    
    try:
        conn = sqlite3.connect(DB_NAME)
        if conn is not None:
            c = conn.cursor()
            c.executemany('INSERT INTO delta_data(id_sensor,id_parameter,value,created_at) VALUES (?,?,?,?)', records)
            conn.commit()
            logger.info('%d rows inserted' % c.rowcount)
            
        else:
            logger.error('Cannot connect to the database')
            
    except Exception as err:
        logger.error('Cannot write to database: %s' % err.args[0])
        
    finally:
        if c:
            c.close()
        if conn:
            conn.close()
            
'''
Read last inserted instance of a TAG.
Returns the time elapset between then and now in minutes
Returns 555 minutes if there is no entries in the database.
'''
def last_insert(TAG):
    
    conn, c = None, None
    try:
        conn = sqlite3.connect(DB_NAME)
        if conn is not None:
            c = conn.cursor()
            sql_select_query = '''SELECT created_at FROM delta_data WHERE id_sensor=? ORDER BY created_at DESC LIMIT 1;'''
            c.execute(sql_select_query, (TAG,))
            res = c.fetchone()
            if res is not None:
                res = res[0]
                last_inserted_time = datetime.datetime.strptime(res, "%Y-%m-%d %H:%M:%S")
                now = datetime.datetime.now()
                minuts = now - last_inserted_time
                return minuts
                
            else:
                logger.warning('The records were exported recently. Sensors are working to generate more data.')
                minuts = datetime.timedelta(minutes=555) #Retorna això com a flag de que no ha trobat valors.
                return minuts
        else:
            logger.error('Cannot connect to the database')
            return None
            
    except Exception as err:
        logger.error('Cannot write to database: %s' % err.args[0])
        return None
        
    finally:
        if c:
            c.close()
        if conn:
            conn.close()
    
'''
Export all data from the database to a .csv file
'''
'''
def export_data(time):
    conn, c = None, None
    try:
        conn = sqlite3.connect(DB_NAME, isolation_level=None, detect_types=sqlite3.PARSE_COLNAMES)
        sql = "select * from monicat_data where created_at<=Datetime('"+time+"')"
        if conn is not None:
            c = conn.cursor()
            db_df = pd.read_sql_query(sql, conn)
            #custom name of the exported file
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            date_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            nom = "exports/"+date_time+"_"+IDRASPI+".csv"
            db_df.to_csv(nom, index=False)
            #insert into movements the time is inserted
            sql_insert_query = "insert into movements (action, date) values ('csv','"+now+"');"
            c.execute(sql_insert_query)
            conn.commit()
            logger.info('Data exported successfully to CSV')
            return True
        else:
            logger.error('Cannot connect to the database')
            return False
            
    except Exception as err:
        logger.error('Cannot export database to CSV: %s' % err.args[0])
        return False
    
    finally:
        if c:
            c.close()
        if conn:
            conn.close()
            
'''
    
'''
Delete all entries in the database. This function can only be used after exporting all entries in the expot_data() function
'''
def clean_database(time):
    
    conn, c = None, None
    try:
        conn = sqlite3.connect(DB_NAME)
        if conn is not None:
            c = conn.cursor()
            sql_delete_query = "delete from delta_data where created_at<=Datetime('"+time+"')"
            c.execute(sql_delete_query)
            conn.commit()
            logger.info('Records deleted successfully')
            return 
        else:
            logger.error('Cannot connect to the database')
            return None
            
    except Exception as err:
        logger.error('Cannot write to database: %s' % err.args[0])
        return None
    finally:
        if c:
            c.close()
        if conn:
            conn.close()

'''
Returns the string of the last instance recorded in the database
'''
def last_date_of_insert():
    
    conn, c = None, None
    try:
        conn = sqlite3.connect(DB_NAME)
        if conn is not None:
            c = conn.cursor()
            #sql_select_query = '''select created_at from monicat_data order by created_at desc limit 1;'''
            sql_select_query = '''select max(created_at) from delta_data'''
            c.execute(sql_select_query)
            last_inserted_time = c.fetchone()[0]
            #logger.info('Time ' + str(last_inserted_time) + ' successfully received')
            return last_inserted_time
        else:
            logger.error('Cannot connect to the database')
            return None
            
    except Exception as err:
        logger.error('Cannot write to database: %s' % err.args[0])
        return None
    
    finally:
        if c:
            c.close()
        if conn:
            conn.close()
    
'''
This function searches in the table movements for the last time inserted of the csv.
The function returns the last date in the database of the exported csv. If this is not disponible it returns the date of the creation of the kit.
'''
def last_generated_csv():
    conn, c = None, None
    try:
        conn = sqlite3.connect(DB_NAME)
        if conn is not None:
            c = conn.cursor()
            sql_select_query = '''select max(date) from movements '''
            c.execute(sql_select_query)
            last_generated_csv = c.fetchone()[0]
            return last_generated_csv
        else:
            logger.error('Cannot connect to the database')
            return None
            
    except Exception as err:
        logger.error('Cannot write to database: %s' % err.args[0])
        return None
    finally:
        if c:
            c.close()
        if conn:
            conn.close()
