import pyaudio
import socket
import struct
import time
import threading
import queue
from rich.console import Console

console = Console()

# Audio Configuration
FORMAT = pyaudio.paInt16
CHANNELS = 2 
RATE = 44100
CHUNK = 320 
BROADCAST_ADDR = '255.255.255.255'
PORT = 10000

from .system_audio import SystemAudioCapture

class AudioMaster:
    def __init__(self, group_name="DefaultGroup", device_index=None, capture_mode="pyaudio"):
        self.group_name = group_name
        self.p = pyaudio.PyAudio()
        self.device_index = device_index
        self.capture_mode = capture_mode 
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)
        self.running = False
        self.sequence = 0
        self.system_capture = None

    def _on_audio_data(self, data):
        """Callback from SystemAudioCapture (SCK Delegate)"""
        if not self.running: return
        header = struct.pack("!Id", self.sequence, time.time())
        try:
            self.sock.sendto(header + data, (BROADCAST_ADDR, PORT))
            self.sequence += 1
        except:
            pass

    def start(self):
        self.running = True
        
        if self.capture_mode == "system":
            # Direct push mode: SCK -> callback -> network
            self.system_capture = SystemAudioCapture(callback=self._on_audio_data)
            self.system_capture.start()
            console.print(f"[bold green]Master started.[/bold green] Broadcasting to network...")
            
            from PyObjCTools import AppHelper
            try: AppHelper.runConsoleEventLoop()
            except KeyboardInterrupt: self.stop()
        else:
            input_channels = CHANNELS
            if self.device_index is not None:
                info = self.p.get_device_info_by_index(self.device_index)
                input_channels = info['maxInputChannels']

            def mic_callback(in_data, frame_count, time_info, status):
                self._on_audio_data(in_data)
                return (None, pyaudio.paContinue)

            stream = self.p.open(format=FORMAT, channels=input_channels, rate=RATE, 
                                 input=True, input_device_index=self.device_index,
                                 frames_per_buffer=CHUNK, stream_callback=mic_callback)
            
            console.print(f"[bold green]Master started (Mic Mode).[/bold green]")
            stream.start_stream()
            while self.running and stream.is_active():
                time.sleep(0.1)
            stream.stop_stream()
            stream.close()

    def stop(self):
        self.running = False
        if self.system_capture: self.system_capture.stop()
        if self.p: self.p.terminate()
        from PyObjCTools import AppHelper
        try: AppHelper.stopEventLoop()
        except: pass

class AudioSlave:
    def __init__(self, port=PORT):
        self.port = port
        self.p = pyaudio.PyAudio()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
        self.sock.bind(('', self.port))
        self.running = False
        self.last_sequence = -1
        # PriorityQueue handles jitter and out-of-order delivery
        self.audio_buffer = queue.PriorityQueue(maxsize=200)

    def start(self):
        self.running = True
        
        # Audio callback for seamless playback
        def playback_callback(in_data, frame_count, time_info, status):
            try:
                # Try to get enough data for the frame_count
                # CHUNK is 320, 2 channels, 2 bytes = 1280 bytes
                seq, audio_data = self.audio_buffer.get_nowait()
                return (audio_data, pyaudio.paContinue)
            except:
                # Buffer empty - return silence
                return (b'\x00' * (frame_count * CHANNELS * 2), pyaudio.paContinue)

        stream = self.p.open(format=FORMAT, channels=CHANNELS, rate=RATE, 
                             output=True, frames_per_buffer=CHUNK,
                             stream_callback=playback_callback)
        
        console.print(f"[bold blue]Slave started.[/bold blue] Listening for broadcast...")
        
        def receiver():
            while self.running:
                try:
                    data_packet, addr = self.sock.recvfrom(4096)
                    header_size = struct.calcsize("!Id")
                    if len(data_packet) < header_size: continue
                    header = data_packet[:header_size]
                    audio_data = data_packet[header_size:]
                    seq, timestamp = struct.unpack("!Id", header)
                    
                    if seq > self.last_sequence:
                        try:
                            self.audio_buffer.put((seq, audio_data), block=False)
                        except queue.Full:
                            try: self.audio_buffer.get_nowait()
                            except: pass
                            self.audio_buffer.put((seq, audio_data), block=False)
                except: continue

        recv_thread = threading.Thread(target=receiver, daemon=True)
        recv_thread.start()
        
        stream.start_stream()
        while self.running and stream.is_active():
            time.sleep(0.1)
        stream.stop_stream()
        stream.close()

    def stop(self):
        self.running = False
        self.p.terminate()
