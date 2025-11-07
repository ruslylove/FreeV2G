import socket
import threading
import time
import queue
from FramingAPIDef import Frame, START_OF_FRAME, END_OF_FRAME
from SUTAdapter import SUTAdapter

class SocketAdapter(SUTAdapter):
    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.socket = None
        self.queue_rx = queue.Queue()
        self.stop_event = threading.Event()
        self.recv_thread = None
        self._connect()

    def _connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            print(f"[SocketAdapter] Connected to {self.host}:{self.port}")
            self.recv_thread = threading.Thread(target=self.process_receive)
            self.recv_thread.daemon = True
            self.recv_thread.start()
        except socket.error as e:
            print(f"[SocketAdapter] Connection failed: {e}")
            raise ConnectionError(f"Failed to connect to {self.host}:{self.port}") from e

    def send(self, data):
        if self.socket:
            try:
                self.socket.sendall(data)
            except socket.error as e:
                print(f"[SocketAdapter] Send failed: {e}")
                self.stop()

    def receive(self):
        try:
            return self.queue_rx.get_nowait()
        except queue.Empty:
            return None

    def process_receive(self):
        while not self.stop_event.is_set():
            try:
                data = self.socket.recv(4096)
                if not data:
                    print("[SocketAdapter] Connection closed by peer.")
                    break
                # The stub relays raw frames, so we need to parse them here.
                if data.startswith(b'\xc0') and data.endswith(b'\xc1'):
                     frame = self.pack_and_parse_frame(data)
                     self.queue_rx.put(frame)
            except socket.error:
                break
        self.stop()

    def stop(self):
        self.stop_event.set()
        if self.socket:
            self.socket.close()
            self.socket = None
        print("[SocketAdapter] Connection stopped.")

    def holding_data(self):
        return not self.queue_rx.empty()

    def clear_queues(self):
        while not self.queue_rx.empty():
            self.queue_rx.get_nowait()