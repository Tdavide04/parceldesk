"""One provider per carrier. Each module says which response shapes real fixtures confirm and which are assumed."""
from parceldesk.carriers.brt import Brt
from parceldesk.carriers.gls import Gls
from parceldesk.carriers.inpost import InPost
from parceldesk.carriers.japanpost import JapanPost
from parceldesk.carriers.mondialrelay import MondialRelay
from parceldesk.carriers.poste import PosteItaliane

ALL = (PosteItaliane, InPost, Gls, Brt, MondialRelay, JapanPost)

__all__ = ["ALL", "Brt", "Gls", "InPost", "JapanPost", "MondialRelay", "PosteItaliane"]
