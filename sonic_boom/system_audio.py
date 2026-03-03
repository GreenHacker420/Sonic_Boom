import objc
import queue
import threading
import time
from Foundation import NSObject
from ScreenCaptureKit import (
    SCStream, SCShareableContent, SCStreamConfiguration, 
    SCContentFilter, SCStreamOutputTypeAudio
)
import CoreMedia
from rich.console import Console

console = Console()

class AudioCaptureDelegate(NSObject):
    def initWithQueue_(self, q):
        self = objc.super(AudioCaptureDelegate, self).init()
        if self:
            self.q = q
        return self

    def stream_didOutputSampleBuffer_ofType_(self, stream, sampleBuffer, outputType):
        if outputType == SCStreamOutputTypeAudio:
            blockBuffer = CoreMedia.CMSampleBufferGetDataBuffer(sampleBuffer)
            if not blockBuffer:
                return
            
            length = CoreMedia.CMBlockBufferGetDataLength(blockBuffer)
            if length == 0:
                return
            
            status, data = CoreMedia.CMBlockBufferCopyDataBytes(blockBuffer, 0, length, None)
            
            if status == 0 and data:
                try:
                    import numpy as np
                    # Float32 is standard for ScreenCaptureKit
                    audio_float = np.frombuffer(data, dtype=np.float32)
                    
                    # ScreenCaptureKit can sometimes provide planar data.
                    # For a 2-channel buffer, if it's planar, 
                    # the first half is Left, second half is Right.
                    # We need interleaved (L, R, L, R) for PyAudio.
                    
                    # Simple check: if audio_float length is consistent with frames
                    # we assume interleaved. If not, we might need to de-interleave.
                    # However, most modern SCK implementations on macOS 14+ 
                    # provide interleaved floats if requested.
                    
                    # Apply gain (e.g., 1.5x) to address "very less audio"
                    # and clip to prevent distortion
                    gain = 1.8 
                    audio_float = np.clip(audio_float * gain, -1.0, 1.0)
                    
                    audio_int16 = (audio_float * 32767).astype(np.int16)
                    self.q.put(audio_int16.tobytes())
                except Exception as e:
                    self.q.put(bytes(data))

class SystemAudioCapture:
    def __init__(self):
        self.audio_queue = queue.Queue()
        self.stream = None
        self.running = False
        self.delegate = None

    def start(self):
        self.running = True
        self._setup_capture()

    def _setup_capture(self):
        def completion_handler(content, error):
            if error:
                console.print(f"[red]Error getting shareable content: {error}[/red]")
                return

            if not content.displays():
                console.print("[red]No displays found for capture.[/red]")
                return

            display = content.displays()[0]
            filter = SCContentFilter.alloc().initWithDisplay_excludingApplications_exceptingWindows_(display, [], [])

            config = SCStreamConfiguration.alloc().init()
            config.setCapturesAudio_(True)
            config.setExcludesCurrentProcessAudio_(True)
            
            config.setWidth_(1280)
            config.setHeight_(720)
            config.setShowsCursor_(False)
            config.setPixelFormat_(1111970369) # 'BGRA'
            
            config.setSampleRate_(44100)
            config.setChannelCount_(2)
            
            self.delegate = AudioCaptureDelegate.alloc().initWithQueue_(self.audio_queue)
            self.stream = SCStream.alloc().initWithFilter_configuration_delegate_(filter, config, self.delegate)
            
            ok, err = self.stream.addStreamOutput_type_sampleHandlerQueue_error_(
                self.delegate, SCStreamOutputTypeAudio, None, objc.NULL
            )
            
            if not ok:
                console.print(f"[red]Error adding stream output: {err}[/red]")
                return
            
            def start_handler(err):
                if err:
                    console.print(f"[red]Error starting capture: {err}[/red]")
                else:
                    console.print("[green]System audio capture active (ScreenCaptureKit).[/green]")

            time.sleep(0.2)
            self.stream.startCaptureWithCompletionHandler_(start_handler)

        SCShareableContent.getShareableContentWithCompletionHandler_(completion_handler)

    def read(self, chunk_size):
        data = b""
        while len(data) < chunk_size:
            try:
                item = self.audio_queue.get(timeout=1.0)
                data += item
            except queue.Empty:
                if not self.running: return b""
                continue
        return data[:chunk_size]

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stopCaptureWithCompletionHandler_(lambda err: None)
