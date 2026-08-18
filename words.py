import re
import time
import requests
from difflib import get_close_matches
from typing import List, Tuple, Dict

_cache: Dict[str, bool] = {}

DICTIONARY_API = "https://api.dictionaryapi.dev/api/v2/entries/{lang}/{word}"
DATAMUSE_API = "https://api.datamuse.com/words"

REQUEST_TIMEOUT = 6
REQUEST_PAUSE = 0.15


def clean_username(username: str) -> str:
    return re.sub(r"[^a-z0-9]", "", username.lstrip("@").lower())


def _api_exists(word: str, lang: str) -> bool:
    if not word or len(word) < 2:
        return False

    cache_key = f"{lang}:{word}"
    if cache_key in _cache:
        return _cache[cache_key]

    url = DICTIONARY_API.format(lang=lang, word=word)
    try:
        time.sleep(REQUEST_PAUSE)
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        exists = r.status_code == 200 and isinstance(r.json(), list)
    except Exception:
        exists = False

    _cache[cache_key] = exists
    return exists


def is_exact_word(username: str) -> bool:
    word = clean_username(username)
    if not word or word.isdigit():
        return False
    return _api_exists(word, "en") or _api_exists(word, "pt")


def is_close_word(username: str, cutoff: float = 0.78) -> bool:
    word = clean_username(username)
    if not word or len(word) < 3 or word.isdigit():
        return False

    if is_exact_word(username):
        return True

    try:
        time.sleep(REQUEST_PAUSE)
        r = requests.get(
            DATAMUSE_API,
            params={"sp": word, "max": 5},
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            for item in data:
                candidate = item.get("word", "").lower()
                score = item.get("score", 0)
                if candidate == word or (score >= 1000 and abs(len(candidate) - len(word)) <= 2):
                    return True
                if get_close_matches(word, [candidate], n=1, cutoff=cutoff):
                    return True
    except Exception:
        pass

    return False


def filter_exact(items: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    return [i for i in items if is_exact_word(i[0])]


def filter_close(items: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    return [i for i in items if is_close_word(i[0])]


def filter_both(items: List[Tuple[str, str]]) -> dict:
    exact = []
    close = []
    for item in items:
        if is_exact_word(item[0]):
            exact.append(item)
        elif is_close_word(item[0]):
            close.append(item)
    return {"exatas": exact, "proximas": close}


def to_txt(items: List[Tuple[str, str]], with_price: bool = True) -> str:
    lines = []
    for user, price in items:
        if with_price and price:
            lines.append(f"{user}, {price}")
        else:
            lines.append(user)
    return "\n".join(lines)
