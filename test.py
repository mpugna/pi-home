import paho.mqtt.client as mqtt
import time


BROKER_PORT = 1883
BROKER_IP = "127.0.0.1"
MQTT_KEEPALIVE = 60
QOS = 0
SENSOR = "SNZB02_01"


def on_message(client, userdata, message):
    print("message received " ,str(message.payload.decode("utf-8")))
    print("message topic=",message.topic)
    print("message qos=",message.qos)
    print("message retain flag=",message.retain)


# Connect to MQTT broker provided by zigbee2mqtt
client = mqtt.Client()
ret = client.connect(BROKER_IP, BROKER_PORT, MQTT_KEEPALIVE)
if ret != 0:
    print(f'MQTT connect return code: {ret}')
client.loop_start() #start the loop

client.subscribe(f"zigbee2/{SENSOR}")
client.on_message = on_message


# Subscribe to all zigbee sensors
client.subscribe(f'zigbee2mqtt/{SENSOR}', qos=QOS)
print(f'Subscribed to: {SENSOR}')

time.sleep(100) # wait
client.loop_stop() #stop the loop