"""Mesh-SOS message format + Ed25519 signing."""
import json, time, uuid, base64, os
from dataclasses import dataclass, field, asdict
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

PRIORITY = {"SOS": 3, "INFO": 1, "ACK": 2}

def _b64(b): return base64.b64encode(b).decode()
def _ub64(s): return base64.b64decode(s.encode())

class Identity:
    """Per-node Ed25519 keypair, stored in a file so the node id is stable."""
    def __init__(self, path):
        if os.path.exists(path):
            with open(path, "rb") as f:
                self.sk = serialization.load_pem_private_key(f.read(), None)
        else:
            self.sk = Ed25519PrivateKey.generate()
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "wb") as f:
                f.write(self.sk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
        self.pub = _b64(self.sk.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))

    def sign(self, data: bytes) -> str:
        return _b64(self.sk.sign(data))

@dataclass
class Message:
    origin: str                 # origin node name
    type: str = "SOS"           # SOS / INFO / ACK
    text: str = ""
    lat: float = None
    lon: float = None
    urgency: int = 3            # 1..5 (people injured, water level...)
    people: int = 1
    ttl: int = 6 * 3600         # seconds of life
    created: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    pubkey: str = ""
    sig: str = ""
    hops: list = field(default_factory=list)   # not signed (changes en route)
    acks: str = ""             # for ACK: id of acknowledged message

    @property
    def priority(self):
        return PRIORITY.get(self.type, 1) * 10 + int(self.urgency or 0)

    def signed_bytes(self):
        d = asdict(self); d.pop("sig"); d.pop("hops")
        return json.dumps(d, sort_keys=True, separators=(",", ":")).encode()

    def sign(self, ident: Identity):
        self.pubkey = ident.pub
        self.sig = ident.sign(self.signed_bytes())
        return self

    def verify(self) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(_ub64(self.pubkey)).verify(_ub64(self.sig), self.signed_bytes())
            return True
        except Exception:
            return False

    def expired(self, now=None):
        return (now or time.time()) > self.created + self.ttl

    def to_dict(self): return asdict(self)

    @classmethod
    def from_dict(cls, d):
        keys = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in keys})
