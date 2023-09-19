import paho.mqtt.client as mqtt
import datetime as dt
import json
import sqlite3
import logging
import signal
import sys
import sched, time
# https://github.com/dschuurman/pi-home

BROKER_PORT = 1883
BROKER_IP = "127.0.0.1"
MQTT_KEEPALIVE = 60
QOS = 0
SENSOR = "SNZB02_1"
DATABASE = "pi-home.db"
LOG_LEVEL = "DEBUG"
LOG_FILE = "pi-home.log"



# Start logging and set logging level; default to INFO level
if LOG_LEVEL == 'error':
    logging.basicConfig(filename=LOG_FILE, level=logging.ERROR, filemode='w')
elif LOG_LEVEL == 'debug':
    logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG, filemode='w')
else:
    logging.basicConfig(filename=LOG_FILE, level=logging.INFO, filemode='w')

# Start log file
logging.info(f'Starting at {dt.datetime.now()} with loglevel={LOG_LEVEL}')


db = sqlite3.connect(DATABASE)
db.execute('CREATE TABLE IF NOT EXISTS SENSORS (name TEXT NOT NULL, timestamp TEXT NOT NULL, temperature REAL, humidity REAL, linkquality INTEGER, battery REAL)')
cursor = db.cursor()


def sigint_handler(signum, frame):
    ''' SIGINT handler - exit gracefully '''
    logging.info(f'Program recevied SIGINT at: {dt.datetime.now()}')
    logging.shutdown()
    db.close()
    sys.exit(0)


# setup a sigint handler to exit gracefully on signal
signal.signal(signal.SIGINT, sigint_handler)



def on_message(client, userdata, message):
    timestamp = str(dt.datetime.now().isoformat())
    sensor_name = message.topic.split('/')[1]   # Extract sensor "friendly name" from MQTT topic
    msg = str(message.payload.decode("utf-8"))
    status = json.loads(msg) # Parse JSON message from sensor into a dictionary
    temperature = status["temperature"] if "temperature" in status.keys() else None
    humidity = status["humidity"] if "humidity" in status.keys() else None
    linkquality = status["linkquality"] if "linkquality" in status.keys() else None
    battery = status["battery"] if "battery" in status.keys() else None
    #  {"battery":100,"humidity":69.72,"linkquality":180,"temperature":25.93,"voltage":3200}
    
    # Insert temperature/humidity into database periodically
    #print(f'{dt.datetime.now()}: inserting data into to table: {temperature},{humidity},{linkquality}{battery}')
    logging.debug(f'{dt.datetime.now()}: inserting data into to table: {temperature},{humidity},{linkquality}{battery}')

    # Insert temp and humidity data into table
    sqlcmd = f"INSERT INTO 'SENSORS' ('name', 'timestamp', 'temperature', 'humidity', 'linkquality', 'battery') " + \
        f"VALUES ('{sensor_name}','{timestamp}',{temperature:.2f},{humidity:.2f},{linkquality:.0f},{battery:.2f});"
    sqlcmd = sqlcmd.replace('None','NULL')
    cursor.execute(sqlcmd)
    #print("{} record inserted.".format(cursor.rowcount))
    logging.debug("{} record inserted.".format(cursor.rowcount))

    # Keep just the last 3 years of readings
    sqlcmd = f"DELETE FROM SENSORS WHERE datetime < datetime('now','localtime','-1095 days')"
    cursor.execute(sqlcmd)
    #print("{} records deleted.".format(cursor.rowcount))
    logging.debug("{} records deleted.".format(cursor.rowcount))
    db.commit()
        
    cursor.execute("SELECT * FROM SENSORS LIMIT 1;")
    rows = cursor.fetchall()
    logging.info(rows[0])
        
    #print(f"Timestamp: {dt.datetime.now():%Y-%m-%d %H:%M:%S}")
    #print(sensor_name, temperature, humidity, linkquality, battery)


# Connect to MQTT broker provided by zigbee2mqtt
client = mqtt.Client()
ret = client.connect(BROKER_IP, BROKER_PORT, MQTT_KEEPALIVE)
if ret != 0:
    logging.info(f'MQTT connect return code: {ret}')


client.subscribe(f"zigbee2/{SENSOR}")
client.on_message = on_message


# Subscribe to all zigbee sensors
client.subscribe(f'zigbee2mqtt/{SENSOR}', qos=QOS)
logging.info(f'Subscribed to: {SENSOR}')

try:
    client.loop_forever()
except KeyboardInterrupt:
    client.disconnect()
    logging.info('Terminating due to KeyboardInterrupt.')
    