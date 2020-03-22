import random
import ssl
import websockets
import asyncio
import os
import sys
import json
import argparse
import subprocess
import re
from .mqtt import daemon

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp

RPI_PIPELINE_DESC = '''
webrtcbin name=sendrecv bundle-policy=max-bundle
 rpicamsrc bitrate=5000000 do-timestamp=true preview=false ! video/x-h264,width=1024,height=768,framerate=30/1 ! h264parse ! 
 rtph264pay config-interval=1 pt=9 ! queue ! application/x-rtp,media=video,encoding-name=H264,payload=97 ! sendrecv. 
'''

PIPELINE_DESC = '''
tee name=t ! queue ! fakesink
 v4l2src device=/dev/video0 ! videoconvert ! queue ! vp8enc deadline=1 ! rtpvp8pay !
 queue ! application/x-rtp,media=video,encoding-name=VP8,payload=97 ! t.
'''
 # audiotestsrc is-live=true wave=red-noise ! audioconvert ! audioresample ! queue ! opusenc ! rtpopuspay !
 # queue ! application/x-rtp,media=audio,encoding-name=OPUS,payload=96 ! sendrecv.

JETSON_PIPELINE_DESC = '''
webrtcbin name=sendrecv bundle-policy=max-bundle
 nvarguscamerasrc ! video/x-raw(memory:NVMM), width=(int)1920, height=(int)1080, format=(string)NV12, framerate=(fraction)30/1 ! nvvidconv ! video/x-raw, width=640, height=480, format=NV12, framerate=30/1 ! videoconvert ! queue ! vp8enc deadline=1 ! rtpvp8pay !
 queue ! application/x-rtp,media=video,encoding-name=VP8,payload=97 ! sendrecv.
 audiotestsrc is-live=true wave=red-noise ! audioconvert ! audioresample ! queue ! opusenc ! rtpopuspay !
 queue ! application/x-rtp,media=audio,encoding-name=OPUS,payload=96 ! sendrecv.
'''


class WebRTCClient(daemon):
    def __init__(self, id_, room_id, server, pid, conf):
        super().__init__(pid, conf)
        self.id_ = id_
        self.conn = None
        self.pipe = None
        self.webrtc = dict()
        self.room_id = room_id
        self.server = server or 'wss://webrtc-signal-server-staging.app.psygig.com:443/'

    async def connect(self):
        sslctx = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)

        if self.server.startswith( 'wss' ):
            self.conn = await websockets.connect(self.server, ssl=sslctx)
        else:
            self.conn = await websockets.connect(self.server)

        await self.conn.send('HELLO %s' % self.id_)

    async def setup_call(self):
        await self.conn.send('ROOM {}'.format(self.room_id))

    def send_sdp_offer(self, offer, peer_id):
        text = offer.sdp.as_text()
        with open('webrtc.log', 'a+') as log:
            log.write('Sending offer:\n%s\n' % text)
        msg = json.dumps({'sdp': {'type': 'offer', 'sdp': text}})
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.conn.send('ROOM_PEER_MSG {} {}'.format(peer_id, msg)))

    def on_offer_created(self, promise, _, peer_id):
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value('offer')
        promise = Gst.Promise.new()
        self.webrtc[peer_id].emit('set-local-description', offer, promise)
        promise.interrupt()
        self.send_sdp_offer(offer, peer_id)

    def on_negotiation_needed(self, element, peer_id):
        promise = Gst.Promise.new_with_change_func(self.on_offer_created, element, peer_id)
        element.emit('create-offer', None, promise)

    def send_ice_candidate_message(self, _, mlineindex, candidate, peer_id):
        icemsg = json.dumps({'ice': {'candidate': candidate, 'sdpMLineIndex': mlineindex}})
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.conn.send('ROOM_PEER_MSG {} {}'.format(peer_id, icemsg)))

    def on_incoming_decodebin_stream(self, _, pad):
        if not pad.has_current_caps():
            print (pad, 'has no caps, ignoring')
            return

        caps = pad.get_current_caps()
        name = caps.to_string()
        if name.startswith('video'):
            q = Gst.ElementFactory.make('queue')
            conv = Gst.ElementFactory.make('videoconvert')
            sink = Gst.ElementFactory.make('autovideosink')
            self.pipe.add(q)
            self.pipe.add(conv)
            self.pipe.add(sink)
            self.pipe.sync_children_states()
            pad.link(q.get_static_pad('sink'))
            q.link(conv)
            conv.link(sink)
        elif name.startswith('audio'):
            q = Gst.ElementFactory.make('queue')
            conv = Gst.ElementFactory.make('audioconvert')
            resample = Gst.ElementFactory.make('audioresample')
            sink = Gst.ElementFactory.make('autoaudiosink')
            self.pipe.add(q)
            self.pipe.add(conv)
            self.pipe.add(resample)
            self.pipe.add(sink)
            self.pipe.sync_children_states()
            pad.link(q.get_static_pad('sink'))
            q.link(conv)
            conv.link(resample)
            resample.link(sink)

    def on_incoming_stream(self, _, pad):
        if pad.direction != Gst.PadDirection.SRC:
            return

        #decodebin = Gst.ElementFactory.make('decodebin')
        #decodebin.connect('pad-added', self.on_incoming_decodebin_stream)
        #self.pipe.add(decodebin)
        #decodebin.sync_state_with_parent()
        #self.webrtc.link(decodebin)

    def start_pipeline(self):
        # Check for jetson nano
        cmd = "cat /proc/device-tree/model"
        try:
            result = subprocess.check_output(cmd, shell=True)
            if result == 'jetson-nano' or result == b'NVIDIA Jetson Nano Developer Kit\x00':
                self.pipe = Gst.parse_launch(JETSON_PIPELINE_DESC)
            elif result.decode('utf-8').startswith('Raspberry Pi'):
                self.pipe = Gst.parse_launch(RPI_PIPELINE_DESC)
            else:
                self.pipe = Gst.parse_launch(PIPELINE_DESC)
        except subprocess.CalledProcessError:
            self.pipe = Gst.parse_launch(PIPELINE_DESC)
        # Start recording but not transmitting
        self.pipe.set_state(Gst.State.PLAYING)

    def add_peer_to_pipeline(self, peer_id):
        # Need separate webrtcbin per peer
        q = Gst.ElementFactory.make('queue', 'queue-{}'.format(peer_id))
        webrtc = Gst.ElementFactory.make('webrtcbin', peer_id)
        self.pipe.add(q)
        self.pipe.add(webrtc)
        srcpad = q.get_static_pad('src')
        sinkpad = webrtc.get_request_pad('sink_%u')
        ret = srcpad.link(sinkpad)
        tee = self.pipe.get_by_name('t')
        srcpad = tee.get_request_pad('src_%u')
        sinkpad = q.get_static_pad('sink')
        ret = srcpad.link(sinkpad)

        self.webrtc[peer_id] = self.pipe.get_by_name(peer_id)
        self.webrtc[peer_id].connect('on-negotiation-needed', self.on_negotiation_needed, peer_id)
        self.webrtc[peer_id].connect('on-ice-candidate', self.send_ice_candidate_message, peer_id)
        self.webrtc[peer_id].connect('pad-added', self.on_incoming_stream)
        ret = q.sync_state_with_parent()
        ret = webrtc.sync_state_with_parent()

    def remove_peer_from_pipeline(self, peer_id):
        webrtc = self.pipe.get_by_name(peer_id)
        self.pipe.remove(webrtc)
        self.webrtc.pop(peer_id)
        q = self.pipe.get_by_name('queue-{}'.format(peer_id))
        sinkpad = q.get_static_pad('sink')
        srcpad = sinkpad.get_peer()
        self.pipe.remove(q)
        tee = self.pipe.get_by_name('t')
        tee.release_request_pad(srcpad)

    async def handle_peer_msg(self, message, peer_id):
        assert (self.webrtc[peer_id])
        msg = json.loads(message)
        if 'sdp' in msg:
            sdp = msg['sdp']
            assert(sdp['type'] == 'answer')
            sdp = sdp['sdp']
            with open('webrtc.log', 'a+') as log:
                log.write('Received answer:\n%s\n' % sdp)
            res, sdpmsg = GstSdp.SDPMessage.new()
            GstSdp.sdp_message_parse_buffer(bytes(sdp.encode()), sdpmsg)
            answer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg)
            promise = Gst.Promise.new()
            self.webrtc[peer_id].emit('set-remote-description', answer, promise)
            promise.interrupt()
        elif 'ice' in msg:
            ice = msg['ice']
            candidate = ice['candidate']
            sdpmlineindex = ice['sdpMLineIndex']
            self.webrtc[peer_id].emit('add-ice-candidate', sdpmlineindex, candidate)

    async def loop(self):
        assert self.conn
        async for message in self.conn:
            if message == 'HELLO':
                await self.setup_call()
            elif message.startswith('ROOM_OK'):
                _, *peers = message.split()
                self.start_pipeline()
                if len(peers) > 0:
                    for peer_id in peers:
                        self.add_peer_to_pipeline(peer_id)
                        import time
                        time.sleep(3)
            elif message.startswith('ROOM_PEER'):
                if message.startswith('ROOM_PEER_JOINED'):
                    _, peer_id = message.split(maxsplit=1)
                    with open('webrtc.log', 'a+') as log:
                        log.write('Peer {!r} joined the room\n'.format(peer_id))
                    self.add_peer_to_pipeline(peer_id)
                elif message.startswith('ROOM_PEER_LEFT'):
                    _, peer_id = message.split(maxsplit=1)
                    with open('webrtc.log', 'a+') as log:
                        log.write('Peer {!r} left the room\n'.format(peer_id))
                    self.remove_peer_from_pipeline(peer_id)
                elif message.startswith('ROOM_PEER_MSG'):
                    _, peer_id, msg = message.split(maxsplit=2)
                    await self.handle_peer_msg(msg, peer_id)
            elif message.startswith('ERROR'):
                print (message)
                return 1
        return 0


def check_plugins():
    needed = ["opus", "vpx", "nice", "webrtc", "dtls", "srtp", "rtp",
              "rtpmanager", "videotestsrc", "audiotestsrc"]
    missing = list(filter(lambda p: Gst.Registry.get().find_plugin(p) is None, needed))
    if len(missing):
        print('Missing gstreamer plugins:', missing)
        return False
    return True


if __name__=='__main__':
    Gst.init(None)
    if not check_plugins():
        sys.exit(1)
    parser = argparse.ArgumentParser()
    parser.add_argument('peerid', help='String ID of the peer to connect to')
    parser.add_argument('--server', help='Signalling server to connect to, eg "wss://127.0.0.1:8443"')
    args = parser.parse_args()
    our_id = random.randrange(10, 10000)
    c = WebRTCClient(our_id, args.peerid, args.server)
    asyncio.get_event_loop().run_until_complete(c.connect())
    res = asyncio.get_event_loop().run_until_complete(c.loop())
    sys.exit(res)