"""A raw wire client for the harness: the join path of a real client (gateway TCP, then KCP to the
game server) without Unity, so a scenario can send what a real client never would (S16 malformed
input) and join and leave many times in a short run (S17 churn).

What it speaks, and where that comes from (rpg-mmo-server, all read at the commit under test):
- Frames: 4-byte big-endian length, then an Envelope body (`backend/shared/messages/codec.go`). The
  legacy JSON Envelope `{"type": N, "payload": {...}}` is used because it needs no protobuf runtime;
  the server sniffs the encoding per frame, so a deliberately broken protobuf body can still follow a
  JSON join on the same connection.
- Gateway hop: TCP, `MsgAuth` with a gateway JWT signed with the lab's `JWT_SECRET` (the "presigned"
  mode of backend/loadtest, the same token Nakama's gateway_token RPC mints), then `MsgEnterWorld`,
  which returns the game server address and a join token. `direct` mode mints the join token itself
  from `JOIN_TOKEN_SECRET` (loadtest `-join direct`) and skips the gateway, so no Redis session exists.
- Game hop: KCP over UDP, plaintext (the scratch stack sets no TRANSPORT_KEY): the 24-byte KCP
  segment header (conv, cmd, frg, wnd, ts, sn, una, len; little endian) of kcp-go v5, stream mode.
  The server's KCP listener opens a session on a PUSH with sn 0 (KcpListener.cs). This module is a
  minimal sender/receiver: in-order delivery, ACKs, retransmission with back-off. It is not a full
  KCP: no congestion control, no FEC, no encryption. It is enough for a session of a few frames per
  second.

Nothing here talks to a real Nakama, and nothing is imported from the Unity client.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import random
import socket
import struct
import threading
import time
import uuid

MAX_FRAME = 1 << 20   # WireProtocol.MaxMessageSize (1 MiB)
PROTOCOL_VERSION = 3  # wire protocol 3 (ADR-30); the server admits 2..3

# Envelope types (shared/messages/messages.go).
MSG_AUTH, MSG_AUTH_RESP, MSG_ENTER_WORLD, MSG_ENTER_WORLD_RESP = 1, 2, 3, 4
MSG_JOIN_TOKEN, MSG_JOIN_TOKEN_RESP, MSG_INPUT, MSG_SNAPSHOT = 5, 6, 7, 8
MSG_DISCONNECT, MSG_RESYNC, MSG_PING, MSG_PONG, MSG_KICK = 9, 10, 11, 12, 15

_KCP_HDR = struct.Struct("<IBBHIIII")
_PUSH, _ACK, _WASK, _WINS = 81, 82, 83, 84
_MSS = 1350 - _KCP_HDR.size   # KcpTuning.Mtu 1350, no crypto header
_RCV_WND = 128


class RawClientError(RuntimeError):
    pass


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def sign_jwt(user_id: str, secret: str, *, server_id: str | None = None, ttl_s: int = 3600) -> str:
    """HS256 JWT as backend/shared/jwt signs it: claims sub, iat, exp; a join token (server_id set)
    adds sid and a unique jti."""
    now = int(time.time())
    claims = {"sub": user_id, "iat": now, "exp": now + ttl_s}
    if server_id:
        claims["sid"] = server_id
        claims["jti"] = uuid.uuid4().hex
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(claims, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64(sig)}"


def frame(body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + body


def json_body(msg_type: int, payload: dict | None = None) -> bytes:
    return json.dumps({"type": msg_type, "payload": payload or {}}, separators=(",", ":")).encode()


# --------------------------------------------------------------------------- transports

class TcpLink:
    """The gateway hop."""

    def __init__(self, host: str, port: int, timeout: float = 10.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(0.2)
        self.closed = False

    def write(self, data: bytes) -> None:
        self.sock.sendall(data)

    def read_some(self, timeout: float) -> bytes | None:
        """Bytes read, b"" when nothing arrived in `timeout`, None when the peer closed."""
        self.sock.settimeout(max(0.01, timeout))
        try:
            data = self.sock.recv(65536)
        except socket.timeout:
            return b""
        except OSError:
            return None
        return data if data else None

    def close(self) -> None:
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass


class KcpLink:
    """The game hop: a minimal KCP-over-UDP endpoint (see the module docstring)."""

    def __init__(self, host: str, port: int, conv: int | None = None):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.connect(self.addr)
        self.sock.settimeout(0.01)
        self.conv = conv or random.getrandbits(32) or 1
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self._snd_nxt = 0
        self._snd: dict[int, list] = {}      # sn -> [data, next_send_mono, rto, xmit]
        self._rcv_nxt = 0
        self._rcv_buf: dict[int, bytes] = {}
        self._stream = bytearray()
        self._acks: list[tuple[int, int]] = []
        self._probe = False
        self.closed = False
        self.rx_datagrams = 0
        self.last_rx_mono: float | None = None
        self.retransmits = 0
        self._thread = threading.Thread(target=self._run, name="rawkcp", daemon=True)
        self._thread.start()

    # -- public ---------------------------------------------------------------
    def write(self, data: bytes) -> None:
        with self._lock:
            if self.closed:
                raise RawClientError("link closed")
            for i in range(0, len(data), _MSS):
                chunk = bytes(data[i:i + _MSS])
                self._snd[self._snd_nxt] = [chunk, 0.0, 0.1, 0]
                self._snd_nxt += 1
        self._flush()

    def read_some(self, timeout: float) -> bytes | None:
        with self._cv:
            if not self._stream and not self.closed:
                self._cv.wait(timeout)
            if self._stream:
                out = bytes(self._stream)
                self._stream.clear()
                return out
            return None if self.closed else b""

    def close(self) -> None:
        """Stop without any goodbye: KCP has no FIN, so this is what a killed process looks like to the server."""
        with self._cv:
            self.closed = True
            self._cv.notify_all()
        try:
            self.sock.close()
        except OSError:
            pass

    # -- internals ------------------------------------------------------------
    def _run(self) -> None:
        last_flush = 0.0
        while not self.closed:
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                data = None
            except OSError:
                # Windows reports ICMP port-unreachable of an earlier send as a reset on UDP.
                data = None
                if self.closed:
                    return
            if data:
                self._input(data)
            now = time.monotonic()
            if now - last_flush >= 0.01:
                last_flush = now
                self._flush()

    def _input(self, data: bytes) -> None:
        pos = 0
        with self._cv:
            self.rx_datagrams += 1
            self.last_rx_mono = time.monotonic()
            while len(data) - pos >= _KCP_HDR.size:
                conv, cmd, _frg, _wnd, ts, sn, una, ln = _KCP_HDR.unpack_from(data, pos)
                pos += _KCP_HDR.size
                if conv != self.conv or len(data) - pos < ln:
                    return
                payload = data[pos:pos + ln]
                pos += ln
                for k in [k for k in self._snd if k < una]:
                    del self._snd[k]
                if cmd == _ACK:
                    self._snd.pop(sn, None)
                elif cmd == _PUSH:
                    if sn < self._rcv_nxt + _RCV_WND:
                        self._acks.append((sn, ts))
                        if sn >= self._rcv_nxt and sn not in self._rcv_buf:
                            self._rcv_buf[sn] = payload
                            while self._rcv_nxt in self._rcv_buf:
                                self._stream += self._rcv_buf.pop(self._rcv_nxt)
                                self._rcv_nxt += 1
                            self._cv.notify_all()
                elif cmd == _WASK:
                    self._probe = True

    def _flush(self) -> None:
        now = time.monotonic()
        out = bytearray()
        with self._lock:
            if self.closed:
                return
            wnd = max(0, _RCV_WND - len(self._rcv_buf))
            ts_now = int(now * 1000) & 0xFFFFFFFF
            for sn, ts in self._acks:
                out += _KCP_HDR.pack(self.conv, _ACK, 0, wnd, ts, sn, self._rcv_nxt, 0)
            self._acks.clear()
            if self._probe:
                out += _KCP_HDR.pack(self.conv, _WINS, 0, wnd, ts_now, 0, self._rcv_nxt, 0)
                self._probe = False
            for sn in sorted(self._snd):
                seg = self._snd[sn]
                if now < seg[1]:
                    continue
                if seg[3]:
                    self.retransmits += 1
                    seg[2] = min(seg[2] * 1.5, 1.0)
                seg[3] += 1
                seg[1] = now + seg[2]
                out += _KCP_HDR.pack(self.conv, _PUSH, 0, wnd, ts_now, sn, self._rcv_nxt, len(seg[0])) + seg[0]
                if len(out) >= 1200:
                    self._send(bytes(out))
                    out.clear()
        if out:
            self._send(bytes(out))

    def _send(self, data: bytes) -> None:
        try:
            self.sock.send(data)
        except OSError:
            pass


# --------------------------------------------------------------------------- framed connection

class Wire:
    """Frames over a link: a reader thread decodes what arrives and answers heartbeats."""

    def __init__(self, link, name: str, answer_pings: bool = True):
        self.link, self.name, self.answer_pings = link, name, answer_pings
        self.frames: list[dict] = []          # decoded frames, oldest first (type, payload, t)
        self.type_counts: dict[int, int] = {}
        self.snapshot_times: list[float] = []
        self.pings_seen = 0
        self.bad_frame: str | None = None     # set when the incoming stream stopped parsing
        self.peer_closed = False
        self._buf = bytearray()
        self._cv = threading.Condition()
        self._stop = False
        self._thread = threading.Thread(target=self._run, name=f"raw-{name}", daemon=True)
        self._thread.start()

    def send(self, data: bytes) -> None:
        self.link.write(data)

    def send_msg(self, msg_type: int, payload: dict | None = None) -> None:
        self.send(frame(json_body(msg_type, payload)))

    def wait_for(self, msg_type: int, timeout: float) -> dict | None:
        deadline = time.monotonic() + timeout
        with self._cv:
            while True:
                for f in self.frames:
                    if f["type"] == msg_type and not f.get("taken"):
                        f["taken"] = True
                        return f
                left = deadline - time.monotonic()
                if left <= 0 or self.peer_closed:
                    return None
                self._cv.wait(min(left, 0.2))

    def stop(self) -> None:
        self._stop = True
        self.link.close()

    def _run(self) -> None:
        while not self._stop:
            data = self.link.read_some(0.2)
            if data is None:
                with self._cv:
                    self.peer_closed = True
                    self._cv.notify_all()
                return
            if data:
                self._buf += data
                self._parse()

    def _parse(self) -> None:
        while len(self._buf) >= 4:
            (ln,) = struct.unpack_from(">I", self._buf, 0)
            if ln == 0 or ln > MAX_FRAME:
                self.bad_frame = f"length {ln}"
                self._buf.clear()
                return
            if len(self._buf) < 4 + ln:
                return
            body = bytes(self._buf[4:4 + ln])
            del self._buf[:4 + ln]
            t = time.monotonic()
            try:
                env = json.loads(body) if body[:1] == b"{" else None
            except ValueError:
                env = None
            if env is None:
                self.bad_frame = "undecodable body"
                continue
            mtype = int(env.get("type", 0))
            payload = env.get("payload") or {}
            with self._cv:
                self.type_counts[mtype] = self.type_counts.get(mtype, 0) + 1
                if mtype == MSG_SNAPSHOT:
                    self.snapshot_times.append(t)
                else:
                    self.frames.append({"type": mtype, "payload": payload, "t": t})
                    if len(self.frames) > 256:
                        del self.frames[:128]
                self._cv.notify_all()
            if mtype == MSG_PING:
                self.pings_seen += 1
                if self.answer_pings:
                    try:
                        self.send_msg(MSG_PONG, {"timestamp": payload.get("timestamp", 0),
                                                 "server_time": int(time.time() * 1000)})
                    except (RawClientError, OSError):
                        pass


# --------------------------------------------------------------------------- one virtual player

class RawPlayer:
    """One user's connection to the scratch stack: gateway auth and enter-world (mode "gateway", the
    real client's path, which creates the Redis session) or a self-minted join token (mode "direct"),
    then the KCP join. `lab` holds `gateway` (host, port), `jwt_secret`, `join_secret`, `map_id`,
    `server_id` and, for direct mode, `game_addr`."""

    def __init__(self, lab: dict, user_id: str, mode: str = "gateway"):
        self.lab, self.user_id, self.mode = lab, user_id, mode
        self.gw: Wire | None = None
        self.game: Wire | None = None
        self.join: dict = {}
        self.tick = 0

    def connect(self, timeout: float = 15.0) -> dict:
        """Join the world. Returns {ok, error, phase, join_s, tick_rate}; never raises for a refusal."""
        t0 = time.monotonic()
        res = {"ok": False, "phase": "gateway", "error": None, "join_s": None, "tick_rate": None}
        try:
            if self.mode == "gateway":
                host, port = self.lab["gateway"]
                self.gw = Wire(TcpLink(host, port, timeout), f"gw-{self.user_id[-6:]}")
                self.gw.send_msg(MSG_AUTH, {"token": sign_jwt(self.user_id, self.lab["jwt_secret"]),
                                            "protocol_version": PROTOCOL_VERSION})
                auth = self.gw.wait_for(MSG_AUTH_RESP, timeout)
                if auth is None or not auth["payload"].get("ok"):
                    res["error"] = "gateway auth: " + json.dumps((auth or {}).get("payload", "no answer"))
                    return res
                self.gw.send_msg(MSG_ENTER_WORLD, {"map_id": self.lab["map_id"]})
                enter = self.gw.wait_for(MSG_ENTER_WORLD_RESP, timeout)
                p = (enter or {}).get("payload") or {}
                if not p.get("join_token") or p.get("error"):
                    res["error"] = "enter world: " + json.dumps(p or "no answer")
                    return res
                addr, token = p["server_addr"], p["join_token"]
            else:
                addr = self.lab["game_addr"]
                token = sign_jwt(self.user_id, self.lab["join_secret"], server_id=self.lab["server_id"], ttl_s=30)
            res["phase"] = "join"
            host, _, port = addr.rpartition(":")
            self.game = Wire(KcpLink(host or "127.0.0.1", int(port)), f"gs-{self.user_id[-6:]}")
            self.game.send_msg(MSG_JOIN_TOKEN, {"token": token, "protocol_version": PROTOCOL_VERSION})
            resp = self.game.wait_for(MSG_JOIN_TOKEN_RESP, timeout)
            payload = (resp or {}).get("payload") or {}
            self.join = payload
            if not payload.get("ok"):
                res["error"] = "join: " + json.dumps(payload or "no answer")
                return res
            res.update(ok=True, phase="in_world", join_s=round(time.monotonic() - t0, 3),
                       tick_rate=payload.get("tick_rate"))
            return res
        except (OSError, RawClientError) as exc:
            res["error"] = f"{type(exc).__name__}: {exc}"
            return res

    # -- what a player sends --------------------------------------------------
    def send_input(self, move_x: float = 0.0, move_y: float = 0.0, **extra) -> None:
        self.tick += 1
        payload = {"tick": self.tick, "move_x": move_x, "move_y": move_y}
        payload.update(extra)
        self.game.send_msg(MSG_INPUT, payload)

    def snapshots(self) -> int:
        return len(self.game.snapshot_times) if self.game else 0

    # -- how it ends ----------------------------------------------------------
    def leave(self) -> None:
        """The game's own way out: MsgDisconnect on the game hop (the server releases the entity at once), then close."""
        try:
            if self.game is not None:
                self.game.send_msg(MSG_DISCONNECT, {})
                time.sleep(0.15)
        except (RawClientError, OSError):
            pass
        self.drop()

    def drop(self) -> None:
        """Kill the link without a goodbye, as a crashed process does: both sockets are closed with no
        MsgDisconnect (the gateway sees the TCP close, the game server sees nothing)."""
        for w in (self.game, self.gw):
            if w is not None:
                w.stop()


def random_bytes(n: int, seed: int) -> bytes:
    """Reproducible noise (a scenario seed), never os.urandom: a failure must be replayable."""
    rng = random.Random(seed)
    return bytes(rng.getrandbits(8) for _ in range(n))
