import pyaudio
import socket
import struct
import time
import threading
from rich.console import Console

console = Console()

# Audio Configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024
MULTICAST_GROUP = '224.3.29.71'
PORT = 10000

class AudioMaster:
    def __init__(self, group_name="DefaultGroup", device_index=None):
        self.group_name = group_name
        self.p = pyaudio.PyAudio()
        self.device_index = device_index
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        self.running = False
        self.sequence = 0

    @staticmethod
    def list_devices():
        p = pyaudio.PyAudio()
        devices = []
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                devices.append({
                    'index': i,
                    'name': info['name'],
                    'channels': info['maxInputChannels']
                })
        p.terminate()
        return devices

    def start(self):
        self.running = True
        # If stereo device (like loopback), use 2 channels
        channels = CHANNELS
        if self.device_index is not None:
            info = self.p.get_device_info_by_index(self.device_index)
            channels = min(2, info['maxInputChannels'])

        stream = self.p.open(format=FORMAT, channels=channels, rate=RATE, 
                             input=True, input_device_index=self.device_index,
                             frames_per_buffer=CHUNK)
        
        console.print(f"[bold green]Master started.[/bold green] Broadcasting to {MULTICAST_GROUP}:{PORT} (Group: {self.group_name})")
        console.print(f"Using device: {self.p.get_device_info_by_index(self.device_index)['name'] if self.device_index is not None else 'Default'}")
        
        try:
            while self.running:
                data = stream.read(CHUNK, exception_on_overflow=False)
                # If we captured mono, but broadcast expects stereo (or vice versa), 
                # for now we keep it simple, but we could handle resampling here.
                header = struct.pack("!Id", self.sequence, time.time())
                self.sock.sendto(header + data, (MULTICAST_GROUP, PORT))
                self.sequence += 1
        except KeyboardInterrupt:
            self.stop()
        finally:
            stream.stop_stream()
            stream.close()

    def stop(self):
        self.running = False
        self.p.terminate()

class AudioSlave:
    def __init__(self, multicast_group=MULTICAST_GROUP, port=PORT):
        self.multicast_group = multicast_group
        self.port = port
        self.p = pyaudio.PyAudio()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', self.port))
        
        mreq = struct.pack("4sl", socket.inet_aton(self.multicast_group), socket.INADDR_ANY)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        
        self.running = False
        self.last_sequence = -1

    def start(self):
        self.running = True
        stream = self.p.open(format=FORMAT, channels=CHANNELS, rate=RATE, 
                             output=True, frames_per_buffer=CHUNK)
        
        console.print(f"[bold blue]Slave started.[/bold blue] Listening for broadcast on {self.multicast_group}:{self.port}...")
        
        try:
            while self.running:
                data_packet, addr = self.sock.recvfrom(2048)
                header_size = struct.calcsize("!Id")
                header = data_packet[:header_size]
                audio_data = data_packet[header_size:]
                
                seq, timestamp = struct.unpack("!Id", header)
                
                # Simple Sync Logic: Drop out-of-order old packets
                if seq > self.last_sequence:
                    self.last_sequence = seq
                    stream.write(audio_data)
                else:
                    # Packet arrived too late or out of order
                    pass
        except KeyboardInterrupt:
            self.stop()
        finally:
            stream.stop_stream()
            stream.close()

    def stop(self):
        self.running = False
        self.p.terminate()
