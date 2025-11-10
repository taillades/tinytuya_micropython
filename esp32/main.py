import network
import time
import socket
import json
import struct
from machine import Pin
from binascii import crc32
try:
    from Crypto.Cipher import AES
    USING_UCRYPTOLIB = False
except ImportError:
    import ucryptolib
    USING_UCRYPTOLIB = True

try:
    import uhashlib as hashlib
except ImportError:
    import hashlib

def hmac_sha256(key, msg):
    """
    Manual HMAC-SHA256 implementation for MicroPython.
    """
    block_size = 64
    
    if len(key) > block_size:
        key = hashlib.sha256(key).digest()
    if len(key) < block_size:
        key = key + b'\x00' * (block_size - len(key))
    
    o_key_pad = bytes([k ^ 0x5c for k in key])
    i_key_pad = bytes([k ^ 0x36 for k in key])
    
    inner = hashlib.sha256(i_key_pad + msg).digest()
    return hashlib.sha256(o_key_pad + inner).digest()


class TuyaDevice:
    def __init__(self, device_id, ip, local_key, version=3.3):
        self.device_id = device_id
        self.ip = ip
        self.real_local_key = local_key.encode('utf-8') if isinstance(local_key, str) else local_key
        self.local_key = self.real_local_key
        self.version = version
        self.socket = None
        self.seq = 0
        self.session_key = None
        self.local_nonce = None
        self.remote_nonce = None
        
    def _pad(self, data):
        pad_len = 16 - (len(data) % 16)
        return data + bytes([pad_len] * pad_len)
    
    def _unpad(self, data):
        return data[:-data[-1]]
    
    def _encrypt(self, data):
        padded_data = self._pad(data)
        if USING_UCRYPTOLIB:
            cipher = ucryptolib.aes(self.local_key, 1)
            return cipher.encrypt(padded_data)
        else:
            cipher = AES.new(self.local_key, AES.MODE_ECB)
            return cipher.encrypt(padded_data)
    
    def _decrypt(self, data):
        if USING_UCRYPTOLIB:
            cipher = ucryptolib.aes(self.local_key, 1)
            decrypted = cipher.decrypt(data)
            return self._unpad(decrypted)
        else:
            cipher = AES.new(self.local_key, AES.MODE_ECB)
            decrypted = cipher.decrypt(data)
            return self._unpad(decrypted)
    
    def _build_payload(self, command, data):
        NO_PROTOCOL_HEADER_CMDS = [10, 16, 18, 9, 3, 4, 5, 64]
        
        self.seq += 1
        
        if command == 3:
            json_data = self.local_nonce
        elif command == 5:
            json_data = hmac_sha256(self.real_local_key, self.remote_nonce)
        elif data:
            json_data = json.dumps(data).encode('utf-8')
        else:
            json_data = b'{}'
        
        if self.version >= 3.4:
            if command not in NO_PROTOCOL_HEADER_CMDS:
                version_header = b'3.4' + (12 * b'\x00')
                json_data = version_header + json_data
            json_data = self._encrypt(json_data)
        elif self.version >= 3.3:
            json_data = self._encrypt(json_data)
            if command not in NO_PROTOCOL_HEADER_CMDS:
                version_header = b'3.3' + (12 * b'\x00')
                json_data = version_header + json_data
        
        prefix = b'\x00\x00\x55\xaa'
        suffix = b'\x00\x00\xaa\x55'
        seq_no = self.seq.to_bytes(4, 'big')
        cmd = command.to_bytes(4, 'big')
        
        if self.version >= 3.4:
            length = len(json_data) + 36
        else:
            length = len(json_data) + 8
        
        payload = prefix + seq_no + cmd + length.to_bytes(4, 'big')
        payload += json_data
        
        if self.version >= 3.4:
            crc_val = hmac_sha256(self.local_key, payload)
        else:
            crc_data = payload[len(prefix):]
            crc_val = (crc32(crc_data) & 0xFFFFFFFF).to_bytes(4, 'big')
        
        payload += crc_val
        payload += suffix
        
        return payload
    
    def _parse_response(self, data):
        if len(data) < 20:
            return {"error": "Response too short"}
        
        payload_len = struct.unpack('>I', data[12:16])[0]
        retcode = struct.unpack('>I', data[16:20])[0]
        suffix_len = 36 if self.version >= 3.4 else 8
        
        try:
            payload = data[20:16+payload_len-suffix_len]
        except Exception as e:
            return {"error": "Extraction failed: " + str(e)}
        
        # Check for empty payload (acknowledgment) and look for second packet
        if len(payload) == 0:
            first_packet_len = 16 + payload_len
            if len(data) > first_packet_len + 28:
                return self._parse_response(data[first_packet_len:])
            return {"success": True, "retcode": retcode}
        
        # Decrypt payload
        if self.version >= 3.4:
            try:
                payload = self._decrypt(payload)
            except Exception as e:
                return {"error": "Decryption failed: " + str(e)}
            
            # Strip version header and null bytes
            if payload.startswith(b'3.4'):
                payload = payload[3:]
                while len(payload) > 0 and payload[0:1] == b'\x00':
                    payload = payload[1:]
                while len(payload) > 0 and payload[0:1] != b'{':
                    payload = payload[1:]
        elif self.version >= 3.3:
            version_header = b'3.3' + (12 * b'\x00')
            if payload.startswith(version_header):
                payload = payload[15:]
            try:
                payload = self._decrypt(payload)
            except Exception as e:
                return {"error": "Decryption failed: " + str(e)}
        
        # Parse JSON
        try:
            return json.loads(payload.decode('utf-8'))
        except Exception as e:
            return {"error": "JSON parse failed: " + str(e)}
    
    def _negotiate_session_key(self):
        if self.version < 3.4:
            return True
        
        print("[*] Starting session key negotiation...")
        
        self.local_nonce = b'0123456789abcdef'
        
        print("[*] Step 1: Sending local nonce...")
        payload = self._build_payload(3, {})
        
        try:
            self.socket.send(payload)
            response = self._receive_response()
            if not response or len(response) < 28:
                print("[!] Step 1 failed: no response")
                return False
            
            cmd = struct.unpack('>I', response[8:12])[0]
            if cmd != 4:
                print("[!] Step 1 failed: expected command 4, got", cmd)
                return False
            
            print("[*] Step 2: Extracting remote nonce...")
            payload_len = struct.unpack('>I', response[12:16])[0]
            encrypted_payload = response[20:16+payload_len-36]
            
            decrypted = self._decrypt(encrypted_payload)
            
            if len(decrypted) < 48:
                print("[!] Step 2 failed: payload too short")
                return False
            
            self.remote_nonce = decrypted[:16]
            received_hmac = decrypted[16:48]
            
            expected_hmac = hmac_sha256(self.real_local_key, self.local_nonce)
            if received_hmac != expected_hmac:
                print("[!] Step 2 HMAC check failed!")
                return False
            
            print("[*] Step 3: Sending HMAC verification...")
            payload = self._build_payload(5, {})
            self.socket.send(payload)
            
            session_key_bytes = bytes([a ^ b for a, b in zip(self.local_nonce, self.remote_nonce)])
            self.session_key = self._encrypt(session_key_bytes)[:16]
            self.local_key = self.session_key
            
            print("[*] Session key negotiated!")
            return True
            
        except Exception as e:
            print("[!] Session key negotiation failed:", e)
            return False
    
    def _receive_response(self):
        try:
            self.socket.settimeout(5)
            response = b''
            chunk = self.socket.recv(1024)
            if not chunk:
                return response
            response += chunk
            
            if len(response) >= 16:
                payload_len = struct.unpack('>I', response[12:16])[0]
                expected_len = 16 + payload_len
                
                while len(response) < expected_len:
                    chunk = self.socket.recv(1024)
                    if not chunk:
                        break
                    response += chunk
        except Exception as e:
            print("[!] Receive error:", e)
        return response
    
    def connect(self):
        try:
            print("[*] Connecting to", self.ip)
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((self.ip, 6668))
            print("[*] Connected!")
            
            if self.version >= 3.4:
                if not self._negotiate_session_key():
                    print("[!] Session key negotiation failed")
                    self.disconnect()
                    return False
            
            return True
        except Exception as e:
            print("[!] Connection failed:", e)
            return False
    
    def disconnect(self):
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        
        self.session_key = None
        self.local_key = self.real_local_key
        self.local_nonce = None
        self.remote_nonce = None
        self.seq = 0
    
    def status(self):
        if not self.socket and not self.connect():
            return None
        
        try:
            if self.version >= 3.4:
                command = 16
                data = {}
            else:
                command = 10
                data = {"gwId": self.device_id, "devId": self.device_id}
            
            payload = self._build_payload(command, data)
            self.socket.send(payload)
            response = self._receive_response()
            
            if response:
                result = self._parse_response(response)
                if "error" not in result and "dps" in result:
                    return result.get("dps", {}).get("1", None)
                elif "data" in result:
                    return result.get("data", {}).get("dps", {}).get("1", None)
        except Exception as e:
            print("[!] Status error:", e)
        
        return None
    
    def toggle(self):
        if not self.socket and not self.connect():
            return False
        
        try:
            current_state = self.status()
            new_state = True if current_state is None else not current_state
            
            if self.version >= 3.4:
                command = 13
                data = {
                    "protocol": 5,
                    "t": int(time.time()),
                    "data": {"dps": {"1": new_state}}
                }
            else:
                command = 7
                data = {
                    "devId": self.device_id,
                    "gwId": self.device_id,
                    "uid": "",
                    "t": str(int(time.time())),
                    "dps": {"1": new_state}
                }
            
            payload = self._build_payload(command, data)
            self.socket.send(payload)
            response = self._receive_response()
            
            if response:
                result = self._parse_response(response)
                return "error" not in result
            return False
        except Exception as e:
            print("[!] Toggle error:", e)
            self.disconnect()
            return False


def load_config(filename='config.json'):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except Exception as e:
        print("[!] Error loading config:", e)
        return None


def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("[*] Connecting to WiFi:", ssid)
        wlan.connect(ssid, password)
        timeout = 20
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
        if not wlan.isconnected():
            print("[!] WiFi connection failed!")
            return False
    print("[*] WiFi connected:", wlan.ifconfig()[0])
    return True


def toggle_all_devices(devices):
    """
    Toggle all devices. If not all in same state, turn all ON.
    """
    print("[*] Checking all device states...")
    states = []
    
    # Get state of all devices
    for dev_info in devices:
        if not dev_info['device'].socket:
            if not dev_info['device'].connect():
                print(f"[!] Failed to connect to {dev_info['name']}")
                states.append(None)
                continue
        
        state = dev_info['device'].status()
        states.append(state)
        print(f"[*] {dev_info['name']}: {'ON' if state else 'OFF' if state is not None else 'UNKNOWN'}")
    
    # Determine target state
    valid_states = [s for s in states if s is not None]
    if not valid_states:
        print("[!] No devices responded, aborting")
        return False
    
    # If not all same state, turn all ON
    if len(set(valid_states)) > 1:
        target_state = True
        print("[*] Mixed states detected, turning all ON")
    else:
        target_state = not valid_states[0]
        print(f"[*] All in same state, toggling to {'ON' if target_state else 'OFF'}")
    
    # Set all devices to target state
    success_count = 0
    for dev_info in devices:
        if not dev_info['device'].socket:
            continue
        
        try:
            command = 13 if dev_info['device'].version >= 3.4 else 7
            if dev_info['device'].version >= 3.4:
                data = {
                    "protocol": 5,
                    "t": int(time.time()),
                    "data": {"dps": {"1": target_state}}
                }
            else:
                data = {
                    "devId": dev_info['device'].device_id,
                    "gwId": dev_info['device'].device_id,
                    "uid": "",
                    "t": str(int(time.time())),
                    "dps": {"1": target_state}
                }
            
            payload = dev_info['device']._build_payload(command, data)
            dev_info['device'].socket.send(payload)
            response = dev_info['device']._receive_response()
            
            if response:
                result = dev_info['device']._parse_response(response)
                if "error" not in result:
                    print(f"[*] {dev_info['name']}: OK")
                    success_count += 1
                else:
                    print(f"[!] {dev_info['name']}: {result.get('error')}")
            else:
                print(f"[!] {dev_info['name']}: No response")
        except Exception as e:
            print(f"[!] {dev_info['name']}: {e}")
            dev_info['device'].disconnect()
    
    return success_count > 0


def main():
    print("="*50)
    print("ESP32 Tuya Button Controller")
    print("="*50)
    
    # Load configuration
    config = load_config()
    if not config:
        print("[!] Failed to load config, exiting")
        return
    
    # Connect to WiFi
    if not connect_wifi(config['wifi']['ssid'], config['wifi']['password']):
        return
    
    # Create device instances (skip devices without keys)
    devices = []
    for dev_cfg in config['devices']:
        # Skip devices without a key
        if not dev_cfg.get('key'):
            continue
        
        # Convert "ver" to protocol float (e.g., "3.4" -> 3.4)
        protocol = float(dev_cfg.get('ver', '3.3'))
        
        device = TuyaDevice(
            dev_cfg['id'],
            dev_cfg['ip'],
            dev_cfg['key'],
            protocol
        )
        devices.append({
            'device': device,
            'name': dev_cfg.get('name', dev_cfg['id'])
        })
    
    print(f"[*] Loaded {len(devices)} device(s)")
    for dev_info in devices:
        print(f"    - {dev_info['name']}")
    
    # Setup button
    button_cfg = config['button']
    button = Pin(button_cfg['pin'], Pin.IN, Pin.PULL_UP)
    debounce_ms = button_cfg['debounce_ms']
    press_time_ms = button_cfg['press_time_ms']
    
    last_press = 0
    button_was_pressed = False
    press_start_time = 0
    
    print(f"[*] Ready! Press button on GPIO {button_cfg['pin']}")
    print(f"[*] Button must be held for {press_time_ms}ms to trigger")
    print("[*] Waiting for button press...")
    
    while True:
        button_state = button.value()
        current_time = time.ticks_ms()
        
        if button_state == 0 and not button_was_pressed:
            if time.ticks_diff(current_time, last_press) > debounce_ms:
                if press_start_time == 0:
                    press_start_time = current_time
                
                if time.ticks_diff(current_time, press_start_time) >= press_time_ms:
                    print(f"\n[*] Button press confirmed!")
                    button_was_pressed = True
                    last_press = current_time
                    press_start_time = 0
                    
                    if toggle_all_devices(devices):
                        print("[*] Toggle operation completed!")
                    else:
                        print("[!] Toggle operation failed!")
                    
                    # Wait for button release
                    while button.value() == 0:
                        time.sleep(0.01)
                    
                    print("[*] Ready for next press")
        
        elif button_state == 1:
            button_was_pressed = False
            press_start_time = 0
        
        time.sleep(0.01)


if __name__ == "__main__":
    main()
