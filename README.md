# MQTT Audio Level Meter

Publishes the volume of an audio source to a MQTT server.

Test setup: Raspberry Pi with an USB microphone and a local Mosquitto server

Can be configured to capture audio output or input under Linux and Windows.

## Installation

```bash
python3 -m pip install paho.mqtt
python3 -m pip install pyaudio
python3 main.py
```
