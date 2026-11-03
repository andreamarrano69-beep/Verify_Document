"""Confronto tra più documenti dello stesso cliente.

I documenti vengono raggruppati per codice fiscale. Per ogni persona si verifica:

- stesso codice fiscale su tutti i documenti (identità coerente)
- buste paga: stessa azienda (P.IVA) e stessa data di assunzione, mesi doppi o mancanti,
  progressivi annui coerenti (progressivo del mese = progressivo precedente + imponibile del mese),
  netto e rapporto netto/lordo coerenti con gli altri mesi
- buste paga ↔ CU dello stesso anno: stesso datore di lavoro e data di assunzione, reddito e
  ritenute IRPEF uguali ai progressivi di dicembre (o compatibili con la media dei mesi)
- CU ↔ Modello Redditi: reddito da lavoro dipendente dichiarato = somma delle CU
- buste paga ↔ Modello Redditi dello stesso anno: reddito da lavoro dipendente compatibile
- più Modelli Redditi: andamento del reddito e cambi di regime
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from statistics import median

from .busta_paga import MESI
from .report import SIMBOLI, Esito, Report
from .validators import formatta_euro

TOLLERANZA_PROGRESSIVI = Decimal("1.00")
SCOSTAMENTO_NETTO = Decimal("0.25")       # ±25% rispetto alla mediana degli altri mesi
SCOSTAMENTO_RAPPORTO = Decimal("0.06")    # netto/lordo: ±6 punti percentuali
SCOSTAMENTO_REDDITI = Decimal("0.20")     # buste paga vs Modello Redditi: ±20%


@dataclass
class Documento:
    nome: str
    report: Report

    @property
    def tipo(self) -> str:
        t = self.report.tipo_documento
        if t == "Busta paga":
            return "busta"
        if t.startswith("Modello Redditi"):
            return "redditi"
        if t.startswith("Certificazione Unica"):
            return "cu"
        return "anagrafica"

    @property
    def codice_fiscale(self) -> str | None:
        d = self.report.dati
        return (d.get("codice_fiscale_dipendente") or d.get("codice_fiscale_contribuente")
                or d.get("codice_fiscale"))

    @property
    def anno_mese(self) -> tuple[int, int] | None:
        periodo = self.report.dati.get("periodo")
        if not periodo:
            return None
        nome, anno = periodo.lower().split()
        return int(anno), MESI.index(nome) + 1


@dataclass
class EsitoConfronto:
    report: Report
    tabelle: dict[str, list[dict]] = field(default_factory=dict)  # CF -> righe buste paga


def confronta(documenti: list[tuple[str, Report]]) -> EsitoConfronto:
    docs = [Documento(n, r) for n, r in documenti if r is not None]
    r = Report("Confronto documenti")
    esito = EsitoConfronto(r)
    r.dati["documenti_confrontati"] = len(docs)

    persone: dict[str, list[Documento]] = {}
    senza_cf = []
    for doc in docs:
        cf = doc.codice_fiscale
        if cf:
            persone.setdefault(cf, []).append(doc)
        else:
            senza_cf.append(doc)
    r.dati["persone"] = list(persone)

    gruppo_generale = "Identità"
    if len(docs) < 2:
        r.aggiungi("Documenti", Esito.ATTENZIONE, "Servono almeno 2 documenti per il confronto",
                   gruppo=gruppo_generale)
        return esito
    if len(persone) == 1:
        cf = next(iter(persone))
        r.aggiungi("Codice fiscale", Esito.OK,
                   f"Tutti i documenti con CF si riferiscono a {cf}", gruppo=gruppo_generale)
    elif len(persone) > 1:
        dettaglio = "; ".join(f"{cf}: {', '.join(d.nome for d in ds)}" for cf, ds in persone.items())
        r.aggiungi("Codice fiscale", Esito.ATTENZIONE,
                   f"Documenti di {len(persone)} persone diverse (confrontati separatamente) — {dettaglio}",
                   gruppo=gruppo_generale)
    if senza_cf:
        r.aggiungi("Documenti senza CF", Esito.ATTENZIONE,
                   "Esclusi dal confronto: " + ", ".join(d.nome for d in senza_cf), gruppo=gruppo_generale)

    for cf, ds in persone.items():
        gruppo = f"Cliente {cf}"
        buste = [d for d in ds if d.tipo == "busta"]
        redditi = [d for d in ds if d.tipo == "redditi"]
        certificazioni = [d for d in ds if d.tipo == "cu"]
        tipi = sorted({d.report.tipo_documento for d in ds})
        r.aggiungi("Documenti", Esito.INFO, f"{len(ds)}: {', '.join(tipi)}", gruppo=gruppo)
        if buste:
            esito.tabelle[cf] = _confronta_buste(r, buste, gruppo)
        if buste and certificazioni:
            _buste_vs_cu(r, buste, certificazioni, gruppo)
        if certificazioni and redditi:
            _cu_vs_redditi(r, certificazioni, redditi, gruppo)
        if buste and redditi:
            _buste_vs_redditi(r, buste, redditi, gruppo)
        if len(redditi) > 1:
            _confronta_redditi(r, redditi, gruppo)
    return esito


# --- Buste paga -------------------------------------------------------------------------

def _uguali(r: Report, buste: list[Documento], chiave: str, nome: str, gruppo: str,
            esito_diverso: Esito, spiegazione: str) -> None:
    valori: dict[str, list[str]] = {}
    for b in buste:
        v = b.report.dati.get(chiave)
        if v is not None:
            testo = v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else str(v)
            valori.setdefault(testo, []).append(b.nome)
    if len(valori) == 1:
        r.aggiungi(nome, Esito.OK, f"Uguale su tutte le buste paga: {next(iter(valori))}", gruppo=gruppo)
    elif len(valori) > 1:
        dettaglio = "; ".join(f"{v} ({', '.join(n)})" for v, n in valori.items())
        r.aggiungi(nome, esito_diverso, f"Valori diversi: {dettaglio} — {spiegazione}", gruppo=gruppo)


def _confronta_buste(r: Report, buste: list[Documento], gruppo: str) -> list[dict]:
    _uguali(r, buste, "partita_iva_azienda", "Azienda (P.IVA)", gruppo, Esito.ATTENZIONE,
            "cambio di datore di lavoro o documento alterato")
    stessa_azienda = len({b.report.dati.get("partita_iva_azienda") for b in buste} - {None}) <= 1
    _uguali(r, buste, "data_assunzione", "Data assunzione", gruppo,
            Esito.ERRORE if stessa_azienda else Esito.ATTENZIONE,
            "con la stessa azienda deve restare uguale" if stessa_azienda else "aziende diverse")

    con_periodo = sorted((b for b in buste if b.anno_mese), key=lambda b: b.anno_mese)
    senza = [b.nome for b in buste if not b.anno_mese]
    if senza:
        r.aggiungi("Periodo", Esito.ATTENZIONE, "Periodo non trovato in: " + ", ".join(senza), gruppo=gruppo)

    ordinarie = [b for b in con_periodo if not b.report.dati.get("mensilita_aggiuntiva")]

    # Mesi doppi e mancanti
    visti: dict[tuple, Documento] = {}
    for b in ordinarie:
        if b.anno_mese in visti:
            altra = visti[b.anno_mese]
            n1, n2 = altra.report.dati.get("netto"), b.report.dati.get("netto")
            stesso = n1 == n2
            r.aggiungi("Mese duplicato", Esito.ATTENZIONE if stesso else Esito.ERRORE,
                       f"{b.report.dati['periodo']} presente due volte ({altra.nome}, {b.nome})"
                       + ("" if stesso else f" con netto diverso: {formatta_euro(n1)} / {formatta_euro(n2)}"),
                       gruppo=gruppo)
        visti[b.anno_mese] = b
    mesi = sorted(visti)
    if len(mesi) >= 2:
        mancanti = []
        a, m = mesi[0]
        while (a, m) < mesi[-1]:
            if (a, m) not in visti:
                mancanti.append(f"{MESI[m - 1].capitalize()} {a}")
            a, m = (a + 1, 1) if m == 12 else (a, m + 1)
        if mancanti:
            r.aggiungi("Mesi mancanti", Esito.INFO, ", ".join(mancanti), gruppo=gruppo)
        else:
            r.aggiungi("Continuità mesi", Esito.OK,
                       f"{len(mesi)} mesi consecutivi da {MESI[mesi[0][1] - 1].capitalize()} {mesi[0][0]} "
                       f"a {MESI[mesi[-1][1] - 1].capitalize()} {mesi[-1][0]}", gruppo=gruppo)

    _progressivi(r, [visti[k] for k in mesi], gruppo)
    _arrotondamenti(r, [visti[k] for k in mesi], gruppo)
    _andamento_netto(r, [visti[k] for k in mesi], gruppo)

    righe = []
    for b in con_periodo:
        d = b.report.dati
        lordo, netto = d.get("totale_competenze"), d.get("netto")
        righe.append({
            "file": b.nome,
            "periodo": d.get("periodo") + (" (13ª/14ª)" if d.get("mensilita_aggiuntiva") else ""),
            "lordo": lordo,
            "netto": netto,
            "netto_su_lordo": (netto / lordo * 100).quantize(Decimal("0.1")) if lordo and netto else None,
            "imponibile_fiscale": d.get("imponibile_fiscale"),
            "progressivo_imponibile_fiscale": d.get("progressivo_imponibile_fiscale"),
            "esito": b.report.esito_globale.value,
        })
    return righe


def _progressivi(r: Report, buste: list[Documento], gruppo: str) -> None:
    """Progressivo imponibile fiscale del mese = progressivo del mese prima + imponibile del mese."""
    controllati, errori = 0, []
    for prec, att in zip(buste, buste[1:]):
        (a1, m1), (a2, m2) = prec.anno_mese, att.anno_mese
        p1 = prec.report.dati.get("progressivo_imponibile_fiscale")
        p2 = att.report.dati.get("progressivo_imponibile_fiscale")
        imp = att.report.dati.get("imponibile_fiscale")
        if None in (p1, p2):
            continue
        if a1 != a2:  # a gennaio i progressivi ripartono
            continue
        controllati += 1
        if p2 < p1:
            errori.append(f"{att.report.dati['periodo']}: progressivo {formatta_euro(p2)} inferiore al mese "
                          f"precedente {formatta_euro(p1)}")
        elif m2 == m1 + 1 and imp is not None and abs(p2 - p1 - imp) > TOLLERANZA_PROGRESSIVI:
            errori.append(f"{att.report.dati['periodo']}: {formatta_euro(p1)} + {formatta_euro(imp)} = "
                          f"{formatta_euro(p1 + imp)}, ma il progressivo indicato è {formatta_euro(p2)}")
    # gennaio: progressivo = imponibile del mese
    for b in buste:
        d = b.report.dati
        if b.anno_mese[1] == 1 and d.get("progressivo_imponibile_fiscale") is not None \
                and d.get("imponibile_fiscale") is not None:
            controllati += 1
            if abs(d["progressivo_imponibile_fiscale"] - d["imponibile_fiscale"]) > TOLLERANZA_PROGRESSIVI:
                errori.append(f"{d['periodo']}: a gennaio il progressivo deve essere uguale all'imponibile del mese")
    if errori:
        r.aggiungi("Progressivi annui", Esito.ERRORE, " | ".join(errori), gruppo=gruppo)
    elif controllati:
        r.aggiungi("Progressivi annui", Esito.OK,
                   f"Imponibile fiscale progressivo coerente mese per mese ({controllati} passaggi verificati)",
                   gruppo=gruppo)
    elif len(buste) >= 2:
        r.aggiungi("Progressivi annui", Esito.INFO, "Progressivi non trovati nelle buste paga", gruppo=gruppo)


def _consecutivi(b1: Documento, b2: Documento) -> bool:
    (a1, m1), (a2, m2) = b1.anno_mese, b2.anno_mese
    return (a2, m2) == ((a1 + 1, 1) if m1 == 12 else (a1, m1 + 1))


def _arrotondamenti(r: Report, buste: list[Documento], gruppo: str) -> None:
    """L'arrotondamento "precedente" di un mese è l'arrotondamento "attuale" del mese prima."""
    controllati, errori = 0, []
    for prec, att in zip(buste, buste[1:]):
        a = prec.report.dati.get("arrotondamento")
        p = att.report.dati.get("arrotondamento_precedente")
        if a is None or p is None or not _consecutivi(prec, att):
            continue
        controllati += 1
        if abs(a - p) > Decimal("0.01"):
            errori.append(f"{att.report.dati['periodo']}: arrotondamento precedente {formatta_euro(p)}, "
                          f"ma in {prec.report.dati['periodo']} l'attuale era {formatta_euro(a)}")
    if errori:
        r.aggiungi("Catena arrotondamenti", Esito.ATTENZIONE, " | ".join(errori), gruppo=gruppo)
    elif controllati:
        r.aggiungi("Catena arrotondamenti", Esito.OK,
                   f"Arrotondamenti riportati correttamente da un mese all'altro ({controllati})", gruppo=gruppo)


def _andamento_netto(r: Report, buste: list[Documento], gruppo: str) -> None:
    validi = [b for b in buste if b.report.dati.get("netto") and b.report.dati.get("totale_competenze")]
    if len(validi) < 3:
        return
    anomalie = []
    for b in validi:
        altri = [x for x in validi if x is not b]
        d = b.report.dati
        mediana_netto = Decimal(median([x.report.dati["netto"] for x in altri]))
        rapporti = [x.report.dati["netto"] / x.report.dati["totale_competenze"] for x in altri]
        mediana_rapporto = Decimal(median(rapporti))
        rapporto = d["netto"] / d["totale_competenze"]
        if abs(rapporto - mediana_rapporto) > SCOSTAMENTO_RAPPORTO:
            anomalie.append((Esito.ERRORE,
                             f"{d['periodo']}: il netto è il {rapporto * 100:.1f}% del lordo, negli altri mesi "
                             f"circa il {mediana_rapporto * 100:.1f}% (netto alterato senza ricalcolare il lordo?)"))
        elif abs(d["netto"] - mediana_netto) > mediana_netto * SCOSTAMENTO_NETTO:
            anomalie.append((Esito.ATTENZIONE,
                             f"{d['periodo']}: netto {formatta_euro(d['netto'])} lontano dagli altri mesi "
                             f"(mediana {formatta_euro(mediana_netto)}): straordinari, arretrati, assenze?"))
    if anomalie:
        peggiore = Esito.ERRORE if any(e == Esito.ERRORE for e, _ in anomalie) else Esito.ATTENZIONE
        r.aggiungi("Andamento netto", peggiore, " | ".join(t for _, t in anomalie), gruppo=gruppo)
    else:
        r.aggiungi("Andamento netto", Esito.OK,
                   f"Netto e rapporto netto/lordo coerenti su {len(validi)} mesi", gruppo=gruppo)


# --- Reddito annuo ricostruito dalle buste paga ----------------------------------------------

@dataclass
class AnnoDaBuste:
    reddito: Decimal
    irpef: Decimal | None
    metodo: str
    esatto: bool  # True se ricavato dai progressivi di dicembre


def _annuo_da_buste(buste: list[Documento], anno: int) -> AnnoDaBuste | None:
    dell_anno = [b for b in buste if b.anno_mese and b.anno_mese[0] == anno
                 and b.report.dati.get("imponibile_fiscale") is not None]
    if not dell_anno:
        return None
    # la busta di dicembre contiene i progressivi dell'intero anno (ultima, se ce n'è più d'una)
    dicembre = sorted((b for b in dell_anno if b.anno_mese[1] == 12
                       and b.report.dati.get("progressivo_imponibile_fiscale") is not None),
                      key=lambda b: b.report.dati["progressivo_imponibile_fiscale"])
    if dicembre:
        d = dicembre[-1].report.dati
        return AnnoDaBuste(d["progressivo_imponibile_fiscale"], d.get("progressivo_irpef"),
                           "progressivo di dicembre", True)
    ordinarie = [b for b in dell_anno if not b.report.dati.get("mensilita_aggiuntiva")]
    if not ordinarie:
        return None
    media = sum(b.report.dati["imponibile_fiscale"] for b in ordinarie) / len(ordinarie)
    return AnnoDaBuste((media * 13).quantize(Decimal("1")), None,
                       f"media di {len(ordinarie)} mesi × 13 mensilità (stima)", False)


def _scostamento(a: Decimal, b: Decimal) -> Decimal:
    return abs(a - b) / b if b else Decimal(1)


# --- Buste paga ↔ CU ---------------------------------------------------------------------------

def _buste_vs_cu(r: Report, buste: list[Documento], certificazioni: list[Documento], gruppo: str) -> None:
    for cu in certificazioni:
        dc = cu.report.dati
        anno, sostituto = dc.get("periodo_imposta"), dc.get("sostituto_imposta")
        if not anno:
            continue
        nome = f"Buste paga ↔ CU {anno}"
        # solo le buste dello stesso datore di lavoro (se la P.IVA è nota)
        stesse = [b for b in buste if not sostituto or not b.report.dati.get("partita_iva_azienda")
                  or b.report.dati["partita_iva_azienda"] == sostituto]
        altre = [b for b in buste if b not in stesse and b.anno_mese and b.anno_mese[0] == anno]
        if altre:
            r.aggiungi(f"Datore di lavoro {anno}", Esito.ATTENZIONE,
                       f"Buste paga di un'azienda diversa dal sostituto della CU ({sostituto}): "
                       + ", ".join(b.nome for b in altre), gruppo=gruppo)
        if dc.get("data_assunzione"):
            diverse = [b for b in stesse if b.report.dati.get("data_assunzione")
                       and b.report.dati["data_assunzione"] != dc["data_assunzione"]]
            if diverse:
                r.aggiungi(f"Data assunzione ↔ CU {anno}", Esito.ERRORE,
                           f"La CU indica inizio rapporto {dc['data_assunzione']:%d/%m/%Y}, diverso da: "
                           + ", ".join(f"{b.nome} ({b.report.dati['data_assunzione']:%d/%m/%Y})" for b in diverse),
                           gruppo=gruppo)
            elif any(b.report.dati.get("data_assunzione") for b in stesse):
                r.aggiungi(f"Data assunzione ↔ CU {anno}", Esito.OK,
                           f"Uguale su CU e buste paga: {dc['data_assunzione']:%d/%m/%Y}", gruppo=gruppo)
        annuo = _annuo_da_buste(stesse, anno)
        reddito_cu = dc.get("reddito_totale")
        if annuo is None or reddito_cu is None:
            continue
        diff = abs(annuo.reddito - reddito_cu)
        dettaglio = (f"CU {formatta_euro(reddito_cu)}, buste paga {formatta_euro(annuo.reddito)} "
                     f"({annuo.metodo})")
        if annuo.esatto:
            if diff <= TOLLERANZA_PROGRESSIVI:
                esito = Esito.OK
            elif _scostamento(annuo.reddito, reddito_cu) <= Decimal("0.02"):
                esito, dettaglio = Esito.ATTENZIONE, dettaglio + " — piccola differenza (conguagli?)"
            else:
                esito, dettaglio = Esito.ERRORE, dettaglio + f" — differenza {formatta_euro(diff)}"
        else:
            sc = _scostamento(annuo.reddito, reddito_cu)
            esito = Esito.OK if sc <= SCOSTAMENTO_REDDITI else Esito.ATTENZIONE
            dettaglio += f"; scostamento {sc * 100:.0f}%"
        r.aggiungi(nome, esito, dettaglio, gruppo=gruppo)

        rit = dc.get("ritenute_irpef")
        if annuo.esatto and annuo.irpef is not None and rit is not None:
            diff = abs(annuo.irpef - rit)
            esito = Esito.OK if diff <= TOLLERANZA_PROGRESSIVI else (
                Esito.ATTENZIONE if _scostamento(annuo.irpef, rit) <= Decimal("0.05") else Esito.ERRORE)
            r.aggiungi(f"IRPEF buste paga ↔ CU {anno}", esito,
                       f"Ritenute CU {formatta_euro(rit)}, progressivo IRPEF di dicembre {formatta_euro(annuo.irpef)}",
                       gruppo=gruppo)


# --- CU ↔ Modello Redditi ------------------------------------------------------------------------

def _cu_vs_redditi(r: Report, certificazioni: list[Documento], redditi: list[Documento], gruppo: str) -> None:
    for red in redditi:
        anno = red.report.dati.get("periodo_imposta")
        dichiarato = red.report.dati.get("reddito_dipendente")
        cu_anno = [c for c in certificazioni if c.report.dati.get("periodo_imposta") == anno
                   and c.report.dati.get("reddito_totale") is not None]
        if not anno or not cu_anno:
            continue
        certificato = sum((c.report.dati["reddito_totale"] for c in cu_anno), Decimal(0))
        nome = f"CU ↔ Redditi {anno}"
        if dichiarato is None:
            r.aggiungi(nome, Esito.ATTENZIONE,
                       f"CU per {formatta_euro(certificato)} ma nessun reddito da lavoro dipendente "
                       f"nel Modello Redditi ({red.nome})", gruppo=gruppo)
            continue
        dettaglio = (f"Dichiarato {formatta_euro(dichiarato)}, certificato da {len(cu_anno)} CU "
                     f"{formatta_euro(certificato)}")
        if abs(dichiarato - certificato) <= 1:
            r.aggiungi(nome, Esito.OK, dettaglio, gruppo=gruppo)
        elif dichiarato > certificato:
            r.aggiungi(nome, Esito.ATTENZIONE,
                       dettaglio + " — dichiarato più del certificato: manca una CU (altro datore) "
                       "o il reddito è stato gonfiato", gruppo=gruppo)
        else:
            r.aggiungi(nome, Esito.ATTENZIONE,
                       dettaglio + " — dichiarato meno del certificato", gruppo=gruppo)


# --- Buste paga ↔ Modello Redditi --------------------------------------------------------

def _buste_vs_redditi(r: Report, buste: list[Documento], redditi: list[Documento], gruppo: str) -> None:
    for red in redditi:
        anno = red.report.dati.get("periodo_imposta")
        reddito_dip = red.report.dati.get("reddito_dipendente")
        if not anno:
            continue
        annuo = _annuo_da_buste(buste, anno)
        if annuo is None:
            continue
        nome = f"Buste paga ↔ Redditi {anno}"
        if reddito_dip is None:
            r.aggiungi(nome, Esito.ATTENZIONE,
                       f"Ci sono buste paga del {anno} ma nel Modello Redditi ({red.nome}) "
                       "non risulta reddito da lavoro dipendente", gruppo=gruppo)
            continue
        sc = _scostamento(annuo.reddito, reddito_dip)
        dettaglio = (f"Dichiarato {formatta_euro(reddito_dip)}, dalle buste paga {formatta_euro(annuo.reddito)} "
                     f"({annuo.metodo}); scostamento {sc * 100:.0f}%")
        r.aggiungi(nome, Esito.OK if sc <= SCOSTAMENTO_REDDITI else Esito.ATTENZIONE, dettaglio, gruppo=gruppo)


def _confronta_redditi(r: Report, redditi: list[Documento], gruppo: str) -> None:
    anni = sorted((d for d in redditi if d.report.dati.get("periodo_imposta")),
                  key=lambda d: d.report.dati["periodo_imposta"])
    for prec, att in zip(anni, anni[1:]):
        dp, da = prec.report.dati, att.report.dati
        a1, a2 = dp["periodo_imposta"], da["periodo_imposta"]
        if dp.get("regime_fiscale") != da.get("regime_fiscale"):
            r.aggiungi(f"Regime {a1} → {a2}", Esito.INFO,
                       f"{dp.get('regime_fiscale')} → {da.get('regime_fiscale')}", gruppo=gruppo)
        r1, r2 = dp.get("reddito_annuo"), da.get("reddito_annuo")
        if r1 and r2:
            var = (r2 - r1) / abs(r1)
            esito = Esito.ATTENZIONE if abs(var) > Decimal("0.5") else Esito.OK
            r.aggiungi(f"Reddito {a1} → {a2}", esito,
                       f"{formatta_euro(r1)} → {formatta_euro(r2)} ({var * 100:+.0f}%)"
                       + (" — variazione molto forte, verificarne il motivo" if esito == Esito.ATTENZIONE else ""),
                       gruppo=gruppo)


# --- Output testuale -------------------------------------------------------------------------

def confronto_testuale(c: EsitoConfronto) -> str:
    r = c.report
    righe = ["#" * 72, f"CONFRONTO TRA {r.dati['documenti_confrontati']} DOCUMENTI", "#" * 72]
    for gruppo, controlli in r.gruppi().items():
        righe += ["", gruppo.upper()]
        for x in controlli:
            righe.append(f"  {SIMBOLI[x.esito]} {x.nome:<28} {x.dettaglio}")
        cf = gruppo.removeprefix("Cliente ")
        if cf in c.tabelle:
            righe += ["", f"  {'Periodo':<24}{'Lordo':>14}{'Netto':>14}{'Netto/lordo':>13}{'Progr. imp.':>16}"]
            for t in c.tabelle[cf]:
                nl = f"{t['netto_su_lordo']}%".replace(".", ",") if t["netto_su_lordo"] else "—"
                righe.append(f"  {t['periodo']:<24}{formatta_euro(t['lordo']):>14}{formatta_euro(t['netto']):>14}"
                             f"{nl:>13}{formatta_euro(t['progressivo_imponibile_fiscale']):>16}")
    righe += ["", f"ESITO CONFRONTO: {SIMBOLI[r.esito_globale]} {r.esito_globale.value}", ""]
    return "\n".join(righe)
