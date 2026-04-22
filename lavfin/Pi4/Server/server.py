#!/usr/bin/python 
# -*- coding: utf-8 -*-
import io
import math
import socket
import numpy as np
import struct
import time
import requests
import cv2
import queue
import threading
from picamera2 import Picamera2, Preview
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
from picamera2.encoders import Quality
from threading import Condition
import fcntl
import sys
from Motor import *
from servo import *
from Led import *
from Buzzer import *
from ADC import *
from Thread import *
from Light import *
from Ultrasonic import *
from Line_Tracking import *
from threading import Timer
from Command import COMMAND as cmd
import RPi.GPIO as GPIO


class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()
        self.ai_frame = None
        self.ai_condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()
        
        with self.ai_condition:
            self.ai_frame = buf
            self.ai_condition.notify_all()


class Server:
    def __init__(self):
        self.PWM = Motor()
        self.servo = Servo()
        self.led = Led()
        self.ultrasonic = Ultrasonic()
        self.buzzer = Buzzer()
        self.adc = Adc()
        self.light = Light()
        self.infrared = Line_Tracking()
        self.tcp_Flag = True
        self.sonic = False
        self.Light = False
        self.Line = False
        self.Mode = 'one'
        self.endChar = '\n'
        self.intervalChar = '#'
        self.rotation_flag = False
        
        # AI Detection variables
        self.SERVER_URL = "http://localhost:32168/v1/vision/detection"
        self.frame_count = 0
        self.last_detection_time = 0
        self.detection_cooldown = 5
        
        # Async processing - SINGLE FRAME QUEUE for minimal delay
        self.detection_queue = queue.Queue(maxsize=1)  # Only keep latest frame
        self.detection_results = queue.Queue()
        
        self.ai_camera = None
        self.output = None
        
        # Start async processing thread
        self.async_processor = threading.Thread(target=self.async_detection_worker)
        self.async_processor.daemon = True
        self.async_processor.start()
        
        print("AI Detection ready - optimized for minimal delay")

    def async_detection_worker(self):
        """Separate thread for AI detection - optimized version"""
        print("Optimized AI detection worker started")
        while True:
            try:
                # Get the LATEST frame only (discard old ones if queue full)
                try:
                    frame_data = self.detection_queue.get(timeout=0.5)
                    if frame_data is None:
                        break
                except queue.Empty:
                    continue
                    
                files, frame_bgr, frame_timestamp = frame_data
                
                # Skip processing if frame is too old (more than 2 seconds)
                if time.time() - frame_timestamp > 2.0:
                    self.detection_queue.task_done()
                    continue
                
                # Process with timeout but don't wait forever
                try:
                    resp = requests.post(self.SERVER_URL, files=files, timeout=8)
                    
                    if resp.ok:
                        result = resp.json()
                        if result.get("success") and "predictions" in result:
                            # Skip if result is too old
                            if time.time() - frame_timestamp < 3.0:
                                self.detection_results.put((frame_bgr, result, frame_timestamp))
                        else:
                            print("AI detection failed in response")
                            
                except requests.exceptions.Timeout:
                    print("AI detection timeout (8s) - skipping frame")
                except Exception as e:
                    print(f"Async detection error: {e}")
                    
                self.detection_queue.task_done()
                
            except Exception as e:
                print(f"Error in async worker: {e}")

    def process_detection_results(self):
        """Process completed detections - skip old results"""
        try:
            while True:
                frame_bgr, result, frame_timestamp = self.detection_results.get_nowait()
                
                # Skip processing if result is too old
                if time.time() - frame_timestamp > 3.0:
                    self.detection_results.task_done()
                    continue
                
                current_time = time.time()
                for pred in result["predictions"]:
                    label = pred["label"].lower()
                    conf = pred["confidence"]
                    
                    if conf > 0.6 and label in ["person", "dog", "cat"]:
                        print(f"ALERTA: Detectado {label.upper()} con {conf:.2f}")
                        
                        if current_time - self.last_detection_time > self.detection_cooldown:
                            self.save_detection_image(frame_bgr, pred, label, conf)
                            self.last_detection_time = current_time
                            
                        self.on_object_detected(label)
                        
                self.detection_results.task_done()
                
        except queue.Empty:
            pass

    def detect_objects(self):
        """Optimized non-blocking object detection"""
        if self.output is None:
            return

        self.frame_count += 1
        
        # Process EVERY frame but with queue size limit (we'll only keep latest)
        try:
            with self.output.ai_condition:
                if self.output.ai_frame is None:
                    self.process_detection_results()
                    return
                
                jpeg_data = self.output.ai_frame
                
            # Convert JPEG to OpenCV format
            jpeg_array = np.frombuffer(jpeg_data, dtype=np.uint8)
            frame_bgr = cv2.imdecode(jpeg_array, cv2.IMREAD_COLOR)
            
            if frame_bgr is None:
                self.process_detection_results()
                return
            
            # Use even smaller resolution for faster processing
            frame_for_ai = cv2.resize(frame_bgr, (320, 240))  # Smaller = faster
            
            # Lower quality for faster transmission
            _, buffer = cv2.imencode(".jpg", frame_for_ai, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            
            files = {"image": ("frame.jpg", buffer.tobytes(), "image/jpeg")}
            current_time = time.time()
            
            # Always try to put latest frame (discard old ones if queue full)
            try:
                self.detection_queue.put_nowait((files, frame_bgr, current_time))
            except queue.Full:
                # If queue full, replace with latest frame
                try:
                    self.detection_queue.get_nowait()  # Remove oldest
                    self.detection_queue.put_nowait((files, frame_bgr, current_time))
                except:
                    pass
            
            # Process any available results
            self.process_detection_results()
            
        except Exception as e:
            print(f"Error in object detection: {e}")
            self.process_detection_results()

    def save_detection_image(self, original_frame, prediction, label, confidence):
        """Save detected object image to /tmp directory"""
        try:
            frame_to_save = original_frame.copy()
            
            # Scale coordinates from AI resolution (240x180) to original (400x300)
            scale_x = original_frame.shape[1] / 320
            scale_y = original_frame.shape[0] / 240
            
            x1 = int(prediction["x_min"] * scale_x)
            y1 = int(prediction["y_min"] * scale_y)
            x2 = int(prediction["x_max"] * scale_x)
            y2 = int(prediction["y_max"] * scale_y)
            
            # Ensure coordinates are within frame boundaries
            x1 = max(0, min(x1, original_frame.shape[1] - 1))
            y1 = max(0, min(y1, original_frame.shape[0] - 1))
            x2 = max(0, min(x2, original_frame.shape[1] - 1))
            y2 = max(0, min(y2, original_frame.shape[0] - 1))
            
            # Draw bounding box
            cv2.rectangle(frame_to_save, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame_to_save, f"{label} {confidence:.2f}",
                       (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX,
                       0.5, (0, 255, 0), 2)
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"/tmp/detected_{label}_{timestamp}_{confidence:.2f}.jpg"
            
            success = cv2.imwrite(filename, frame_to_save)
            if success:
                print(f"Imagen guardada: {filename}")
            else:
                print(f"Error: No se pudo guardar la imagen {filename}")
            
        except Exception as e:
            print(f"Error saving detection image: {e}")

    def on_object_detected(self, label):
        """Optional: Trigger actions when specific objects are detected"""
        try:
            if label == "person":
                self.led.ledIndex(0x01, 255, 0, 0)
                self.buzzer.run('1')
                time.sleep(0.1)  # Shorter beep
                self.led.ledIndex(0x01, 0, 0, 0)
                self.buzzer.run('0')
                
            elif label in ["dog", "cat"]:
                self.led.ledIndex(0x02, 0, 255, 0)
                time.sleep(0.2)  # Shorter flash
                self.led.ledIndex(0x02, 0, 0, 0)
                
        except Exception as e:
            print(f"Error in detection action: {e}")

    def ai_detection_loop(self):
        """Optimized AI detection loop"""
        print("Optimized AI Detection loop started")
        while True:
            self.detect_objects()
            time.sleep(0.05)  # Shorter delay for more responsive processing

    def get_interface_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        return socket.inet_ntoa(fcntl.ioctl(s.fileno(),
                                            0x8915,
                                            struct.pack('256s', b'wlan0'[:15])
                                            )[20:24])

    def StartTcpServer(self):
        HOST = str(self.get_interface_ip())
        self.server_socket1 = socket.socket()
        self.server_socket1.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.server_socket1.bind((HOST, 5000))
        self.server_socket1.listen(1)
        self.server_socket = socket.socket()
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.server_socket.bind((HOST, 8000))
        self.server_socket.listen(1)
        print('Server address: ' + HOST)

    def StopTcpServer(self):
        try:
            self.connection.close()
            self.connection1.close()
        except Exception as e:
            print('\n' + "No client connection")

    def Reset(self):
        self.StopTcpServer()
        self.StartTcpServer()
        self.SendVideo = threading.Thread(target=self.sendvideo)
        self.ReadData = threading.Thread(target=self.readdata)
        self.SendVideo.start()
        self.ReadData.start()

    def send(self, data):
        self.connection1.send(data.encode('utf-8'))

    def sendvideo(self):
        try:
            self.connection, self.client_address = self.server_socket.accept()
            self.connection = self.connection.makefile('wb')
        except:
            pass
        self.server_socket.close()
        print("socket video connected ... ")
        
        # Setup camera for streaming
        camera = Picamera2()
        camera.configure(camera.create_video_configuration(main={"size": (400, 300)}))
        self.output = StreamingOutput()
        encoder = JpegEncoder(q=90)
        
        # Start AI detection thread
        self.AIDetection = threading.Thread(target=self.ai_detection_loop)
        self.AIDetection.start()
        print("Optimized AI Detection started")
        
        camera.start_recording(encoder, FileOutput(self.output), quality=Quality.VERY_HIGH)
        
        while True:
            with self.output.condition:
                self.output.condition.wait()
                frame = self.output.frame
            try:
                lenFrame = len(self.output.frame)
                lengthBin = struct.pack('<I', lenFrame)
                self.connection.write(lengthBin)
                self.connection.write(frame)
            except Exception as e:
                camera.stop_recording()
                camera.close()
                print("End transmit ... ")
                break

    def stopMode(self):
        try:
            stop_thread(self.infraredRun)
            self.PWM.setMotorModel(0, 0, 0, 0)
        except:
            pass
        try:
            stop_thread(self.lightRun)
            self.PWM.setMotorModel(0, 0, 0, 0)
        except:
            pass
        try:
            stop_thread(self.ultrasonicRun)
            self.PWM.setMotorModel(0, 0, 0, 0)
            self.servo.setServoPwm('0', 90)
            self.servo.setServoPwm('1', 90)
        except:
            pass
        self.sonic = False
        self.Light = False
        self.Line = False
        self.send('CMD_MODE' + '#1' + '#' + '0' + '#' + '0' + '\n')
        self.send('CMD_MODE' + '#3' + '#' + '0' + '\n')
        self.send('CMD_MODE' + '#2' + '#' + '000' + '\n')

    def readdata(self):
        try:
            try:
                self.connection1, self.client_address1 = self.server_socket1.accept()
                print("Client connection successful !")
            except:
                print("Client connect failed")
            restCmd = ""
            self.server_socket1.close()
            while True:
                try:
                    AllData = restCmd + self.connection1.recv(1024).decode('utf-8')
                except:
                    if self.tcp_Flag:
                        self.Reset()
                    break
                print(AllData)
                if len(AllData) < 5:
                    restCmd = AllData
                    if restCmd == '' and self.tcp_Flag:
                        self.Reset()
                        break
                restCmd = ""
                if AllData == '':
                    break
                else:
                    cmdArray = AllData.split("\n")
                    if (cmdArray[-1] != ""):
                        restCmd = cmdArray[-1]
                        cmdArray = cmdArray[:-1]

                for oneCmd in cmdArray:
                    data = oneCmd.split("#")
                    if data is None:
                        continue
                    elif cmd.CMD_MODE in data:
                        if data[1] == 'one' or data[1] == "0":
                            self.stopMode()
                            self.Mode = 'one'
                        elif data[1] == 'two' or data[1] == "1":
                            self.stopMode()
                            self.Mode = 'two'
                            self.lightRun = threading.Thread(target=self.light.run)
                            self.lightRun.start()
                            self.Light = True
                            self.lightTimer = threading.Timer(0.3, self.sendLight)
                            self.lightTimer.start()
                        elif data[1] == 'three' or data[1] == "3":
                            self.stopMode()
                            self.Mode = 'three'
                            self.ultrasonicRun = threading.Thread(target=self.ultrasonic.run)
                            self.ultrasonicRun.start()
                            self.sonic = False
                            self.ultrasonicTimer = threading.Timer(5, self.sendUltrasonic)
                            self.ultrasonicTimer.start()
                        elif data[1] == 'four' or data[1] == "2":
                            self.stopMode()
                            self.Mode = 'four'
                            self.infraredRun = threading.Thread(target=self.infrared.run)
                            self.infraredRun.start()
                            self.Line = True
                            self.lineTimer = threading.Timer(0.4, self.sendLine)
                            self.lineTimer.start()

                    elif (cmd.CMD_MOTOR in data) and self.Mode == 'one':
                        try:
                            data1=int(data[1])
                            data2=int(data[2])
                            data3=int(data[3])
                            data4=int(data[4])
                            if data1==None or data2==None or data3==None or data4==None:
                                continue
                            self.PWM.setMotorModel(data1, data2, data3, data4)
                        except:
                            pass
                    elif (cmd.CMD_M_MOTOR in data) and self.Mode == 'one':
                        try:
                            data1 = int(data[1])
                            data2 = int(data[2])
                            data3 = int(data[3])
                            data4 = int(data[4])

                            LX = -int((data2 * math.sin(math.radians(data1))))
                            LY = int(data2 * math.cos(math.radians(data1)))
                            RX = int(data4 * math.sin(math.radians(data3)))
                            RY = int(data4 * math.cos(math.radians(data3)))

                            FR = LY - LX + RX
                            FL = LY + LX - RX
                            BL = LY - LX - RX
                            BR = LY + LX + RX

                            if data1==None or data2==None or data3==None or data4==None:
                                continue
                            self.PWM.setMotorModel(FL, BL, FR, BR)
                        except:
                            pass
                    elif (cmd.CMD_CAR_ROTATE in data) and self.Mode == 'one':
                        try:

                            data1 = int(data[1])
                            data2 = int(data[2])
                            data3 = int(data[3])
                            data4 = int(data[4])
                            set_angle = data3
                            if data4 == 0:
                                try:
                                    stop_thread(Rotate_Mode)
                                    self.rotation_flag = False
                                except:
                                    pass
                                LX = -int((data2 * math.sin(math.radians(data1))))
                                LY = int(data2 * math.cos(math.radians(data1)))
                                RX = int(data4 * math.sin(math.radians(data3)))
                                RY = int(data4 * math.cos(math.radians(data3)))

                                FR = LY - LX + RX
                                FL = LY + LX - RX
                                BL = LY - LX - RX
                                BR = LY + LX + RX

                                if data1 == None or data2 == None or data3 == None or data4 == None:
                                    continue
                                self.PWM.setMotorModel(FL, BL, FR, BR)
                            elif self.rotation_flag == False:
                                self.angle = data[3]
                                try:
                                    stop_thread(Rotate_Mode)
                                except:
                                    pass
                                self.rotation_flag = True
                                Rotate_Mode = threading.Thread(target=self.PWM.Rotate, args=(data3,))
                                Rotate_Mode.start()
                        except:
                            pass
                    elif cmd.CMD_SERVO in data:
                        try:
                            data1 = data[1]
                            data2 = int(data[2])
                            if data1 is None or data2 is None:
                                continue
                            self.servo.setServoPwm(data1, data2)
                        except:
                            pass

                    elif cmd.CMD_LED in data:
                        try:
                            data1=int(data[1])
                            data2=int(data[2])
                            data3=int(data[3])
                            data4=int(data[4])
                            if data1==None or data2==None or data3==None or data4==None:
                                continue
                            self.led.ledIndex(data1, data2, data3, data4)
                        except:
                            pass
                    elif cmd.CMD_LED_MOD in data:
                        self.LedMoD = data[1]
                        if self.LedMoD == '0':
                            try:
                                stop_thread(Led_Mode)
                            except:
                                pass
                        if self.LedMoD == '1':
                            try:
                                stop_thread(Led_Mode)
                            except:
                                pass
                            self.led.ledMode(self.LedMoD)
                            time.sleep(0.1)
                            self.led.ledMode(self.LedMoD)
                        else:
                            try:
                                stop_thread(Led_Mode)
                            except:
                                pass
                            time.sleep(0.1)
                            Led_Mode = threading.Thread(target=self.led.ledMode, args=(data[1],))
                            Led_Mode.start()
                    elif cmd.CMD_SONIC in data:
                        if data[1] == '1':
                            self.sonic = True
                            self.ultrasonicTimer = threading.Timer(0.5, self.sendUltrasonic)
                            self.ultrasonicTimer.start()
                        else:
                            self.sonic = False
                    elif cmd.CMD_BUZZER in data:
                        try:
                            self.buzzer.run(data[1])
                        except:
                            pass
                    elif cmd.CMD_LIGHT in data:
                        if data[1] == '1':
                            self.Light = True
                            self.lightTimer = threading.Timer(0.3, self.sendLight)
                            self.lightTimer.start()
                        else:
                            self.Light = False
                    elif cmd.CMD_POWER in data:
                        ADC_Power = self.adc.recvADC(2) * 5
                        try:
                            self.send(cmd.CMD_POWER + '#' + str(round(ADC_Power, 2)) + '\n')
                        except:
                            pass
        except Exception as e:
            print(e)
        self.StopTcpServer()

    def sendUltrasonic(self):
        if self.sonic == True:
            ADC_Ultrasonic = self.ultrasonic.get_distance()
            try:
                self.send(cmd.CMD_MODE + "#" + "3" + "#" + str(ADC_Ultrasonic) + '\n')
            except:
                self.sonic = False
            self.ultrasonicTimer = threading.Timer(0.23, self.sendUltrasonic)
            self.ultrasonicTimer.start()

    def sendLight(self):
        if self.Light == True:
            ADC_Light1 = self.adc.recvADC(0)
            ADC_Light2 = self.adc.recvADC(1)
            try:
                self.send("CMD_MODE#1" + '#' + str(ADC_Light1) + '#' + str(ADC_Light2) + '\n')
            except:
                self.Light = False
            self.lightTimer = threading.Timer(0.17, self.sendLight)
            self.lightTimer.start()

    def sendLine(self):
        if self.Line == True:
            Line1 = 1 if GPIO.input(14) else 0
            Line2 = 1 if GPIO.input(15) else 0
            Line3 = 1 if GPIO.input(23) else 0
            try:
                self.send("CMD_MODE#2" + '#' + str(Line1) + str(Line2) + str(Line3) + '\n')
            except:
                self.Line = False
            self.LineTimer = threading.Timer(0.20, self.sendLine)
            self.LineTimer.start()

    def Power(self):
        while True:
            ADC_Power = self.adc.recvADC(2) * 5
            try:
                self.send(cmd.CMD_POWER + '#' + str(round(ADC_Power, 2)) + '\n')
            except:
                pass
            time.sleep(3)
            if ADC_Power < 10:
                for i in range(4):
                    self.buzzer.run('1')
                    time.sleep(0.1)
                    self.buzzer.run('0')
                    time.sleep(0.1)
            elif ADC_Power < 10.5:
                for i in range(2):
                    self.buzzer.run('1')
                    time.sleep(0.1)
                    self.buzzer.run('0')
                    time.sleep(0.1)
            else:
                self.buzzer.run('0')


if __name__ == '__main__':
    server = Server()
    server.StartTcpServer()
    server.Reset()