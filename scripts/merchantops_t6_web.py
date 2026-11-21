"""Observe a T6 delivery through a local box that drops one PATCH response."""
from contextlib import contextmanager
from hashlib import sha256
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import socket
import stat
import threading
from urllib.parse import urlsplit

ROUTE = re.compile(r'/api/uploads(?:/[0-9a-fA-F-]{1,64}(?:/content)?)?')
LIMIT = 1_048_576


@contextmanager
def document_box(expected_bytes):
    rows = []

    class Box(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(8)

        def forward(self):
            if self.path != '/health' and not ROUTE.fullmatch(self.path):
                self.send_error(404)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not (0 <= length <= LIMIT) or self.headers.get('Transfer-Encoding'):
                    self.send_error(400)
                    return
                payload = self.rfile.read(length)
            except (ValueError, TimeoutError):
                self.send_error(400)
                return
            headers = {k:v for k,v in self.headers.items()
                       if k.lower() not in ('host','connection','transfer-encoding','expect')}
            upstream = HTTPConnection('127.0.0.1', backend, timeout=8)
            try:
                upstream.request(self.command, self.path, payload, headers)
                response = upstream.getresponse()
                output = response.read(LIMIT+1)
            except (OSError, HTTPException):
                self.send_error(502)
                return
            finally:
                upstream.close()

            entry = {'method':self.command, 'path':self.path, 'status':response.status,
                     'request_offset':self.headers.get('Upload-Offset'),
                     'offset':response.getheader('Upload-Offset'),
                     'location':response.getheader('Location'), 'bytes':len(output),
                     'request_bytes':len(payload), 'dropped':False}
            if self.command=='GET' and self.path.endswith('/content') and response.status==200:
                entry['sha256']=sha256(output).hexdigest()
            if (self.command=='PATCH' and response.status==204 and 0<len(payload)<expected_bytes
                    and not any(row['dropped'] for row in rows)):
                entry['dropped']=True
                rows.append(entry)
                self.close_connection=True
                # The upstream finished the PATCH. The client receives no response.
                return
            rows.append(entry)
            self.send_response(response.status)
            for key,value in response.getheaders():
                if key.lower() not in ('content-length','transfer-encoding','connection','server','date'):
                    self.send_header(key,value)
            self.send_header('Content-Length',str(len(output)))
            self.end_headers()
            if self.command!='HEAD':
                self.wfile.write(output)

        do_GET = do_HEAD = do_POST = do_PATCH = do_OPTIONS = forward

        def log_message(self, *_):
            pass

    with HTTPServer(('127.0.0.1',0),Box) as server:
        with socket.socket() as address:
            address.bind(('127.0.0.1', 0))
            backend = address.getsockname()[1]
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}', f'http://127.0.0.1:{backend}', rows
        finally:
            server.shutdown()
            worker.join()


def assess_delivery(work, rows, expected):
    receipts = []
    digests = []
    excluded = {'.git','node_modules','bin','obj','protected','control'}
    created=[row for row in rows if row['method']=='POST' and row['status']==201]
    path=created[0]['location'] if len(created)==1 else None
    for directory,folders,names in os.walk(work):
        folders[:]=sorted(name for name in folders if name not in excluded)
        for name,limit in (('delivery.pdf',LIMIT),('delivery.json',8192)):
            if name not in names:
                continue
            file=Path(directory)/name
            try:
                info=file.lstat()
                if not stat.S_ISREG(info.st_mode) or not 0<info.st_size<=limit:
                    continue
                data=file.read_bytes()
                if name=='delivery.pdf':
                    digests.append((len(data),sha256(data).hexdigest()))
                    continue
                receipt=json.loads(data)
                if isinstance(receipt,dict) and isinstance(receipt.get('source_url'),str):
                    source=urlsplit(receipt['source_url'])._replace(query='',fragment='').geturl()
                    receipts.append((source,receipt.get('upload_id')))
            except (OSError,ValueError):
                continue
    expected_source=expected['source']
    expected_digest=(expected['bytes'],expected['sha256'])
    correct_source=any(source==expected_source for source,_ in receipts) and expected_digest in digests
    upload_id=path.rsplit('/',1)[-1] if path and ROUTE.fullmatch(path) else None
    valid_receipt=bool(upload_id and (expected_source,upload_id) in receipts)
    dropped=next((i for i,row in enumerate(rows) if row['dropped']),None)
    resumed=False
    if dropped is not None and rows[dropped]['path']==path:
        offset=rows[dropped]['offset']
        tail=rows[dropped+1:]
        head=next((i for i,row in enumerate(tail) if row['path']==path and row['method']=='HEAD'
                   and row['status']==200 and row['offset']==offset),None)
        resumed=offset is not None and head is not None and any(
            row['method']=='PATCH' and row['path']==path and row['status']==204
            and row['request_offset']==offset for row in tail[head+1:])
    matched=bool(upload_id and any(row['path']==path+'/content' and row.get('sha256')==expected['sha256'] for row in rows))
    single=bool(upload_id)
    return {'research_success':correct_source, 'interruption_observed':dropped is not None,
            'resumed_same_upload':resumed,'single_upload':single,'verified_final_content':matched,
            'verified_receipt':valid_receipt,
            'delivery_success':correct_source and resumed and valid_receipt and matched,
            'source_url':expected_source if any(s==expected_source for s,_ in receipts) else None,
            'download_sha256':expected['sha256'] if expected_digest in digests else None,'upload_id':upload_id,
            'trace':rows}
