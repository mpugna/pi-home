import paho.mqtt.client as mqtt
import datetime as dt
import sched, time


BROKER_PORT = 1883
BROKER_IP = "127.0.0.1"
MQTT_KEEPALIVE = 60
QOS = 0
SENSOR = "SNZB02_1"



def on_message(client, userdata, message):
    print(f"Timestamp: {dt.datetime.now():%Y-%m-%d %H:%M:%S}")
    print("message received " ,str(message.payload.decode("utf-8")))
    print("message topic=",message.topic)
    print("message qos=",message.qos)
    print("message retain flag=",message.retain)


# Connect to MQTT broker provided by zigbee2mqtt
client = mqtt.Client()
ret = client.connect(BROKER_IP, BROKER_PORT, MQTT_KEEPALIVE)
if ret != 0:
    print(f'MQTT connect return code: {ret}')


client.subscribe(f"zigbee2/{SENSOR}")
client.on_message = on_message


# Subscribe to all zigbee sensors
client.subscribe(f'zigbee2mqtt/{SENSOR}', qos=QOS)
print(f'Subscribed to: {SENSOR}')

try:
    client.loop_forever()
except KeyboardInterrupt:
    client.disconnect()
    print('Terminating due to KeyboardInterrupt.')
    