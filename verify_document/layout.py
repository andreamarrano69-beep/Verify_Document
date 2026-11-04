"""Parole con la loro posizione sulla pagina e ricerca "etichetta → valore" per posizione.

Nelle buste paga reali i valori stanno spesso SOTTO l'etichetta, in colonne affiancate:

    TOTALE COMPETENZE   TOTALE TRATTENUTE   NETTO DEL MESE
         2.150,00            517,74            1.632,00

Cercando nel testo "il primo numero dopo l'etichetta" si sbaglia colonna. Qui invece, per ogni etichetta,
si cerca il valore nella stessa riga (subito a destra) oppure nella cella sotto, cioè nella fascia
orizzontale compresa tra l'inizio dell'etichetta e l'inizio del campo successivo sulla stessa riga.

Le parole arrivano da pdfplumber (PDF con testo) o da Tesseract (scansioni); durante l'analisi di un
documento sono disponibili tramite ``contesto_parole`` e vengono usate da ``report.cerca_importo``.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from statistics import median


@dataclass
class Parola:
    testo: str
    x0: float
    x1: float
    top: float
    bottom: float
    ocr: bool = False  # letta con l'OCR (scansione/foto)

    @property
    def altezza(self) -> float:
        return max(self.bottom - self.top, 1.0)

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2


_PAROLE: ContextVar[list[Parola] | None] = ContextVar("parole_documento", default=None)


@contextmanager
def contesto_parole(parole: list[Parola] | None):
    token = _PAROLE.set(parole or None)
    try:
        yield
    finally:
        _PAROLE.reset(token)


def parole_correnti() -> list[Parola] | None:
    return _PAROLE.get()


def testo_da_ocr() -> bool:
    """Vero se il documento in analisi è stato letto (anche in parte) con l'OCR."""
    return any(p.ocr for p in (_PAROLE.get() or []))


def cf_corretto_ocr(cf: str | None, nominativo: str | None = None) -> tuple[str | None, str | None]:
    """Nei documenti letti con l'OCR corregge un CF con un carattere letto male. Restituisce (cf, nota)."""
    from .validators import correggi_cf_letto, valida_codice_fiscale

    if not cf or valida_codice_fiscale(cf) or not testo_da_ocr():
        return cf, None
    corretto = correggi_cf_letto(cf, nominativo)
    if corretto is None:
        return cf, None
    diversi = ", ".join(f"«{a}»→«{b}» (posizione {i + 1})" for i, (a, b) in enumerate(zip(cf, corretto)) if a != b)
    controllo = " e coerente con nome e cognome" if nominativo else ""
    return corretto, (f"Letto dall'OCR come {cf}: corretto in {corretto} ({diversi}), unica correzione con "
                      f"carattere di controllo valido{controllo}. Verificare sul documento.")


# --- righe ---------------------------------------------------------------------------------

def raggruppa_righe(parole: list[Parola]) -> list[list[Parola]]:
    """Raggruppa le parole in righe (stessa altezza sulla pagina), ordinate da sinistra a destra."""
    if not parole:
        return []
    h = median(p.altezza for p in parole)
    righe: list[list[Parola]] = []
    for p in sorted(parole, key=lambda p: p.cy):
        if righe and abs(p.cy - median(q.cy for q in righe[-1])) <= 0.55 * h:
            righe[-1].append(p)
        else:
            righe.append([p])
    return [sorted(r, key=lambda p: p.x0) for r in righe]


def testo_da_parole(parole: list[Parola]) -> str:
    """Ricostruisce il testo mantenendo le colonne (come pdfplumber con layout=True)."""
    righe = raggruppa_righe(parole)
    if not righe:
        return ""
    larghezze = [(p.x1 - p.x0) / len(p.testo) for p in parole if p.testo]
    cw = max(median(larghezze), 1.0) if larghezze else 6.0
    sinistra = min(p.x0 for p in parole)
    linee = []
    for riga in righe:
        linea = ""
        for p in riga:
            colonna = int(round((p.x0 - sinistra) / cw))
            if linea:
                colonna = max(colonna, len(linea) + 1)
            linea = linea.ljust(colonna) + p.testo
        linee.append(linea)
    return "\n".join(linee)


# --- ricerca etichetta → valore ---------------------------------------------------------------

def _stringa_riga(riga: list[Parola]) -> tuple[str, list[tuple[int, int, Parola]]]:
    parti, mappa, pos = [], [], 0
    for p in riga:
        mappa.append((pos, pos + len(p.testo), p))
        parti.append(p.testo)
        pos += len(p.testo) + 1
    return " ".join(parti), mappa


def _x_di(offset: int, mappa) -> float:
    """Coordinata x di un carattere della riga (interpolata dentro la parola)."""
    for inizio, fine, p in mappa:
        if inizio <= offset <= fine:
            if fine == inizio:
                return p.x0
            return p.x0 + (p.x1 - p.x0) * (offset - inizio) / (fine - inizio)
    return mappa[-1][2].x1 if offset > mappa[-1][1] else mappa[0][2].x0


def _letterale(etichetta: str) -> str | None:
    """Testo semplice di un'etichetta-regex ("netto\\s+del\\s+mese" -> "netto del mese"), se è semplice."""
    t = etichetta.replace(r"\b", "")
    t = re.sub(r"(?:\\.|[^\\()\[\]])\?", "", t)  # caratteri opzionali ("a?r?rotondamento" -> "rotondamento")
    t = re.sub(r"\\w\*", "", t)                     # finali variabili ("preced\w*" -> "preced")
    t = re.sub(r"\\s[+*]?", " ", t)
    t = t.replace(r"\.", ".").replace("'", "'")
    if re.search(r"[\[\](){}|?*+^$\\]", t) or len(t.strip()) < 8:
        return None
    return re.sub(r" +", " ", t.strip().lower())


def _corrispondenze_approssimate(etichetta: str, stringa: str, soglia: float = 0.86):
    """Trova l'etichetta anche con 1-2 lettere lette male dall'OCR ("METTO DEL MESE")."""
    from difflib import SequenceMatcher

    letterale = _letterale(etichetta)
    if not letterale:
        return []
    bassa = stringa.lower()
    risultati = []
    # inizio di ogni parola, anche dopo una parentesi o un simbolo ("(mdeterminato)")
    inizi = sorted({0, *(m.end() for m in re.finditer(r"[\s(\[\"'«{|]+", bassa))})
    for i in inizi:
        punteggi = [(SequenceMatcher(None, bassa[i:i + n], letterale).ratio(), n)
                    for n in (len(letterale) - 1, len(letterale), len(letterale) + 1) if i + n <= len(bassa)]
        if punteggi:
            migliore, n = max(punteggi)
            if migliore >= soglia:
                risultati.append((i, i + n))
    return risultati


class _Corrispondenza:
    def __init__(self, inizio: int, fine: int):
        self._i, self._f = inizio, fine

    def start(self):
        return self._i

    def end(self):
        return self._f


_QUANTITA = re.compile(r"\d+,\d{3,}|\d[\d.,]*\s*(?:%|ORE\b|GG\b|H\b)", re.IGNORECASE)


def _solo_quantita(testo: str) -> bool:
    """Vero se tutti i numeri della cella sono ore, tariffe (3+ decimali) o percentuali, non importi."""
    numeri = re.findall(r"\d[\d.,]*\s*(?:%|ORE\b|GG\b|H\b)?", testo, re.IGNORECASE)
    return bool(numeri) and all(_QUANTITA.fullmatch(n.strip()) for n in numeri)


def _numero_di_casella(testo: str, match) -> bool:
    """Un intero senza decimali seguito subito da una descrizione è il numero di una casella ("8 Data inizio")."""
    valore = match.group(0)
    return not re.search(r"[.,]", valore) and bool(re.match(r"\s*[A-Za-zÀ-ÿ]{3,}", testo[match.end():]))


_PAROLA_ETICHETTA = re.compile(r"[A-Za-zÀ-ÿ]{3,}")
_IGNORA_TRA = re.compile(r"\b(?:EUR|euro)\b", re.IGNORECASE)


def _ha_etichetta_propria(cella: list[Parola], riga: list[Parola], h: float) -> bool:
    """Vero se il valore della cella ha, subito alla sua sinistra sulla stessa riga, una propria etichetta
    (es. "RC1 Redditi di pensione 24.050"): allora è il valore di quell'altro campo."""
    primo = next((p for p in cella if re.search(r"\d", p.testo)), None)
    if primo is None:
        return False
    i = riga.index(primo)
    if i == 0:
        return False
    vicino = riga[i - 1]
    return bool(_PAROLA_ETICHETTA.fullmatch(vicino.testo.strip(":.").replace("'", ""))) \
        and primo.x0 - vicino.x1 < 8 * h


def cerca_valore(etichetta: str, valore: str, parole: list[Parola] | None = None,
                 numerico: bool = True, righe_sotto: int = 3,
                 ignora_maiuscole: bool = False) -> tuple[bool, str | None]:
    """Cerca ``etichetta`` (regex) e restituisce (etichetta trovata?, testo del valore).

    ``valore`` è una regex: se ha un gruppo si restituisce il gruppo 1, altrimenti tutto il match.
    """
    parole = parole if parole is not None else parole_correnti()
    if not parole:
        return False, None
    righe = raggruppa_righe(parole)
    re_et = re.compile(etichetta, re.IGNORECASE)
    re_val = re.compile(valore, re.IGNORECASE if ignora_maiuscole else 0)
    from .estrazione import normalizza_ocr  # "197, 59" -> "197,59" anche tra parole separate
    trovata = False
    # se l'etichetta non compare esattamente da nessuna parte, la si cerca in modo approssimato (errori OCR)
    esatta = any(re_et.search(_stringa_riga(r)[0]) for r in righe)

    def corrispondenze(stringa):
        if esatta:
            return list(re_et.finditer(stringa))
        return [_Corrispondenza(a, b) for a, b in _corrispondenze_approssimate(etichetta, stringa)]

    def estrai(m):
        return (m.group(1) if m.re.groups else m.group(0)).strip()

    for i, riga in enumerate(righe):
        stringa, mappa = _stringa_riga(riga)
        for m in corrispondenze(stringa):
            trovata = True
            x0, x1 = _x_di(m.start(), mappa), _x_di(m.end(), mappa)
            parole_et = [p for a, b, p in mappa if b > m.start() and a < m.end()]
            h = median(p.altezza for p in parole_et)
            bottom = max(p.bottom for p in parole_et)

            # 1. stessa riga, subito a destra (niente altre etichette in mezzo)
            resto = normalizza_ocr(stringa[m.end():])
            mv = re_val.search(resto)
            if mv:
                tra = _IGNORA_TRA.sub("", resto[:mv.start()])
                gap = _x_di(m.end() + mv.start(), mappa) - x1
                if not _PAROLA_ETICHETTA.search(tra) and (numerico or ":" in tra or gap < 2.5 * h) \
                        and not _numero_di_casella(resto, mv):
                    return True, estrai(mv)

            # 2. cella sotto: tra l'inizio dell'etichetta e il campo successivo della stessa riga
            dopo = [p for a, b, p in mappa if a >= m.end() + 1 and p.x0 > x1 + 0.3 * h]
            destra = dopo[0].x0 - 0.3 * h if dopo else float("inf")
            # il valore sta nella cella che comincia con l'etichetta: si guarda il centro del valore, così un
            # importo allineato a destra nella cella precedente non viene attribuito a questa
            sinistra = x0 - 0.5 * h
            fondo, continuazioni = bottom, 0
            for riga_sotto in righe[i + 1:i + 1 + righe_sotto + 2]:
                if min(p.top for p in riga_sotto) > fondo + 4.5 * h:
                    break
                cella = [p for p in riga_sotto if sinistra <= p.cx <= destra]
                if not cella:
                    continue
                testo_cella = normalizza_ocr(" ".join(p.testo for p in cella))
                mv = re_val.search(testo_cella)
                # si guarda solo la prima riga con qualcosa in questa colonna, e il valore deve venire prima
                # di qualsiasi altra etichetta (altrimenti è il valore di un altro campo)
                if mv and not _PAROLA_ETICHETTA.search(_IGNORA_TRA.sub("", testo_cella[:mv.start()])) \
                        and not _ha_etichetta_propria(cella, riga_sotto, h) and not _numero_di_casella(testo_cella, mv):
                    return True, estrai(mv)
                # descrizione che va a capo nella stessa casella ("Redditi di lavoro dipendente ed /
                # assimilati (indeterminato)"): solo parole, allineata, subito sotto -> si scende ancora
                if continuazioni < 2 and not mv and not re.search(r"\d", testo_cella) \
                        and abs(cella[0].x0 - x0) <= 3 * h and min(p.top for p in cella) - fondo <= 1.5 * h:
                    continuazioni += 1
                    fondo = max(p.bottom for p in cella)
                    continue
                # solo parole NON allineate all'etichetta: descrizione di una casella vicina (es. "di famiglia")
                # di cui l'OCR ha perso l'inizio -> si salta; una riga con numeri invece ferma la ricerca
                if not mv and not re.search(r"\d", testo_cella) and abs(cella[0].x0 - x0) > 3 * h:
                    continue
                # solo ore, tariffe o percentuali ("8,22500 ORE", "27,22500"): non sono importi -> si salta
                if not mv and _solo_quantita(testo_cella):
                    continue
                break
    return trovata, None
