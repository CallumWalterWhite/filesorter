import json
from service.config import PORT
from service.file_watcher import FileWatcher
import socket
import threading
from multiprocessing import Process
from service.model import TagPath, Logs, db
from service.file_tag_mover import FileMover

class FileWatcherClient:
    def __init__(self):
        self._port = PORT
        self._fileWatchers = []
        self._setup_database()
        self._started = False

    def _setup_database(self):
        db.connect()
        db.create_tables([TagPath, Logs])

    def _init_watchers(self):
        self._tag_paths = TagPath.select()
        self.refresh_w = True
        for tag_path in self._tag_paths:
            self.add_watcher(tag_path.sourcepath, tag_path.tags, tag_path.targetpath, tag_path.id, self._log)

    def _start_tcp_server(self):
        self._tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._tcp_socket.bind(('', self._port))
        self._tcp_socket.listen(5)
        print(f"TCP server started at port {self._port}")
        while True:
            client_socket, addr = self._tcp_socket.accept()
            print(f"Accepted connection from {addr[0]}:{addr[1]}")
            client_handler = threading.Thread(target=self._handle_tcp_requests, args=(client_socket,))
            client_handler.start()
    
    def _stop_tcp_server(self):
        self._tcp_socket.close()

    def _handle_tcp_requests(self, client_socket):
        request = client_socket.recv(1024)
        request_body = request.decode('utf-8')
        print(f"Received request: {request_body}")
        request_command = json.loads(request_body)
        self._handle_client_command(request_command)
        client_socket.send(''.encode('utf-8'))
        client_socket.close()
        
    def _handle_client_command(self, request_command):
        try:
            if request_command['command'] == 'trigger':
                source_path = request_command['body']['source_path']
                tags = request_command['body']['tags']
                target_path = request_command['body']['target_path']
                file_mover = FileMover(source_path, tags, target_path)
                file_mover.move_files_by_tags()
            elif request_command['command'] == 'refresh':
                self._tag_paths = TagPath.select()
                self.refresh_w = True
                self.refresh_watches(request_command['body']['refresh_ids'])
            else:
                print('Unknown command sent')
        except Exception as error:  
            print(error) #ignore exception
            #TODO: return exception to tcp

    def add_watcher(self, source, tags, target, meta_id=None, callback=None):
        self._fileWatchers.append(FileWatcher(source, tags, target, meta_id, callback))
        
    def refresh_watches(self, refresh_ids=[]):
        if self.refresh_w == True:
            print('Refreshing watches')
            for tagpath in self._tag_paths:
                id = tagpath.id
                if len(list(filter(lambda x: x.meta_id == id, self.watches))) == 0:
                    self.add_watcher(tagpath.sourcepath, tagpath.tags, tagpath.targetpath, tagpath.meta_id, callback=self.watcher_callback)
                    print('New watcher added')
                elif id in refresh_ids and len(list(filter(lambda x: x.meta_id == id, self.watches))) == 1:
                    list(filter(lambda x: x.meta_id == id, self.watches))[0].stop()
                    self.add_watcher(tagpath.sourcepath, tagpath.tags, tagpath.targetpath, tagpath.meta_id, callback=self.watcher_callback)
                    print('Watcher updated')
            self.refresh_w = False

    def stop(self):
        for fileWatcher in self._fileWatchers:
            fileWatcher.stop()
        self._stop_tcp_server()
        self._started = False

    def start(self):
        if self._started == False:
            self._started = True
            self._init_watchers()
            self._start_tcp_server()

    def _log(self, log):
        Logs.create(log=log)
        print(log)
