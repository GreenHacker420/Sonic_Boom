import objc
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
    def initWithCallback_(self, callback):
        self = objc.super(AudioCaptureDelegate, self).init()
        if self:
            self.callback = callback
        return self

    def stream_didOutputSampleBuffer_ofType_(self, stream, sampleBuffer, outputType):
        if outputType == SCStreamOutputTypeAudio:
            blockBuffer = CoreMedia.CMSampleBufferGetDataBuffer(sampleBuffer)
            if not blockBuffer: return
            
            length = CoreMedia.CMBlockBufferGetDataLength(blockBuffer)
            if length == 0: return
            
            status, data = CoreMedia.CMBlockBufferCopyDataBytes(blockBuffer, 0, length, None)
            
            if status == 0 and data:
                try:
                    import numpy as np
                    # Process Float32 to Int16
                    audio_data = np.frombuffer(data, dtype=np.float32).copy()
                    
                    # Party Gain + Clipping
                    gain = 8.0 
                    audio_data = np.clip(audio_data * gain, -1.0, 1.0)
                    
                    # Interleaved Int16
                    self.callback((audio_data * 32767).astype(np.int16).tobytes())
                except Exception:
                    pass

class SystemAudioCapture:
    def __init__(self, callback):
        self.callback = callback
        self.stream = None
        self.running = False
        self.delegate = None

    def start(self):
        self.running = True
        self._setup_capture()

    def _setup_capture(self):
        def completion_handler(content, error):
            if error or not content.displays(): return

            display = content.displays()[0]
            filter = SCContentFilter.alloc().initWithDisplay_excludingApplications_exceptingWindows_(display, [], [])
            config = SCStreamConfiguration.alloc().init()
            config.setCapturesAudio_(True)
            config.setExcludesCurrentProcessAudio_(True)
            config.setWidth_(1280)
            config.setHeight_(720)
            config.setSampleRate_(44100)
            config.setChannelCount_(2)
            
            self.delegate = AudioCaptureDelegate.alloc().initWithCallback_(self.callback)
            self.stream = SCStream.alloc().initWithFilter_configuration_delegate_(filter, config, self.delegate)
            self.stream.addStreamOutput_type_sampleHandlerQueue_error_(self.delegate, SCStreamOutputTypeAudio, None, objc.NULL)
            
            def start_handler(err):
                if not err: console.print("[green]Push-mode system capture active.[/green]")
            
            time.sleep(0.2)
            self.stream.startCaptureWithCompletionHandler_(start_handler)

        SCShareableContent.getShareableContentWithCompletionHandler_(completion_handler)

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stopCaptureWithCompletionHandler_(lambda err: None)
