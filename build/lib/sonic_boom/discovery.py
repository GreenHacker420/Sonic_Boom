from typing import List, Dict, Any, Optional
from zeroconf import Zeroconf, ServiceBrowser, ServiceListener, ServiceInfo
import time
import socket

class SpeakerListener(ServiceListener):
    def __init__(self):
        self.discovered_speakers = []

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            self.discovered_speakers.append(self._parse_info(info))

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            self.discovered_speakers.append(self._parse_info(info))

    def _parse_info(self, info: ServiceInfo) -> Dict[str, Any]:
        properties = {k.decode('utf-8') if isinstance(k, bytes) else k: 
                      v.decode('utf-8') if isinstance(v, bytes) else v 
                      for k, v in info.properties.items()}
        
        # Determine "Group" info based on common speaker protocols
        group_id = properties.get('md', 'None')  # Model/Group for Google Cast
        if 'group' in properties:
            group_id = properties['group']
        elif 'gid' in properties:
            group_id = properties['gid']

        return {
            'name': info.name,
            'server': info.server,
            'address': f"{'.'.join(map(str, info.addresses[0])) if info.addresses else 'unknown'}:{info.port}",
            'properties': properties,
            'group_id': group_id,
        }

def scan_speakers(timeout: int = 5) -> List[Dict[str, Any]]:
    zeroconf = Zeroconf()
    listener = SpeakerListener()
    
    # Common audio service types
    service_types = [
        "_googlecast._tcp.local.",
        "_spotify-connect._tcp.local.",
        "_airplay._tcp.local.",
        "_sonos._tcp.local.",
        "_sonicboom._udp.local.",
    ]
    
    browsers = [ServiceBrowser(zeroconf, st, listener) for st in service_types]
    
    time.sleep(timeout)
    zeroconf.close()
    
    return listener.discovered_speakers

def register_master_service(zc: Zeroconf, name: str, port: int, group: str) -> ServiceInfo:
    desc = {'group': group, 'type': 'sonic-boom-master'}
    # Use real IP for the master so slaves can find it
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    
    info = ServiceInfo(
        "_sonicboom._udp.local.",
        f"{name}._sonicboom._udp.local.",
        addresses=[socket.inet_aton(local_ip)],
        port=port,
        properties=desc,
        server=f"{hostname}.local.",
    )
    zc.register_service(info)
    return info
