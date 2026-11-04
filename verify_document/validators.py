"""Validatori e utilità di parsing per dati fiscali italiani.

- Codice fiscale persona fisica (16 caratteri, con gestione omocodia)
- Partita IVA (11 cifre, cifra di controllo tipo Luhn)
- Importi in formato italiano ("1.234,56") e date ("31/12/2025")
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# ---------------------------------------------------------------------------
# Codice fiscale
# ---------------------------------------------------------------------------

_CF_DISPARI = {
    **dict(zip("0123456789", [1, 0, 5, 7, 9, 13, 15, 17, 19, 21])),
    **dict(
        zip(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16,
             10, 22, 25, 24, 23],
        )
    ),
}
_CF_PARI = {
    **{c: i for i, c in enumerate("0123456789")},
    **{c: i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")},
}
_CF_MESI = "ABCDEHLMPRST"
_CF_OMOCODIA = "LMNPQRSTUV"  # sostituti delle cifre 0-9
_CF_POS_NUMERICHE = (6, 7, 9, 10, 12, 13, 14)

# Pattern "largo": tollera lettere al posto delle cifre (omocodia)
CF_REGEX = re.compile(
    r"\b[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}"
    r"[A-Z][0-9LMNPQRSTUV]{3}[A-Z]\b"
)
PIVA_REGEX = re.compile(r"(?<!\d)\d{11}(?!\d)")


def carattere_controllo_cf(primi15: str) -> str:
    totale = 0
    for i, c in enumerate(primi15.upper()):
        # posizioni 1,3,5... (1-based) = indici pari (0-based) -> tabella "dispari"
        totale += _CF_DISPARI[c] if i % 2 == 0 else _CF_PARI[c]
    return chr(ord("A") + totale % 26)


def _de_omocodia(cf: str) -> str:
    chars = list(cf)
    for p in _CF_POS_NUMERICHE:
        if chars[p] in _CF_OMOCODIA:
            chars[p] = str(_CF_OMOCODIA.index(chars[p]))
    return "".join(chars)


def valida_codice_fiscale(cf: str) -> bool:
    cf = (cf or "").strip().upper().replace(" ", "")
    if not CF_REGEX.fullmatch(cf):
        return False
    return carattere_controllo_cf(cf[:15]) == cf[15]


# Scambi tipici dell'OCR tra lettere e cifre
_OCR_A_CIFRA = {"O": "0", "D": "0", "Q": "0", "I": "1", "L": "1", "|": "1", "Z": "2", "S": "5",
                "G": "6", "T": "7", "B": "8"}
_OCR_A_LETTERA = {v: k for k, v in _OCR_A_CIFRA.items() if k not in ("D", "Q", "L", "|")}
_POSIZIONI_LETTERA = (0, 1, 2, 3, 4, 5, 8, 11, 15)


def _correggi_cf_ocr(candidato: str) -> str | None:
    """Corregge gli scambi lettera/cifra dell'OCR secondo la struttura del CF; valido solo se il controllo torna."""
    c = list(candidato.upper())
    if len(c) != 16:
        return None
    for i, ch in enumerate(c):
        if i in _POSIZIONI_LETTERA:
            c[i] = _OCR_A_LETTERA.get(ch, ch)
        elif ch not in "0123456789LMNPQRSTUV":  # posizioni numeriche (ammesse le lettere dell'omocodia)
            c[i] = _OCR_A_CIFRA.get(ch, ch)
    cf = "".join(c)
    return cf if valida_codice_fiscale(cf) else None


def trova_codici_fiscali(testo: str) -> list[str]:
    """Codici fiscali presenti nel testo (in ordine, senza doppioni).

    Prima quelli scritti correttamente (anche se con carattere di controllo errato, per segnalarlo);
    se non ce ne sono, quelli ricostruiti correggendo gli errori dell'OCR (O/0, I/1, S/5, B/8, ...),
    anche spezzati in due parole, accettati solo se il carattere di controllo è giusto.
    """
    alto = testo.upper()
    esatti = list(dict.fromkeys(m.group(0) for m in CF_REGEX.finditer(alto)))
    if esatti:
        return esatti
    parole = re.findall(r"[A-Z0-9|]+", alto)
    corretti = []
    for i, p in enumerate(parole):
        candidati = [p] if len(p) == 16 else []
        if i + 1 < len(parole) and len(p) + len(parole[i + 1]) == 16:
            candidati.append(p + parole[i + 1])  # CF spezzato dall'OCR
        for c in candidati:
            cf = _correggi_cf_ocr(c)
            if cf:
                corretti.append(cf)
    return list(dict.fromkeys(corretti))


@dataclass
class DatiCodiceFiscale:
    codice: str
    valido: bool
    sesso: str | None = None
    data_nascita: date | None = None
    codice_comune: str | None = None  # codice catastale (Belfiore), es. H501 = Roma


def decodifica_codice_fiscale(cf: str, riferimento: date | None = None) -> DatiCodiceFiscale:
    """Estrae sesso, data di nascita e codice comune dal codice fiscale."""
    cf = (cf or "").strip().upper().replace(" ", "")
    valido = valida_codice_fiscale(cf)
    if not valido:
        return DatiCodiceFiscale(cf, False)
    base = _de_omocodia(cf)
    anno2 = int(base[6:8])
    mese = _CF_MESI.index(base[8]) + 1
    giorno = int(base[9:11])
    sesso = "F" if giorno > 40 else "M"
    if giorno > 40:
        giorno -= 40
    oggi = riferimento or date.today()
    secolo = 2000 if 2000 + anno2 <= oggi.year else 1900
    try:
        nascita = date(secolo + anno2, mese, giorno)
    except ValueError:
        return DatiCodiceFiscale(cf, False)
    return DatiCodiceFiscale(cf, True, sesso, nascita, base[11:15])


_VOCALI = "AEIOU"


def _lettere(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFKD", s.upper())
    return "".join(c for c in s if "A" <= c <= "Z")


def codice_cognome(cognome: str) -> str:
    s = _lettere(cognome)
    cons = [c for c in s if c not in _VOCALI]
    voc = [c for c in s if c in _VOCALI]
    return ("".join(cons + voc) + "XXX")[:3]


def codice_nome(nome: str) -> str:
    s = _lettere(nome)
    cons = [c for c in s if c not in _VOCALI]
    voc = [c for c in s if c in _VOCALI]
    if len(cons) >= 4:
        return cons[0] + cons[2] + cons[3]
    return ("".join(cons + voc) + "XXX")[:3]


# ---------------------------------------------------------------------------
# Partita IVA
# ---------------------------------------------------------------------------

def valida_partita_iva(piva: str) -> bool:
    piva = re.sub(r"\s", "", piva or "")
    if piva.upper().startswith("IT"):
        piva = piva[2:]
    if not re.fullmatch(r"\d{11}", piva) or piva == "0" * 11:
        return False
    totale = 0
    for i, ch in enumerate(piva[:10]):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        totale += n
    return (10 - totale % 10) % 10 == int(piva[10])


# ---------------------------------------------------------------------------
# Importi e date
# ---------------------------------------------------------------------------

# Importo con decimali: 1.234,56 | 1234,56 | -12,00 | 1,234.56
IMPORTO_DECIMALI = r"-?\d{1,3}(?:[.\s']\d{3})+,\d{2}|-?\d+,\d{2}|-?\d{1,3}(?:,\d{3})+\.\d{2}"
# Importo anche intero (modelli fiscali spesso in euro senza centesimi)
IMPORTO_ANCHE_INTERO = IMPORTO_DECIMALI + r"|-?\d{1,3}(?:\.\d{3})+(?![\d,])|-?\d+(?![\d,.])"

_RE_DEC = re.compile(IMPORTO_DECIMALI)
_RE_INT = re.compile(IMPORTO_ANCHE_INTERO)


def parse_importo(s: str) -> Decimal | None:
    """Converte un importo testuale (formato italiano o inglese) in Decimal."""
    if s is None:
        return None
    s = s.strip().replace("€", "").replace("EUR", "").replace(" ", "").replace("'", "")
    if not s:
        return None
    negativo = s.endswith("-") or s.startswith("-")
    s = s.strip("-")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):  # 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:  # 1,234.56
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif "." in s:
        # "1.234" o "12.345.678" -> separatore migliaia italiano
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):
            s = s.replace(".", "")
    try:
        v = Decimal(s)
    except InvalidOperation:
        return None
    return -v if negativo else v


def trova_importi(testo: str, solo_decimali: bool = True) -> list[Decimal]:
    regex = _RE_DEC if solo_decimali else _RE_INT
    out = []
    for m in regex.finditer(testo):
        v = parse_importo(m.group(0))
        if v is not None:
            out.append(v)
    return out


_RE_DATA = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b")


def parse_data(s: str) -> date | None:
    m = _RE_DATA.search(s or "")
    if not m:
        return None
    g, me, a = (int(x) for x in m.groups())
    if a < 100:
        a += 2000 if a <= date.today().year % 100 else 1900
    try:
        return date(a, me, g)
    except ValueError:
        return None


def formatta_euro(v: Decimal | float | None) -> str:
    if v is None:
        return "n.d."
    s = f"{Decimal(v):,.2f}"  # 1,234.56
    return "€ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def oggi() -> date:
    return datetime.now().date()
