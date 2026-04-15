import re
import logging
from faster_whisper import WhisperModel
from config import TRANSCRIPTION_HINT

log = logging.getLogger(__name__)

_FR_WORDS  = {'le','la','les','de','du','des','un','une','et','est','je','tu','il','elle','nous','vous','ils','elles','ce','se','au','aux','en','que','qui','pour','dans','sur','avec','par','mais','ou','si','mon','ma','mes','son','sa','ses','leur','leurs','pas','plus','très','bien','aussi','tout','tous','même','faire','avoir','être','ça','je','à'}
_EN_WORDS  = {'the','a','an','is','are','was','were','of','in','to','and','or','for','with','on','at','by','from','this','that','it','he','she','they','i','you','we','my','your','his','her','our','not','no','so','but','if','do','be','have','all','can','will','just','get','how','what','when','who'}
_MUSIC_CHARS = set('♪♫♬♩ \n\t')

whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
log.info("Whisper base model loaded")


def analyze_metadata_lang(text: str):
    words = set(re.findall(r"[a-zA-ZÀ-ÿ]+", text.lower()))
    fr = len(words & _FR_WORDS)
    en = len(words & _EN_WORDS)
    if fr == 0 and en == 0:
        return None
    return 'fr' if fr >= en else 'en'


def is_non_speech_content(text: str) -> bool:
    return all(c in _MUSIC_CHARS for c in text)
