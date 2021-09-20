#!/usr/bin/env python3

import pyaudio
import struct

import numpy as np

class Listener:
  def __init__(self, dataTime = 1/20, agcTime = 10, input = False):
    self._dataTime = dataTime
    self._agcTime = agcTime
    self._input = input
    self.p = pyaudio.PyAudio()
    
    self.left = self.right = self.fft = []
    
    self._agcMaxima = [0]
    self._agcIndex = 0
    self._agcLen = 0
    self._beatCb = None
    self._sampleRate = 0
    self._hasNewData = False
    self.buffersize = None
    
    self._doFFT = False
    self._doAgcFFT = False
    
  def start(self, dev = None):
    self._device = dev or self.getDefaultOutputDeviceInfo()
      
    if self._device == None:
      print("no device found")
      return
      
    print("device name: {} channels: {} defaultSampleRate: {}".format(self._device["name"], self._device["channels"], self._device["defaultSampleRate"]))
      
    if self._sampleRate != self._device["defaultSampleRate"]:
      self._sampleRate = self._device["defaultSampleRate"]
      self.buffersize = int(self._sampleRate * self._dataTime)
      self.fft = self.right = self.left = np.ndarray((self.buffersize))
      
      self._agcLen = int(1 / self._dataTime * self._agcTime)
      self._agcMaxima = np.ndarray((self._agcLen))
      self._agcMaxima.fill(2**15 * 0.1)
      self._agcIndex = 0
      self._lastBeatTime = 0
      self.meanAmp = 2**15 * 0.1
    
    try:
      self._stream = self.openStream(self._device)
    except OSError:
      self._stream = None
    
    if not self._stream:
      print("stream open failed")
      return
    
    self._stream.start_stream()
    
    return self._stream.is_active()
    
  def stop(self):
    if not self._stream:# or not self._stream.is_active():
      return False
    self._stream.stop_stream()
    return True
    
  def setBeatCb(self, cb):
    self._beatCb = cb
  
  def getDefaultOutputDeviceInfo(self):
    #Set default to first in list or ask Windows
    try:
      self.p.terminate()
      self.p.__init__()
      if self._input:
        info = self.p.get_default_input_device_info()
      else:
        info = self.p.get_default_output_device_info()
    except IOError:
      info = None
    
    #Handle no devices available
    if info == None:
        print ("No device available.")
        return None

    if (self.p.get_host_api_info_by_index(info["hostApi"])["name"]).find("WASAPI") == -1:
      for i in range(0, self.p.get_device_count()):
        x = self.p.get_device_info_by_index(i)
        is_wasapi = (self.p.get_host_api_info_by_index(x["hostApi"])["name"]).find("WASAPI") != -1
        if x["name"].find(info["name"]) >= 0 and is_wasapi:
          info = x
          break

    #Handle no devices available
    if info == None:
      print ("Device doesn't support WASAPI")
      return None
      
    info["channels"] = info["maxInputChannels"] if (info["maxOutputChannels"] < info["maxInputChannels"]) else info["maxOutputChannels"]
      
    return info
    
  def openStream(self, dev):
  
    is_input = dev["maxInputChannels"] > 0
    is_wasapi = (self.p.get_host_api_info_by_index(dev["hostApi"])["name"]).find("WASAPI") != -1
    
    #print("is input: {} is wasapi: {}".format(is_input, is_wasapi))

    if not is_input and not is_wasapi:
      print ("Selection is output and does not support loopback mode.")
      return None
    if is_wasapi:
      stream = self.p.open(
        format = pyaudio.paInt16,
        channels = (dev["channels"] if dev["channels"] < 2 else 2),
        rate = int(self._sampleRate),
        input = True,
        frames_per_buffer = self.buffersize,
        input_device_index = dev["index"],
        stream_callback=self.streamCallback,
        as_loopback = False if is_input else is_wasapi)
    else:
      stream = self.p.open(
        format = pyaudio.paInt16,
        channels = (dev["channels"] if dev["channels"] < 2 else 2),
        rate = int(self._sampleRate),
        input = True,
        frames_per_buffer = self.buffersize,
        input_device_index = dev["index"],
        stream_callback=self.streamCallback)
    return stream
    
  def closeStream(self):
    if not self._stream:
      return False
    self._stream.close()
    return True
      
  def streamCallback(self, buf, frame_count, time_info, flag):
    self._buf = buf
    arr = np.array(struct.unpack("%dh" % (len(buf)/2), buf))
    
    mx = arr.max()
    self._agcIndex += 1
    if self._agcIndex >= self._agcLen:
      self._agcIndex = 0
    self._agcMaxima[self._agcIndex] = mx
      
    self.meanAmp = np.max(np.absolute(self._agcMaxima))
    
    if self.meanAmp > 2**15 * 0.02:
      amp = 1 / self.meanAmp
    else:
      amp = 1 / (2**15 * 0.02)
    
    if self._device["channels"] >= 2:
      self.left, self.right  = arr[::2]  * amp, arr[1::2] * amp
      if self._doFFT:
        self.fft = self.fftCalc((self.left+self.right)/2)
    else:
      self.left = self.right = arr * amp
      if self._doFFT:
        self.fft = self.fftCalc(self.left)
    
    self._hasNewData = True
    
    if self._doAgcFFT:
      self.agcFFT = np.fft.rfft(self._agcMaxima, self.beatnFFT) / self.beatnFFT
    
    if self._beatCb and mx * (time_info["current_time"] - self._lastBeatTime) > 0.5:
      self._lastBeatTime = time_info["current_time"]
      self._beatCb(self.fft)
      
    return (None, pyaudio.paContinue)
  
  def hasNewData(self):
    if not self._hasNewData:
      return False
    self._hasNewData = False
    return True
  
  def getSampleRate(self):
    return int(self._sampleRate)
  
  def getAgc(self):
    return self.meanAmp / 2**15
    
  def getVolume(self):
    if self._agcMaxima.sum() == 0:
      return 0
    return self._agcMaxima[self._agcIndex] / self.meanAmp
  
  def isActive(self):
    if not self._stream:
      return False
    return self._stream.is_active()
  
  def fftSetLimits(self, nFFT, fMin, fMax):
    self._doFFT = True
    self.nFFT = nFFT
    self.fftMin = int(fMin / self._sampleRate * nFFT)
    self.fftMax = int(fMax / self._sampleRate * nFFT)
    print("nFFT: {} \tfftMin: {} \tfftMax: {}".format(self.nFFT, self.fftMin, self.fftMax))

  def agcFftSetLimits(self, fMin, fMax):
    self._doAgcFFT = True
    self.beatnFFT = self._agcLen
    self.beatFftMin = int(fMin * self._dataTime * self.beatnFFT)
    self.beatFftMax = int(fMax * self._dataTime * self.beatnFFT)
    print("beat nFFT: {} \tfftMin: {} \tfftMax: {}".format(self.beatnFFT, self.beatFftMin, self.beatFftMax))
    
  def fftCalc(self, data):
    return abs(np.fft.rfft(data, self.nFFT)[self.fftMin:self.fftMax]) / self.nFFT
              
  def fftGroup(self, fft, limits):
    groups = []
    for freqs in zip(limits, limits[1:]):
      a = int(freqs[0] / self._sampleRate * self.nFFT)
      b = int(freqs[1] / self._sampleRate * self.nFFT)
      #groups.append(sum(fft[a:b]) / (b-a) if (b-a) > 0 else 0)
      if b != a:
        groups.append(max(fft[a:b]))
      else:
        groups.append(fft[a])
    return groups