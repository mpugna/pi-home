# Part of the Pi-Home program for use with Zigbee devices and a Raspberry Pi with email alerts
# (C) 2020 Derek Schuurman
# License: GNU General Public License (GPL) v3
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import logging
import sqlite3
from datetime import datetime
import paho.mqtt.client as mqtt
import json
import logging
from datetime import datetime
import smtplib
from email.utils import make_msgid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Constants
TABLE = 'SensorData'
TIMER_PERIOD = 180

# Alarm codes
LOW_TEMPERATURE_ALARM = 1
FREEZING_ALARM = 2
HUMIDITY_ALARM = 3

# Constants
TEMPERATURE_HYSTERESIS = 1.0
HUMIDITY_HYSTERESIS = 2.0

# Sensor class definitions

class SNZB02:
    ''' class to manage device state for Sonoff SNZB02 '''

    def __init__(self, sensor_list):
        ''' Constructor: connect to MQTT broker and initialize state variables
            control bulbs, outlets, and store and retrieve sensor states
        '''
        self.sensor_list = sensor_list


        # Initialize states to None
        self.temperature = None
        self.humidity = None
        self.battery = None
        self.linkquality = False
     
    def set_temperature(self, temp):
        self.temperature = temp

    def set_humidity(self, humidity):
        self.humidity = humidity

    def get_temperature(self):
        return self.temperature

    def get_humidity(self):
        return self.humidity

    def get_battery(self):
        return self.battery

    def get_linkquality(self):
        return self.linkquality

    def is_low_temp(self):
        if self.temperature == None:
            return False
        else:
            return self.temperature < self.low_temp_threshold

    def __str__(self):
        sensor_str = self.sensor_list[0]
        for i in range(1,len(self.sensor_list)):
            sensor_str += f', {self.sensor_list[i]}'
        return sensor_str
    

class Events:
    ''' Event class used to handle periodic sensor sampling and MQTT messages from sensors
    '''
    def __init__(self, scheduler, sensors, database, mail):
        ''' Constructor 
        '''
        self.scheduler = scheduler
        self.sensors = sensors
        self.mail = mail

        # Initialize a list to store alarms that may occur
        self.alarms = []

        # Connect to the sqlite database and create new table if not found
        self.db = sqlite3.connect(database)
        self.db.execute(f'CREATE TABLE IF NOT EXISTS {TABLE} (datetime TEXT NOT NULL, temperature double, humidity double, pressure double)')
        self.cursor = self.db.cursor()

    def timer_handler(self, signum, frame):
        ''' Timer schedule handler- fires every second and manages sensor readings
        '''
        # first capture sensor readings
        temperature = self.sensors.get_temperature()
        humidity = self.sensors.get_humidity()
        pressure = self.sensors.get_pressure()

        # If there is no useful data, return rather than storing NULL data
        if temperature==None and humidity==None and pressure==None:
            logging.debug(f'{datetime.now()}: no valid data to store in table...')
            return

        # Insert temperature/humidity into database periodically
        logging.debug(f'{datetime.now()}: inserting data into to table: {temperature},{humidity},{pressure}')

        # Insert temp and humidity data into table
        sqlcmd = f"INSERT INTO {TABLE} VALUES (datetime('now','localtime'),{temperature},{humidity},{pressure})"
        sqlcmd = sqlcmd.replace('None','NULL')
        self.cursor.execute(sqlcmd)
        logging.debug("{} record inserted.".format(self.cursor.rowcount))

        # Keep just the last year of readings
        sqlcmd = f"DELETE FROM {TABLE} WHERE datetime < datetime('now','localtime','-365 days')"
        self.cursor.execute(sqlcmd)
        logging.debug("{} records deleted.".format(self.cursor.rowcount))
        self.db.commit()

    def timer_event(self):
        ''' Scheduler handler to periodically store sensor readings
        '''
        # set next timer event
        self.scheduler.enter(TIMER_PERIOD, 1, self.timer_event)

        # first capture sensor readings
        temperature = self.sensors.get_temperature()
        humidity = self.sensors.get_humidity()
        pressure = self.sensors.get_pressure()

        # If there is no useful data, return rather than storing NULL data
        if temperature==None and humidity==None and pressure==None:
            logging.debug(f'{datetime.now()}: no valid data to store in table...')
            return

        # Insert temperature/humidity into database periodically
        logging.debug(f'{datetime.now()}: inserting data into to table: {temperature},{humidity},{pressure}')

        # Insert temp and humidity data into table
        sqlcmd = f"INSERT INTO {TABLE} VALUES (datetime('now','localtime'),{temperature},{humidity},{pressure})"
        sqlcmd = sqlcmd.replace('None','NULL')
        self.cursor.execute(sqlcmd)
        logging.debug("{} record inserted.".format(self.cursor.rowcount))

        # Keep just the last year of readings
        sqlcmd = f"DELETE FROM {TABLE} WHERE datetime < datetime('now','localtime','-365 days')"
        self.cursor.execute(sqlcmd)
        logging.debug("{} records deleted.".format(self.cursor.rowcount))
        self.db.commit()

    def mqtt_message_handler(self, client, data, msg):
        ''' MQTT message handler for messages from sensors
            Send e-mail alert when water leak or low battery detected
        '''
        message = str(msg.payload.decode("utf-8"))
        sensor = msg.topic.split('/')[1]   # Extract sensor "friendly name" from MQTT topic
        logging.debug(f'{datetime.now()} MQTT Message received from {sensor}: {message}')
        status = json.loads(message) # Parse JSON message from sensor into a dictionary

        # check MQTT dictionary keys for various variables exposed by sensors
        # Water leak status
        if "water_leak" in status:
            if status['water_leak'] and sensor not in self.alarms:
                logging.info(f'Water leak alarm detected for {sensor}!')
                self.mail.send(f'Water leak alarm detected for {sensor}!',message)
                self.alarms.append(sensor)
                self.sensors.water_leak = True
            elif not status['water_leak'] and sensor in self.alarms:
                logging.info(f'Water leak alarm stopped for {sensor}!')
                self.mail.send(f'Water leak alarm stopped for {sensor}',message)
                self.alarms.remove(sensor)
                self.sensors.water_leak = False

        # Low battery status
        if 'battery_low' in status and status['battery_low']:
            logging.info(f'Low battery detected for {sensor}!')
            self.mail.send(f'Low battery detected for {sensor}!', message)

        # temperature reading
        if 'temperature' in status:
            logging.debug(f'Temperature = {status["temperature"]} degrees C')
            self.sensors.temperature = float(status['temperature'])
            # Next, check temperature value; send an alert if it falls below a preset threshold
            if self.sensors.is_low_temp() and LOW_TEMPERATURE_ALARM not in self.alarms:
                message = f'The house temperature has fallen to: {status["temperature"]} degrees C!'
                logging.info(f'{datetime.now()}: {message}')
                self.mail.send('Home temperature warning!', message)
                self.alarms.append(LOW_TEMPERATURE_ALARM)
            # otherwise check if temperature returns back above threshold
            elif self.sensors.is_temp_normal() and LOW_TEMPERATURE_ALARM in self.alarms:
                message = f'The house temperature is now risen to {status["temperature"]} degrees C.'
                logging.info(f'{datetime.now()}: {message}')
                self.mail.send('Home temperature update', message)
                self.alarms.remove(LOW_TEMPERATURE_ALARM)
            # check explicitly for freezing temperatures
            elif self.sensors.is_freezing() and FREEZING_ALARM not in self.alarms:
                message = f'The house temperature is freezing! Temperature={status["temperature"]} degrees C!'
                logging.info(f'{datetime.now()}: {message}')
                self.mail.send('Home temperature FREEZING!', message)
                self.alarms.append(FREEZING_ALARM)
            # otherwise check if things are no longer freezing
            elif self.sensors.is_above_freezing() and FREEZING_ALARM in self.alarms:
                message = f'The house temperature is now risen above freezing. Temperature={status["temperature"]} degrees C.'
                logging.info(f'{datetime.now()}: {message}')
                self.mail.send('Home temperature update', message)
                self.alarms.remove(FREEZING_ALARM)
        
        # Humidity reading
        if 'humidity' in status:
            logging.debug(f'Humidity = {status["humidity"]}')
            self.sensors.humidity = float(status['humidity'])
            # check humidity value; send an alert if it rises above a preset threshold
            if self.sensors.is_high_humidity() and HUMIDITY_ALARM not in self.alarms:
                message = f'The house humidity has risen to: {status["humidity"]}!'
                logging.info(f'{datetime.now()}: {message}')
                self.mail.send('Home humidity warning!', message)
                self.alarms.append(HUMIDITY_ALARM)
            # otherwise check if things are back to normal
            elif self.sensors.is_humidity_normal() and HUMIDITY_ALARM in self.alarms:
                message = f'The house humidity has now fallen to: {status["humidity"]}.'
                logging.info(f'{datetime.now()}: {message}')
                self.mail.send('Home humidity update', message)
                self.alarms.remove(HUMIDITY_ALARM)

        # Air pressure
        if 'pressure' in status:
            logging.debug(f'Air pressure = {status["pressure"]} hPa')
            self.sensors.pressure = float(status['pressure'])

        # Action messages are used to send miscellaneous info and alerts
        if 'action' in status:
            message = f'{sensor} reporting: {status["action"]}!'
            logging.info(f'{datetime.now()}: {message}')
            self.mail.send(f'{status["action"]} notification', message)

class Mail:
    ''' Class to encapsulate methods to send an alert email if sensor reading goes beyond 
        preset thresholds. Requires an SMTP server to be available.
    '''
    def __init__(self, from_address, to_address, server):
        ''' Function to send a warning email - assumes server running locally to forward mail
        '''
        self.to_address = to_address        
        self.from_address = from_address
        self.server = server

    def send(self, subject, message, html=None):
        ''' Function to send an email - requires SMTP server to forward mail
            Includes optional support for html messages
        '''
        # if no to-address or server set then just return
        if self.to_address == '' or self.server == '':
            logging.debug('recipient address or SMTP server not set - no email sent')
            return
        
        # message to be sent
        if html == None:
            msg = MIMEText(message)
        else:
            msg = MIMEMultipart('alternative')
        msg['To'] = self.to_address
        msg['From'] = self.from_address
        msg['Subject'] = subject
        msg['Message-ID'] = make_msgid()

        # If html part present, set the MIME types of both parts - plain and html
        # and attach parts into message container.
        if html != None:
            msg.attach(MIMEText(message, 'plain'))
            msg.attach(MIMEText(html, 'html'))

        # send the mail and terminate the session
        try:
            # creates SMTP session and sends mail
            s = smtplib.SMTP(self.server)
            s.sendmail(self.from_address, self.to_address, msg.as_string())
            logging.info(f'{datetime.now()}: Email alert sent to {self.to_address}')
            s.quit()
        except:
            logging.info(f'{datetime.now()}: Email alert failed to send!')

# Self test code
if __name__ == '__main__':
    sensors = Sensors(['test_sensor'],10, 80)
    sensors.set_temperature(10)
    assert (sensors.get_temperature() == 10)
    sensors.set_humidity(10)
    assert (sensors.get_humidity() == 10)
    sensors.set_pressure(1000)
    assert (sensors.get_pressure() == 1000)
    sensors.set_temperature(1+TEMPERATURE_HYSTERESIS)
    assert (sensors.is_above_freezing() == True)
    sensors.set_temperature(-1)
    assert (sensors.is_above_freezing() == False)
    sensors.set_temperature(8)
    assert (sensors.is_temp_normal() == False)
    sensors.set_temperature(11+TEMPERATURE_HYSTERESIS)
    assert (sensors.is_temp_normal() == True)
    sensors.set_humidity(80)
    assert (sensors.is_high_humidity() == False)
    sensors.set_humidity(81)
    assert (sensors.is_high_humidity() == True)
    sensors.set_humidity(79-HUMIDITY_HYSTERESIS)
    assert (sensors.is_humidity_normal() == True)
    # Test mail with no settings
    mail = Mail('','','server')
    try:
        mail.send('subject','message')
        assert False, 'Test failed: mail send method should throw an exception'
    except:
        assert True
    