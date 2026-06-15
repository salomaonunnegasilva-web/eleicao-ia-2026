import re
import unicodedata


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents.lower()).strip()


def is_non_valid_vote_label(name: str) -> bool:
    normalized = normalize_text(name)
    return normalized in {
        "branco/nulo",
        "branco",
        "nulo",
        "nao sabe/indeciso",
        "indeciso",
        "nao sabe",
        "nulos/brancos",
    }
