"""Pulizia delle immagini prima dell'OCR (scansioni e foto di buste paga, CU, ecc.).

1. orientamento: pagina girata di 90°/180° (rilevata da Tesseract)
2. ingrandimento fino a ~300 DPI equivalenti (A4 largo almeno 2480 pixel)
3. raddrizzamento della pagina leggermente storta (fino a ±5°)
4. sfondo uniforme: toglie ombre, carta grigia, macchie di luce delle foto
5. bianco e nero (soglia di Otsu)
6. rimozione delle linee della griglia delle tabelle, che confondono l'OCR
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter, ImageOps

LARGHEZZA_MINIMA = 2480  # pixel: A4 a 300 DPI


@dataclass
class Varianti:
    grigia: Image.Image   # raddrizzata, in scala di grigi
    pulita: Image.Image   # bianco e nero, senza linee
    fattore: float        # ingrandimento rispetto all'originale
    angolo: float         # gradi di raddrizzamento applicati


def _otsu(a: np.ndarray) -> int:
    istogramma = np.bincount(a.ravel(), minlength=256).astype(float)
    totale = a.size
    somma = np.dot(np.arange(256), istogramma)
    peso_b = somma_b = 0.0
    migliore, soglia = -1.0, 128
    for t in range(256):
        peso_b += istogramma[t]
        if peso_b == 0:
            continue
        peso_f = totale - peso_b
        if peso_f == 0:
            break
        somma_b += t * istogramma[t]
        media_b, media_f = somma_b / peso_b, (somma - somma_b) / peso_f
        varianza = peso_b * peso_f * (media_b - media_f) ** 2
        if varianza > migliore:
            migliore, soglia = varianza, t
    return soglia


def _orienta(img: Image.Image, pytesseract) -> Image.Image:
    """Ruota di 90/180/270° se Tesseract rileva che la pagina è girata."""
    try:
        piccola = img.copy()
        piccola.thumbnail((1600, 1600))
        osd = pytesseract.image_to_osd(piccola, config="--psm 0 -c min_characters_to_try=10")
        m = re.search(r"Rotate:\s*(\d+)", osd)
        conf = re.search(r"Orientation confidence:\s*([\d.]+)", osd)
        if m and int(m.group(1)) and (not conf or float(conf.group(1)) >= 2.0):
            return img.rotate(-int(m.group(1)), expand=True, fillcolor=255)
    except Exception:
        pass  # poco testo o dati "osd" mancanti: si lascia com'è
    return img


def _angolo_inclinazione(img: Image.Image) -> float:
    """Stima l'inclinazione: l'angolo per cui le righe di testo sono più "nette" (varianza delle proiezioni)."""
    piccola = img.copy()
    piccola.thumbnail((1000, 1400))
    a = np.asarray(piccola)
    inchiostro = Image.fromarray(((a < _otsu(a)) * 255).astype(np.uint8))

    def nettezza(angolo):
        r = np.asarray(inchiostro.rotate(angolo, resample=Image.NEAREST, fillcolor=0), dtype=np.float32)
        return float(np.var(r.sum(axis=1)))

    migliore = max(np.arange(-5, 5.01, 1.0), key=nettezza)
    migliore = max(np.arange(migliore - 0.8, migliore + 0.81, 0.2), key=nettezza)
    return float(round(migliore, 2))


def _sfondo_uniforme(img: Image.Image) -> Image.Image:
    """Divide per lo sfondo stimato (ombre e carta grigia diventano bianco)."""
    piccola = img.resize((max(img.width // 8, 1), max(img.height // 8, 1)), Image.BILINEAR)
    sfondo = piccola.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(3)).resize(img.size, Image.BILINEAR)
    a = np.asarray(img, dtype=np.float32)
    s = np.maximum(np.asarray(sfondo, dtype=np.float32), 1.0)
    return Image.fromarray(np.clip(a / s * 255.0, 0, 255).astype(np.uint8))


def _segmenti_lunghi(maschera: np.ndarray, lunghezza: int) -> np.ndarray:
    """Pixel appartenenti a tratti continui (in orizzontale) lunghi almeno ``lunghezza``."""
    righe, colonne = maschera.shape
    if colonne < lunghezza:
        return np.zeros_like(maschera)
    cum = np.zeros((righe, colonne + 1), dtype=np.int32)
    np.cumsum(maschera, axis=1, out=cum[:, 1:])
    pieni = (cum[:, lunghezza:] - cum[:, :-lunghezza]) == lunghezza   # inizio di un tratto pieno
    cum2 = np.zeros((righe, pieni.shape[1] + 1), dtype=np.int32)
    np.cumsum(pieni, axis=1, out=cum2[:, 1:])
    x = np.arange(colonne)
    inizio = np.clip(x - lunghezza + 1, 0, pieni.shape[1])
    fine = np.clip(x + 1, 0, pieni.shape[1])
    return (cum2[:, fine] - cum2[:, inizio]) > 0


def _togli_linee(inchiostro: np.ndarray) -> np.ndarray:
    h, w = inchiostro.shape
    orizzontali = _segmenti_lunghi(inchiostro, max(w // 25, 40))
    verticali = _segmenti_lunghi(inchiostro.T, max(h // 40, 40)).T
    return inchiostro & ~orizzontali & ~verticali


def prepara_per_ocr(grigia: Image.Image, pytesseract=None, lingua: str = "") -> Varianti:
    img = ImageOps.exif_transpose(grigia).convert("L")
    if pytesseract is not None:
        img = _orienta(img, pytesseract)
    fattore = 1.0
    if img.width < LARGHEZZA_MINIMA:
        fattore = LARGHEZZA_MINIMA / img.width
        img = img.resize((LARGHEZZA_MINIMA, int(img.height * fattore)), Image.LANCZOS)
    img = ImageOps.autocontrast(img, cutoff=1)
    angolo = _angolo_inclinazione(img)
    if abs(angolo) >= 0.2:
        img = img.rotate(angolo, resample=Image.BICUBIC, expand=False, fillcolor=255)
    uniforme = _sfondo_uniforme(img)
    a = np.asarray(uniforme)
    inchiostro = a < _otsu(a)
    pulito = _togli_linee(inchiostro)
    pulita = Image.fromarray(np.where(pulito, 0, 255).astype(np.uint8))
    pulita = pulita.filter(ImageFilter.MedianFilter(3))  # puntini di rumore
    return Varianti(grigia=uniforme, pulita=pulita, fattore=fattore, angolo=angolo)
