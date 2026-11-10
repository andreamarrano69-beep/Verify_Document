"""Estratto conto contributivo (INPS, ex INPDAP / dipendenti pubblici, Gestione separata, casse).

Legge le righe dei periodi:   dal  al  tipo di contribuzione  contributi  unità  retribuzione  datore
    01/01/2010  31/12/2010  Lavoro dipendente  52  Settimane  25.000,00  ALFA SRL

Calcola:
- la somma dei contributi versati, convertita in settimane (52 = 1 anno)
- l'anzianità contributiva stimata: per ogni anno al massimo 52 settimane, così i periodi
  sovrapposti (due lavori nello stesso periodo) non vengono contati due volte
- gli anni e mesi che mancano ai requisiti di pensione (anticipata e vecchiaia)

Controlli:
- codice fiscale valido
- date dei periodi (inizio prima della fine, nessuna data nel futuro)
- contributi non superiori alla durata del periodo (es. 60 settimane in un anno)
- periodi sovrapposti e periodi scoperti (buchi contributivi)
- totale indicato nel documento uguale alla somma delle righe

Conversioni in settimane: settimane 1:1; mesi × 52/12; anni × 52;
giorni: 6 giorni = 1 settimana (INPS), per i dipendenti pubblici (ex INPDAP, CPDEL, CTPS, ...) 360 giorni = 1 anno.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from .layout import cf_corretto_ocr
from .report import Esito, Report
from .validators import IMPORTO_DECIMALI, decodifica_codice_fiscale, formatta_euro, parse_importo, trova_codici_fiscali

SETTIMANE_ANNO = 52
# Requisiti di pensione in vigore fino al 2026 (dal 2027 possono aumentare per la speranza di vita)
ANTICIPATA_UOMINI = 42 * 52 + 10 * 52 / 12   # 42 anni e 10 mesi ≈ 2.227 settimane
ANTICIPATA_DONNE = 41 * 52 + 10 * 52 / 12    # 41 anni e 10 mesi ≈ 2.175 settimane
VECCHIAIA_CONTRIBUTI = 20 * 52                # 20 anni di contributi
VECCHIAIA_ETA = 67

GRUPPO_PERIODI = "Periodi contributivi"
GRUPPO_ANZIANITA = "Anzianità contributiva"

_DATA = r"(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})"
_UNITA = {
    "settimane": "settimane", "settimana": "settimane", "sett": "settimane", "settim": "settimane",
    "mesi": "mesi", "mese": "mesi", "giorni": "giorni", "giorno": "giorni", "gg": "giorni",
    "anni": "anni", "anno": "anni",
}
_RE_UNITA = r"(settimane|settimana|settim\.?|sett\.?|mesi|mese|giorni|giorno|gg\.?|anni|anno)"
_PUBBLICI = re.compile(r"inpdap|cpdel|ctps|cps\b|cpi\b|cpug|dipendenti\s+pubblici|gestione\s+pubblica|"
                       r"amministrazion[ei]\s+(?:pubblic|statal)|stato\b|statale|scuola|ministero", re.IGNORECASE)


def riconosci(testo: str) -> int:
    t = testo.lower()
    punti = 0
    for k, peso in [("estratto conto contributivo", 6), ("estratto contributivo", 6), ("estratto conto certificativo", 6),
                    ("estratto conto integrato", 6), ("ecocert", 5), ("posizione assicurativa", 3),
                    ("contributi utili", 2), ("settimane", 1), ("gestione separata", 1),
                    ("fondo pensioni lavoratori dipendenti", 2), ("tipologia contributo", 2),
                    ("tipo contribuzione", 2), ("contribuzione", 1)]:
        if k in t:
            punti += peso
    # molte righe "dal al" con date: tipico dell'estratto
    if len(re.findall(_DATA + r"\s*(?:-|–|al)?\s*" + _DATA, testo)) >= 3:
        punti += 2
    return punti


@dataclass
class Periodo:
    dal: date
    al: date
    tipo: str
    contributi: Decimal
    unita: str
    retribuzione: Decimal | None
    datore: str
    riga: str

    @property
    def pubblico(self) -> bool:
        return bool(_PUBBLICI.search(self.tipo))

    @property
    def settimane(self) -> Decimal:
        """Contributi convertiti in settimane."""
        c = self.contributi
        if self.unita == "mesi":
            return c * 52 / 12
        if self.unita == "anni":
            return c * 52
        if self.unita == "giorni":
            return c * 52 / 360 if self.pubblico else c / 6
        return c

    @property
    def settimane_massime(self) -> Decimal:
        """Settimane che il periodo può contenere al massimo (durata del periodo)."""
        giorni = (self.al - self.dal).days + 1
        return Decimal(giorni) / 7

    def testo(self) -> str:
        unita = {"settimane": "sett.", "mesi": "mesi", "giorni": "gg", "anni": "anni"}[self.unita]
        n = f"{self.contributi:f}".rstrip("0").rstrip(".") if "." in f"{self.contributi:f}" else f"{self.contributi}"
        parti = [f"{self.dal:%d/%m/%Y} – {self.al:%d/%m/%Y}", self.tipo or "contribuzione", f"{n} {unita}"]
        if self.unita != "settimane":
            parti[-1] += f" (= {_sett(self.settimane)} sett.)"
        if self.retribuzione is not None:
            parti.append(f"retribuzione {formatta_euro(self.retribuzione)}")
        if self.datore:
            parti.append(self.datore)
        return " · ".join(parti)


def _data(s: str) -> date | None:
    g, m, a = map(int, re.split(r"[/.-]", s))
    try:
        return date(a, m, g)
    except ValueError:
        return None


def _numero(s: str) -> Decimal:
    s = s.replace(".", "").replace(",", ".") if "," in s else s
    return Decimal(s)


def _sett(x: Decimal | float) -> str:
    return f"{Decimal(x).quantize(Decimal('1'), ROUND_HALF_UP):,}".replace(",", ".")


def anni_mesi(settimane: Decimal | float) -> str:
    settimane = Decimal(settimane)
    mesi_totali = int((settimane * 12 / 52).quantize(Decimal("1"), ROUND_HALF_UP))
    anni, mesi = divmod(mesi_totali, 12)
    parti = []
    if anni:
        parti.append(f"{anni} ann{'o' if anni == 1 else 'i'}")
    if mesi or not anni:
        parti.append(f"{mesi} mes{'e' if mesi == 1 else 'i'}")
    return " e ".join(parti)


def _unita_predefinita(testo: str) -> str:
    conta = {u: len(re.findall(rf"\b{u}\b", testo, re.IGNORECASE)) for u in ("settimane", "mesi", "giorni")}
    migliore = max(conta, key=conta.get)
    return migliore if conta[migliore] else "settimane"


_RIGA = re.compile(rf"^\s*{_DATA}\s*(?:-|–|al)?\s*{_DATA}\s+(?P<resto>.+)$", re.IGNORECASE | re.MULTILINE)


def leggi_periodi(testo: str) -> list[Periodo]:
    predefinita = _unita_predefinita(testo)
    periodi = []
    for m in _RIGA.finditer(testo):
        dal, al = _data(m.group(1)), _data(m.group(2))
        if not dal or not al:
            continue
        resto = re.sub(r"[ \t]+", " ", m.group("resto")).strip()
        retribuzione = None
        imp = re.search(r"(?<![\d.,])(" + IMPORTO_DECIMALI + r")(?![\d,])", resto)
        if imp:
            retribuzione = parse_importo(imp.group(1))
        # contributi: "52 Settimane" (o "Settimane 52"), altrimenti il primo numero intero isolato
        u = re.search(r"(?<![\d.,])(\d{1,4}(?:[.,]\d{1,2})?)\s*" + _RE_UNITA + r"(?![a-z])", resto, re.IGNORECASE)
        if not u:
            u2 = re.search(_RE_UNITA + r"\s*(\d{1,4}(?:[.,]\d{1,2})?)(?![\d.,])", resto, re.IGNORECASE)
            if u2:
                numero, unita, inizio, fine = u2.group(2), u2.group(1), u2.start(), u2.end()
            else:
                n = None
                for c in re.finditer(r"(?<![\d.,/])(\d{1,4}(?:,\d{1,2})?)(?![\d.,/])", resto):
                    if imp and imp.start() <= c.start() < imp.end():
                        continue
                    n = c
                    break
                if not n:
                    continue
                numero, unita, inizio, fine = n.group(1), predefinita, n.start(), n.end()
        else:
            numero, unita, inizio, fine = u.group(1), u.group(2), u.start(), u.end()
        unita = _UNITA[unita.lower().rstrip(".")]
        tipo = resto[:inizio].strip(" -·|")
        dopo = resto[fine:]
        if imp and imp.start() >= fine:
            dopo = resto[imp.end():]
        elif imp and imp.end() <= inizio:
            tipo = resto[:imp.start()].strip(" -·|")
        datore = dopo.strip(" -·|")
        periodi.append(Periodo(dal, al, tipo, _numero(numero), unita, retribuzione, datore, m.group(0).strip()))
    return periodi


def _unisci(intervalli: list[tuple[date, date]]) -> list[tuple[date, date]]:
    uniti: list[list[date]] = []
    for dal, al in sorted(intervalli):
        if uniti and dal <= uniti[-1][1] + timedelta(days=1):
            uniti[-1][1] = max(uniti[-1][1], al)
        else:
            uniti.append([dal, al])
    return [(a, b) for a, b in uniti]


def settimane_per_anno(periodi: list[Periodo]) -> dict[int, Decimal]:
    """Settimane di ogni anno solare (un periodo su più anni è diviso in proporzione ai giorni)."""
    anni: dict[int, Decimal] = {}
    for p in periodi:
        giorni_tot = (p.al - p.dal).days + 1
        if giorni_tot <= 0:
            continue
        for anno in range(p.dal.year, p.al.year + 1):
            inizio, fine = max(p.dal, date(anno, 1, 1)), min(p.al, date(anno, 12, 31))
            quota = Decimal((fine - inizio).days + 1) / giorni_tot
            anni[anno] = anni.get(anno, Decimal(0)) + p.settimane * quota
    return dict(sorted(anni.items()))


def analizza(testo: str, oggi: date | None = None) -> Report:
    oggi = oggi or date.today()
    r = Report("Estratto contributivo")
    d = r.dati

    ente = re.search(r"\b(INPS|INPDAP|ENPAM|INARCASSA|CASSA\s+FORENSE|ENASARCO|CIPAG|ENPAIA|CASSA\s+GEOMETRI)\b",
                     testo, re.IGNORECASE)
    d["ente"] = ente.group(1).upper() if ente else None
    m = re.search(r"(?i:assicurato|lavoratore|cognome\s+e\s+nome|nominativo|intestatario)\s*[:\-]\s*"
                  r"([A-Z][A-Z'À-Ü]+(?: [A-Z'À-Ü]+){1,3})(?=\s{2,}|\s*\n|\s+(?i:codice|c\.f|nat))", testo)
    d["nominativo"] = m.group(1).strip() if m else None
    m = re.search(r"(?i:aggiornato\s+al|alla\s+data\s+del|data\s+(?:di\s+)?(?:stampa|elaborazione|emissione))\s*[:\-]?\s*"
                  + _DATA, testo)
    d["data_estratto"] = _data(m.group(1)) if m else None

    codici = trova_codici_fiscali(testo)
    cf, nota_cf = cf_corretto_ocr(codici[0] if codici else None, d.get("nominativo"))
    d["codice_fiscale"] = cf
    info = None
    if nota_cf:
        r.aggiungi("Codice fiscale corretto (OCR)", Esito.ATTENZIONE, nota_cf)
    if not cf:
        r.aggiungi("Codice fiscale", Esito.ERRORE, "Codice fiscale non trovato")
    else:
        info = decodifica_codice_fiscale(cf, oggi)
        if info.valido:
            eta = oggi.year - info.data_nascita.year - ((oggi.month, oggi.day) < (info.data_nascita.month,
                                                                                    info.data_nascita.day))
            d["eta"] = eta
            r.aggiungi("Codice fiscale", Esito.OK, f"{cf} valido — età {eta} anni")
        else:
            r.aggiungi("Codice fiscale", Esito.ERRORE, f"{cf} NON valido (carattere di controllo errato)")
            info = None

    periodi = leggi_periodi(testo)
    d["periodi_letti"] = len(periodi)
    if not periodi:
        r.aggiungi("Periodi contributivi", Esito.ERRORE,
                   "Nessun periodo letto (righe attese: dal, al, tipo, contributi, unità). Controllare il tipo di documento "
                   "o la scansione")
        return r

    # --- controlli riga per riga --------------------------------------------------------
    for p in periodi:
        esito, note = Esito.INFO, []
        if p.al < p.dal:
            esito = Esito.ERRORE
            note.append("data di fine precedente all'inizio")
        if p.al > oggi:
            esito = Esito.ERRORE
            note.append("periodo nel futuro")
        if p.al >= p.dal and p.settimane > p.settimane_massime + Decimal("1.5"):
            esito = Esito.ERRORE if esito == Esito.ERRORE else Esito.ATTENZIONE
            note.append(f"{_sett(p.settimane)} settimane in un periodo di {_sett(p.settimane_massime)}: troppe")
        r.aggiungi(f"{p.dal.year}" if p.dal.year == p.al.year else f"{p.dal.year}–{p.al.year}", esito,
                   p.testo() + (f" — {'; '.join(note)}" if note else ""), GRUPPO_PERIODI)

    validi = [p for p in periodi if p.al >= p.dal]
    somma = sum((p.settimane for p in validi), Decimal(0))
    per_anno = settimane_per_anno(validi)
    utili = sum((min(s, Decimal(SETTIMANE_ANNO)) for s in per_anno.values()), Decimal(0))
    r.extra["periodi"] = [{"dal": p.dal, "al": p.al, "tipo": p.tipo, "settimane": p.settimane,
                           "retribuzione": p.retribuzione, "datore": p.datore} for p in validi]
    d["primo_contributo"] = min(p.dal for p in validi) if validi else None
    d["ultimo_contributo"] = max(p.al for p in validi) if validi else None
    d["somma_contributi_settimane"] = int(somma.quantize(Decimal("1"), ROUND_HALF_UP))
    d["anzianita_settimane"] = int(utili.quantize(Decimal("1"), ROUND_HALF_UP))
    d["anzianita_contributiva"] = anni_mesi(utili)
    retribuzioni = [p.retribuzione for p in validi if p.retribuzione is not None]
    d["totale_retribuzioni"] = sum(retribuzioni, Decimal(0)) if retribuzioni else None

    # per gestione (tipo di contribuzione)
    for tipo in sorted({p.tipo or "non indicato" for p in validi}):
        s = sum((p.settimane for p in validi if (p.tipo or "non indicato") == tipo), Decimal(0))
        r.aggiungi(f"Totale {tipo}", Esito.INFO, f"{_sett(s)} settimane ({anni_mesi(s)})", GRUPPO_ANZIANITA)

    r.aggiungi("Somma dei contributi", Esito.INFO,
               f"{_sett(somma)} settimane = {anni_mesi(somma)} (somma di tutte le righe)", GRUPPO_ANZIANITA)
    esito_anz = Esito.OK
    dettaglio = f"{_sett(utili)} settimane = {anni_mesi(utili)}"
    if utili < somma - 1:
        dettaglio += (f" — {_sett(somma - utili)} settimane in anni con più di 52 settimane (periodi sovrapposti) "
                      "non contano per il diritto alla pensione, salvo cumulo/totalizzazione")
        esito_anz = Esito.ATTENZIONE
    r.aggiungi("Anzianità contributiva (stima)", esito_anz, dettaglio, GRUPPO_ANZIANITA)

    # sovrapposizioni tra righe (solo segnalazione: stesse date in due righe)
    ordinati = sorted(validi, key=lambda p: (p.dal, p.al))
    sovrapposti = []
    for i, a in enumerate(ordinati):
        for b in ordinati[i + 1:]:
            if b.dal > a.al:
                break
            inizio, fine = max(a.dal, b.dal), min(a.al, b.al)
            if (fine - inizio).days >= 6:
                sovrapposti.append(f"{inizio:%d/%m/%Y}–{fine:%d/%m/%Y} ({a.tipo or '?'} / {b.tipo or '?'})")
    if sovrapposti:
        r.aggiungi("Periodi sovrapposti", Esito.ATTENZIONE,
                   f"{len(sovrapposti)}: " + "; ".join(sovrapposti[:6]) + (" …" if len(sovrapposti) > 6 else "")
                   + " — verificare che non siano contributi doppi")
    else:
        r.aggiungi("Periodi sovrapposti", Esito.OK, "Nessuna sovrapposizione tra le righe")

    # buchi contributivi (più di un mese senza contributi)
    uniti = _unisci([(p.dal, p.al) for p in validi])
    buchi = [(a[1] + timedelta(days=1), b[0] - timedelta(days=1)) for a, b in zip(uniti, uniti[1:])
             if (b[0] - a[1]).days > 31]
    if buchi:
        testo_buchi = "; ".join(f"{x:%d/%m/%Y}–{y:%d/%m/%Y} ({anni_mesi(Decimal((y - x).days + 1) / 7)})"
                                for x, y in buchi[:6])
        r.aggiungi("Periodi senza contributi", Esito.INFO,
                   f"{len(buchi)}: {testo_buchi}{' …' if len(buchi) > 6 else ''} (eventuale riscatto o "
                   "contribuzione figurativa da verificare)")
    else:
        r.aggiungi("Periodi senza contributi", Esito.OK, "Nessun periodo scoperto superiore a un mese")
    if d["ultimo_contributo"] and (oggi - d["ultimo_contributo"]).days > 400:
        r.aggiungi("Ultimo contributo", Esito.ATTENZIONE,
                   f"{d['ultimo_contributo']:%d/%m/%Y}: nessun contributo da più di un anno (estratto non aggiornato "
                   "o lavoro non più in corso)")

    # totale indicato nel documento
    m = re.search(r"(?i)totale\s+(?:generale\s+)?(?:contributi|settimane)(?:\s+utili)?[^\d\n]{0,30}"
                  r"(\d{1,2}\.\d{3}|\d{1,4})(?!\s*[,/]\d)", testo)
    if m:
        dichiarato = _numero(m.group(1).replace(".", ""))
        d["totale_indicato"] = int(dichiarato)
        if abs(dichiarato - somma) <= 1 or abs(dichiarato - utili) <= 1:
            r.aggiungi("Totale del documento", Esito.OK, f"{_sett(dichiarato)} settimane, uguale alla somma delle righe")
        else:
            r.aggiungi("Totale del documento", Esito.ERRORE,
                       f"Il documento indica {_sett(dichiarato)} settimane, la somma delle righe è {_sett(somma)} "
                       f"(anzianità {_sett(utili)}): righe mancanti, lette male o totale modificato")

    # requisiti di pensione
    if info is not None:
        anticipata = Decimal(ANTICIPATA_DONNE if info.sesso == "F" else ANTICIPATA_UOMINI)
        mancano = anticipata - utili
        r.aggiungi("Pensione anticipata", Esito.INFO,
                   ("requisito raggiunto" if mancano <= 0 else f"mancano circa {anni_mesi(mancano)}")
                   + f" (servono {'41' if info.sesso == 'F' else '42'} anni e 10 mesi di contributi, "
                   "requisiti fino al 2026)", GRUPPO_ANZIANITA)
        eta_mancante = VECCHIAIA_ETA - d.get("eta", 0)
        contr = "contributi sufficienti" if utili >= VECCHIAIA_CONTRIBUTI else \
            f"mancano {anni_mesi(Decimal(VECCHIAIA_CONTRIBUTI) - utili)} di contributi"
        r.aggiungi("Pensione di vecchiaia", Esito.INFO,
                   (f"età raggiunta, {contr}" if eta_mancante <= 0 else f"tra {eta_mancante} anni (67 anni di età), {contr}")
                   + " (servono almeno 20 anni)", GRUPPO_ANZIANITA)
    return r
