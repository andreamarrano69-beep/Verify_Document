"""Collegamento a Ollama tramite la sua API HTTP (nessuna libreria in più da installare).

Ollama può girare su questo PC (http://localhost:11434) oppure su un altro PC dell'ufficio
(es. http://PC-ANDREA:11434: su quel PC va impostata la variabile OLLAMA_HOST=0.0.0.0).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Iterator


class ErroreOllama(Exception):
    pass


def _url(host: str, percorso: str) -> str:
    host = (host or "http://localhost:11434").rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host + percorso


def _post(host: str, percorso: str, dati: dict, timeout: float = 600):
    richiesta = urllib.request.Request(_url(host, percorso), data=json.dumps(dati).encode("utf-8"),
                                       headers={"Content-Type": "application/json"}, method="POST")
    try:
        return urllib.request.urlopen(richiesta, timeout=timeout)  # noqa: S310 - indirizzo scelto dall'utente
    except urllib.error.HTTPError as e:
        try:
            messaggio = json.loads(e.read().decode("utf-8")).get("error", str(e))
        except Exception:
            messaggio = str(e)
        raise ErroreOllama(spiega(messaggio)) from e
    except (urllib.error.URLError, OSError) as e:
        raise ErroreOllama(spiega(str(e))) from e


def spiega(errore: str) -> str:
    t = errore.lower()
    if "refused" in t or "rifiutata" in t or "timed out" in t or "urlopen" in t or "no route" in t:
        return ("Non riesco a collegarmi a Ollama. Controlla che sia avviato (icona vicino all'orologio) "
                "o l'indirizzo in ⚙ Impostazioni → Assistente AI.")
    if "not found" in t and "model" in t:
        return "Modello non scaricato: in ⚙ Impostazioni → Assistente AI premi «Scarica i modelli»."
    return errore


def modelli(host: str, timeout: float = 3) -> list[str]:
    """Modelli installati; solleva ErroreOllama se Ollama non risponde."""
    try:
        with urllib.request.urlopen(_url(host, "/api/tags"), timeout=timeout) as r:  # noqa: S310
            return [m.get("name", "") for m in json.loads(r.read().decode("utf-8")).get("models", [])]
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ErroreOllama(spiega(str(e))) from e


def disponibile(host: str) -> bool:
    try:
        modelli(host)
        return True
    except ErroreOllama:
        return False


def ha_modello(installati: list[str], nome: str) -> bool:
    base = nome if ":" in nome else nome + ":latest"
    return nome in installati or base in installati


def embed(host: str, modello: str, testi: list[str]) -> list[list[float]]:
    with _post(host, "/api/embed", {"model": modello, "input": testi}) as r:
        return json.loads(r.read().decode("utf-8"))["embeddings"]


def chat(host: str, modello: str, messaggi: list[dict]) -> Iterator[str]:
    """Risposta a pezzi, man mano che viene scritta."""
    with _post(host, "/api/chat", {"model": modello, "messages": messaggi, "stream": True}) as r:
        for riga in r:
            if not riga.strip():
                continue
            dato = json.loads(riga.decode("utf-8"))
            if dato.get("error"):
                raise ErroreOllama(spiega(dato["error"]))
            pezzo = dato.get("message", {}).get("content", "")
            if pezzo:
                yield pezzo
            if dato.get("done"):
                break


def scarica_modello(host: str, modello: str) -> Iterator[str]:
    """Scarica un modello (ollama pull) restituendo l'avanzamento in testo."""
    with _post(host, "/api/pull", {"model": modello, "stream": True}, timeout=3600) as r:
        for riga in r:
            if not riga.strip():
                continue
            dato = json.loads(riga.decode("utf-8"))
            if dato.get("error"):
                raise ErroreOllama(spiega(dato["error"]))
            stato = dato.get("status", "")
            if dato.get("total") and dato.get("completed"):
                stato += f" {dato['completed'] * 100 // dato['total']}%"
            yield f"{modello}: {stato}"
