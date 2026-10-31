"""Generation d'une base SQLite simulant une usine pharma.

On injecte volontairement des causes de retard connues (panne machine,
rupture de stock, retard qualite) pour pouvoir evaluer le systeme ensuite.
"""
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "usine.db"

SCHEMA = """
CREATE TABLE machines (
    machine_id TEXT PRIMARY KEY,
    nom TEXT,
    ligne TEXT
);
CREATE TABLE ordres_fabrication (
    of_id INTEGER PRIMARY KEY,
    produit TEXT,
    machine_id TEXT REFERENCES machines(machine_id),
    date_prevue DATE,
    date_reelle DATE,          -- NULL si pas encore termine
    statut TEXT                -- 'termine', 'en_retard', 'en_cours'
);
CREATE TABLE incidents_machine (
    incident_id INTEGER PRIMARY KEY,
    machine_id TEXT REFERENCES machines(machine_id),
    date_incident DATE,
    duree_arret_h REAL,
    description TEXT
);
CREATE TABLE stocks_matieres (
    matiere TEXT,
    date_releve DATE,
    quantite_kg REAL,
    seuil_mini_kg REAL
);
CREATE TABLE nomenclature (
    produit TEXT,
    matiere TEXT,
    kg_par_lot REAL
);
CREATE TABLE controles_qualite (
    of_id INTEGER REFERENCES ordres_fabrication(of_id),
    resultat TEXT,             -- 'conforme', 'non_conforme', 'en_attente'
    commentaire TEXT
);
"""

MACHINES = [("M1", "Granulateur", "L1"), ("M2", "Presse a comprimes", "L1"),
            ("M3", "Pelliculeuse", "L2"), ("M4", "Blistereuse", "L2")]
PRODUITS = {"Doliprane 500": ["paracetamol", "amidon"],
            "Aspegic 1000": ["acetylsalicylate", "glycine"],
            "Lovenox 40": ["enoxaparine", "eau_ppi"]}

# Cas de retard injectes : of_id -> cause (sert de verite terrain pour l'eval)
CAUSES_CONNUES = {
    1042: "panne_machine",      # arret long de M3 juste avant la date prevue
    1043: "rupture_stock",      # enoxaparine sous le seuil
    1044: "qualite",            # controle non conforme
}


def build(seed: int = 42) -> Path:
    random.seed(seed)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO machines VALUES (?,?,?)", MACHINES)

    for produit, matieres in PRODUITS.items():
        for m in matieres:
            con.execute("INSERT INTO nomenclature VALUES (?,?,?)",
                        (produit, m, round(random.uniform(5, 40), 1)))

    debut = date(2026, 9, 1)
    # 40 OF "normaux" termines a l'heure
    for i in range(1000, 1040):
        produit = random.choice(list(PRODUITS))
        machine = random.choice(MACHINES)[0]
        prevue = debut + timedelta(days=random.randint(0, 40))
        con.execute("INSERT INTO ordres_fabrication VALUES (?,?,?,?,?,?)",
                    (i, produit, machine, prevue, prevue, "termine"))
        con.execute("INSERT INTO controles_qualite VALUES (?,?,?)",
                    (i, "conforme", ""))

    # Bruit : petits incidents sans impact
    for k in range(15):
        con.execute("INSERT INTO incidents_machine VALUES (?,?,?,?,?)",
                    (k, random.choice(MACHINES)[0],
                     debut + timedelta(days=random.randint(0, 50)),
                     round(random.uniform(0.2, 1.0), 1), "Micro-arret, reprise immediate"))

    # Cas 1042 : panne longue de M3
    con.execute("INSERT INTO ordres_fabrication VALUES (1042,'Aspegic 1000','M3','2026-10-20',NULL,'en_retard')")
    con.execute("INSERT INTO incidents_machine VALUES (100,'M3','2026-10-19',6.0,'Casse du tambour de pelliculage, attente piece de rechange')")
    con.execute("INSERT INTO controles_qualite VALUES (1042,'en_attente','')")

    # Cas 1043 : rupture de stock enoxaparine
    con.execute("INSERT INTO ordres_fabrication VALUES (1043,'Lovenox 40','M2','2026-10-22',NULL,'en_retard')")
    con.execute("INSERT INTO controles_qualite VALUES (1043,'en_attente','')")

    # Cas 1044 : non-conformite qualite
    con.execute("INSERT INTO ordres_fabrication VALUES (1044,'Doliprane 500','M1','2026-10-21',NULL,'en_retard')")
    con.execute("INSERT INTO controles_qualite VALUES (1044,'non_conforme','Durete des comprimes hors specification')")

    # Stocks : tout est OK sauf l'enoxaparine
    for matiere in {m for ms in PRODUITS.values() for m in ms}:
        qte = 3.0 if matiere == "enoxaparine" else round(random.uniform(200, 500), 1)
        con.execute("INSERT INTO stocks_matieres VALUES (?,?,?,?)",
                    (matiere, "2026-10-21", qte, 50.0))

    con.commit()
    con.close()
    return DB_PATH


if __name__ == "__main__":
    print("Base creee :", build())
