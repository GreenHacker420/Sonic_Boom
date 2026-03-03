# Sonic Boom CLI

A simple CLI tool to scan for speaker broadcasters (Google Cast, Sonos, AirPlay, Spotify Connect) in your local network and check their group sync status.

## Prerequisites

- Python 3.8+
- pip

## Installation

```bash
# Clone the repository (if applicable)
cd Sonic_Boom

# Install dependencies
python3 -m pip install .
```

## Usage

### Scan for speakers
```bash
sonic-boom scan
```

The tool will list all discovered speakers, including any active Sonic Boom Master nodes.

### Broadcast Audio (Master)
To start broadcasting audio from your microphone or system audio:
```bash
sonic-boom master --group MyParty
```
1.  The tool will list all available audio input devices.
2.  Select the index of the device you want to broadcast (e.g., your Microphone for voice, or a Loopback device for system audio).

#### **Broadcasting System Audio (macOS)**
macOS does not allow direct capture of system audio. To broadcast system audio (e.g., from Spotify or YouTube):
1.  **Install BlackHole:** `brew install blackhole-2ch`.
2.  **Audio MIDI Setup:** Create a **Multi-Output Device** in macOS "Audio MIDI Setup" containing both "BlackHole 2ch" and your "Built-in Output".
3.  **System Settings:** Set your system's sound output to this new **Multi-Output Device**.
4.  **Sonic Boom:** Run `sonic-boom master` and select the **BlackHole 2ch** index.

### Receive Audio (Slave)
To receive and play the audio broadcast on another device in the network:
```bash
sonic-boom slave
```
The slave will automatically join the multicast group and play the incoming stream.

### How it works (Master/Slave)
- **Master:** Captures audio using `PyAudio`, packs it with a sequence number and timestamp, and broadcasts it to `224.3.29.71:10000` via UDP Multicast.
- **Slave:** Listens on the multicast address, de-packets the audio, and uses a simple sequence-based sync logic to play the stream with minimal jitter.
