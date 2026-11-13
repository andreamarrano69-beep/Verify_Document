"""Assistente AI facoltativo: domande sui documenti OAM e Compass dell'ufficio, con Ollama in locale.

Se Ollama non è installato (o non è raggiungibile) il resto del programma funziona normalmente:
solo le funzioni dell'assistente restano disattivate.

- ollama_http.py  collegamento a Ollama (API HTTP, nessuna libreria in più)
- rag.py          lettura dei documenti, indice condiviso, ricerca e risposta
- scarica.py      scarica i documenti pubblici da OAM e Compass
- finestra.py     finestra «Assistente AI»
"""
