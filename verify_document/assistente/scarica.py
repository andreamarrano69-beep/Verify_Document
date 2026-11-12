"""Scarica i documenti pubblici di OAM e Compass nella cartella dei documenti dell'assistente AI.

- PDF collegati alle pagine elencate in FONTI e testo delle pagine stesse (.txt)
- salta i documenti non pertinenti (compro oro, cripto, polizze auto, ...): liste «escludi»
- nomi dei file Compass leggibili (es. «Cessione del quinto - Copia idonea per la stipula (CQ002).pdf»)
- rilanciandolo scarica solo i file nuovi e sostituisce quelli cambiati sul sito (es. tabella TEGM)
- il sito OAM può rifiutare gli scaricamenti automatici (errore 403): in quel caso i PDF si scaricano a mano
  dal browser e si mettono nella cartella OAM (oppure «+ Documento» nella finestra dell'assistente)
Solo libreria standard di Python.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urljoin, urlparse

PAUSA_SECONDI = 1.5  # attesa tra una richiesta e l'altra, per non sovraccaricare i siti
FORZA_HTTPS = True   # i link http dei siti vengono aperti in https
INTESTAZIONI = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
}

FONTI = {
    "oam": {
        "cartella": "OAM",
        "domini": ["organismo-am.it"],
        "nomi_descrittivi": False,
        "pagine": [
            ("normativa",        "https://www.organismo-am.it/normative-di-settore"),
            ("circolari",        "https://www.organismo-am.it/circolari"),
            ("regolamenti",      "https://www.organismo-am.it/regolamenti-integrativi"),
            ("linee_guida",      "https://www.organismo-am.it/pubblicazioni-oam/linee-guida"),
            ("comunicazioni",    "https://www.organismo-am.it/comunicazioni"),
            ("agenti",           "https://www.organismo-am.it/profilo-professionale-agente"),
            ("agenti",           "https://www.organismo-am.it/requisiti-persone-fisiche"),
            ("agenti",           "https://www.organismo-am.it/dipendenti-e-collaboratori"),
            ("mediatori",        "https://www.organismo-am.it/mediatore"),
            ("mediatori",        "https://www.organismo-am.it/mediatore-requisiti"),
            ("mediatori",        "https://www.organismo-am.it/dipendenti-mediatore"),
            ("vigilanza",        "https://www.organismo-am.it/vigilanza/elementi-di-verifica-per-gli-agenti"),
            ("vigilanza",        "https://www.organismo-am.it/vigilanza/elementi-di-verifica-per-i-mediatori"),
            ("prova_valutativa", "https://www.organismo-am.it/bando-prova-valutativa"),
            ("faq_e_guide",      "https://www.organismo-am.it/info-point/domande-frequenti"),
            ("faq_e_guide",      "https://www.organismo-am.it/info-point/guide-operative"),
        ],
        "escludi": [
            r"compro[\s_-]*oro", r"\boco\b", r"\boro\b", r"operatori? professional\w* in oro",
            r"cambiavalute", r"\bvasp\b", r"valut\w* virtual\w*", r"cripto", r"crypto",
            r"merchant", r"punti di contatto", r"\bpsp\b", r"\bimel\b",
            r"elezioni", r"bilancio", r"lavora in oam", r"bando di (selezione|concorso)",
        ],
    },

    "compass": {
        "cartella": "Compass",
        "domini": ["compass.it", "compassquinto.it"],
        "nomi_descrittivi": True,
        "pagine": [
            # Trasparenza Compass: contratti, fogli informativi, polizze, guide, TEGM
            ("trasparenza_compass", "https://www.compass.it/trasparenza.html"),
            # Trasparenza Compass Quinto (rete agenti, cessione del quinto)
            ("trasparenza_compassquinto", "https://www.compassquinto.it/trasparenza.html"),
            # Privacy, reclami, antiriciclaggio
            ("privacy",          "https://www.compass.it/privacy.html"),
            ("privacy",          "https://www.compassquinto.it/privacy.html"),
            ("reclami",          "https://www.compass.it/reclami.html"),
            ("antiriciclaggio",  "https://www.compass.it/antiriciclaggio.html"),
        ],
        "escludi": [
            # documenti tecnici o in altre lingue
            r"accessibilit", r"tedesc", r"leitfaden", r"\bTED\b",
            # polizze non più in vendita
            r"non (più )?disponibil\w* per la vendita",
            # prodotti fuori dal tuo ambito: business, Poste, pagamenti, factoring
            r"bancoposta", r"partita iva", r"business", r"factoring", r"heylight",
            r"nexi", r"acquiring", r"mobile payments", r"commercio elettronico",
            r"trasferimento dei servizi di pagamento", r"\bpsd2\b", r"opuscolo",
            # polizze auto/moto/casa/beni (non legate ai finanziamenti)
            r"\bcvt\b", r"kasko", r"gap auto", r"car (protection|assistance)", r"motocicl",
            r"casa sempre", r"goods protection", r"design protection",
            r"fondo interbancario",
        ],
    },
}



# ------------------------------------------------------------------ lettura delle pagine
class _Pagina(HTMLParser):
    """Raccoglie i link (con testo e titolo della sezione) e il testo utile della pagina."""

    SALTA = {"script", "style", "nav", "header", "footer", "form", "noscript"}
    TITOLI = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.link: list[tuple[str, str, str]] = []   # (href, testo, titolo sezione)
        self.testo: list[str] = []
        self._salta = 0
        self._titolo_corrente = ""
        self._in_titolo = False
        self._buffer_titolo: list[str] = []
        self._href: str | None = None
        self._buffer_link: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SALTA:
            self._salta += 1
        elif tag in self.TITOLI:
            self._in_titolo, self._buffer_titolo = True, []
        elif tag == "a":
            self._href = dict(attrs).get("href")
            self._buffer_link = []
        elif tag in ("br", "p", "div", "li", "tr"):
            self.testo.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SALTA and self._salta:
            self._salta -= 1
        elif tag in self.TITOLI and self._in_titolo:
            self._in_titolo = False
            self._titolo_corrente = " ".join("".join(self._buffer_titolo).split())
        elif tag == "a" and self._href is not None:
            self.link.append((self._href, " ".join("".join(self._buffer_link).split()), self._titolo_corrente))
            self._href = None

    def handle_data(self, data):
        if self._in_titolo:
            self._buffer_titolo.append(data)
        if self._href is not None:
            self._buffer_link.append(data)
        if not self._salta:
            self.testo.append(data)

    def testo_pulito(self) -> str:
        righe = [r.strip() for r in "".join(self.testo).splitlines()]
        return "\n".join(r for r in righe if r)


def _scarica(url: str, timeout: float = 60) -> bytes:
    richiesta = urllib.request.Request(url, headers=INTESTAZIONI)
    with urllib.request.urlopen(richiesta, timeout=timeout) as r:  # noqa: S310 - siti fissi in FONTI
        return r.read()


def nome_file_sicuro(nome: str, massimo: int = 150) -> str:
    nome = unquote(nome)
    nome = re.sub(r'[<>:"/\\|?*\n\r\t]', " ", nome)
    nome = re.sub(r"\s+", " ", nome).strip(" .")
    return nome[:massimo]


def _nome_pdf(url: str, testo_link: str, sezione: str, descrittivi: bool) -> str:
    originale = Path(unquote(urlparse(url).path)).name
    if not descrittivi:
        return nome_file_sicuro(originale)
    if testo_link and testo_link.lower() not in sezione.lower():
        descrizione = f"{sezione} - {testo_link}" if sezione else testo_link
    else:
        descrizione = sezione or Path(originale).stem
    return f"{nome_file_sicuro(descrizione, 120)} ({Path(originale).stem}).pdf"


def aggiorna(cartella: str | Path, fonti: list[str] | None = None,
             avanzamento: Callable[[str], None] = print, pausa: float = PAUSA_SECONDI) -> dict:
    """Scarica le fonti indicate (predefinito: tutte). Restituisce il riepilogo."""
    cartella = Path(cartella)
    riepilogo = {"nuovi": [], "aggiornati": [], "invariati": 0, "esclusi": 0, "errori": [], "bloccati": []}
    for nome_fonte in fonti or list(FONTI):
        fonte = FONTI[nome_fonte]
        filtro = re.compile("|".join(fonte["escludi"]), re.IGNORECASE)
        base = cartella / fonte["cartella"]
        visti: set[str] = set()
        bloccate = 0
        for sottocartella, url_pagina in fonte["pagine"]:
            avanzamento(f"{nome_fonte.upper()}: {url_pagina}")
            try:
                html = _scarica(url_pagina, 30).decode("utf-8", errors="ignore")
            except (urllib.error.URLError, OSError) as e:
                riepilogo["errori"].append(f"{url_pagina}: {e}")
                if "403" in str(e):
                    bloccate += 1
                    if bloccate >= 3:
                        riepilogo["bloccati"].append(nome_fonte.upper())
                        break
                continue
            time.sleep(pausa)
            pagina = _Pagina()
            pagina.feed(html)
            destinazione = base / sottocartella
            destinazione.mkdir(parents=True, exist_ok=True)
            testo = pagina.testo_pulito()
            if len(testo) > 200:
                dominio = urlparse(url_pagina).netloc.replace("www.", "")
                percorso = urlparse(url_pagina).path.strip("/").replace("/", "_").replace(".html", "")
                (destinazione / nome_file_sicuro(f"pagina {dominio} {percorso}.txt")).write_text(
                    f"Fonte: {url_pagina}\nScaricato il: {datetime.now():%d/%m/%Y}\n\n{testo}", encoding="utf-8")
            for href, testo_link, sezione in pagina.link:
                url = urljoin(url_pagina, href.strip())
                if FORZA_HTTPS and url.startswith("http://"):
                    url = "https://" + url[len("http://"):]
                parti = urlparse(url)
                if not parti.path.lower().endswith(".pdf") or url in visti:
                    continue
                if not any(parti.netloc.endswith(d) for d in fonte["domini"]):
                    continue
                visti.add(url)
                if filtro.search(" ".join([unquote(parti.path).replace("_", " "), testo_link, sezione])):
                    riepilogo["esclusi"] += 1
                    continue
                file = destinazione / _nome_pdf(url, testo_link, sezione, fonte["nomi_descrittivi"])
                try:
                    contenuto = _scarica(url)
                    if not contenuto.startswith(b"%PDF"):
                        raise ValueError("il file scaricato non è un PDF")
                    if file.exists() and file.read_bytes() == contenuto:
                        riepilogo["invariati"] += 1
                    else:
                        riepilogo["aggiornati" if file.exists() else "nuovi"].append(file.name)
                        file.write_bytes(contenuto)
                        avanzamento(f"  + {file.name}")
                except (urllib.error.URLError, OSError, ValueError) as e:
                    riepilogo["errori"].append(f"{url}: {e}")
                time.sleep(pausa)
    return riepilogo


def testo_riepilogo(r: dict) -> str:
    righe = [f"Nuovi PDF: {len(r['nuovi'])} · aggiornati: {len(r['aggiornati'])} · invariati: {r['invariati']} · "
             f"saltati perché non pertinenti: {r['esclusi']} · errori: {len(r['errori'])}"]
    for nome in r["bloccati"]:
        righe.append(f"Il sito {nome} blocca gli scaricamenti automatici: scarica i PDF a mano dal browser e mettili "
                     f"nella cartella {nome} (o usa «+ Documento»).")
    return "\n".join(righe)
