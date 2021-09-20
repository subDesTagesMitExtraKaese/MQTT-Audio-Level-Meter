#!/usr/bin/env python3

import time

import paho.mqtt.client as mqtt

import audioHandler

mqtt_host = "localhost"
mqtt_port = 1883
interval = 20.0 # sec
use_audio_sink = False

audio = audioHandler.Listener(dataTime=interval if interval<5 else 5, agcTime=interval, input=not use_audio_sink)


def main():
  audio.start()
  mqttc = mqtt.Client()
  mqttc.connect_async(mqtt_host, mqtt_port)
  mqttc.loop_start()
  while True:
    if audio.hasNewData():
      vol = audio.getAgc()
      mqttc.publish("Room/noise", "{:.4f}".format(vol))
      time.sleep(interval)
    else:
      time.sleep(.1)


if __name__ == "__main__":
  main()