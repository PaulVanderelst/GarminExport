import os
import csv
import time
import requests
from pathlib import Path
from datetime import date, datetime
from garminconnect import Garmin

EMAIL     = os.environ["GARMIN_EMAIL"]
PASSWORD  = os.environ["GARMIN_PASSWORD"]
FLASK_URL = os.environ.get("FLASK_UPLOAD_URL", "")

OUTPUT = Path("data/garmin_activities.csv")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

FIELDS = [
    "activityId", "activityName", "activityType",
    "startTimeLocal", "distance", "duration",
    "averageHR", "maxHR", "calories",
    "averageSpeed", "maxSpeed", "elevationGain",
]


# ─── I/O ──────────────────────────────────────────────────────────────────────

def download_existing_csv(url: str, path: Path):
    """Télécharge le CSV depuis Flask pour préserver l'historique."""
    try:
        r = requests.get(f"{url}/download/garmin_activities.csv", timeout=15)
        if r.status_code == 200:
            path.write_bytes(r.content)
            print(f"📥 CSV récupéré depuis Flask ({len(r.content)} bytes)")
        elif r.status_code == 404:
            print("ℹ️  Aucun CSV sur le serveur — premier run.")
        else:
            print(f"⚠️  Réponse inattendue du serveur : {r.status_code}")
    except Exception as e:
        print(f"⚠️  Impossible de récupérer le CSV : {e}")


def load_existing(path: Path) -> tuple[list[dict], set]:
    if not path.exists():
        return [], set()
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    ids = {r["activityId"] for r in rows if r.get("activityId")}
    return rows, ids


def save_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


# ─── Garmin ───────────────────────────────────────────────────────────────────

def login_with_retry(client: Garmin, retries: int = 3, delay: int = 10):
    for attempt in range(retries):
        try:
            client.login()
            print("🔐 Connecté à Garmin Connect")
            return
        except Exception as e:
            if "429" in str(e) and attempt < retries - 1:
                print(f"⚠️  Rate limited, retry dans {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                raise


def normalize(act: dict) -> dict:
    row = {f: act.get(f, "") for f in FIELDS}
    if isinstance(row["activityType"], dict):
        row["activityType"] = row["activityType"].get("typeKey", "")
    row["activityId"] = str(row["activityId"])
    return row


def find_oldest_missing_date(client: Garmin, existing_ids: set) -> date | None:
    """
    Parcourt l'historique Garmin par batch de 100 (du plus récent au plus ancien)
    et retourne la date de la première activité absente du CSV.
    S'arrête dès qu'une activité connue est trouvée — minimise les requêtes.
    """
    start = 0
    batch = 100
    oldest_missing_date = None

    print("🔍 Recherche des activités manquantes...")

    while True:
        chunk = client.get_activities(start, batch)
        if not chunk:
            break

        found_known = False
        for act in chunk:
            aid = str(act.get("activityId", ""))
            raw_date = act.get("startTimeLocal", "")
            act_date = datetime.fromisoformat(raw_date).date() if raw_date else None

            if aid not in existing_ids:
                # Activité manquante — on retient la plus ancienne trouvée
                if act_date and (oldest_missing_date is None or act_date < oldest_missing_date):
                    oldest_missing_date = act_date
            else:
                # Activité déjà connue dans ce batch → historique rattrapé
                found_known = True

        if found_known and oldest_missing_date is not None:
            # On a trouvé à la fois des manquantes ET une connue dans ce batch :
            # inutile d'aller plus loin dans le passé
            break

        if found_known and oldest_missing_date is None:
            # Toutes les activités de ce batch sont déjà connues
            break

        start += batch
        time.sleep(0.5)  # pause légère entre chaque requête

    return oldest_missing_date


def fetch_activities_since(client: Garmin, since: date, existing_ids: set) -> list[dict]:
    """Fetch toutes les activités depuis `since` et filtre celles déjà connues."""
    print(f"📡 Fetch des activités depuis le {since}...")
    raw = client.get_activities_by_date(since.isoformat(), date.today().isoformat())
    new = []
    for act in raw:
        aid = str(act.get("activityId", ""))
        if aid and aid not in existing_ids:
            new.append(normalize(act))
    return new


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    # 1. Récupérer le CSV actuel depuis Flask
    if FLASK_URL:
        download_existing_csv(FLASK_URL, OUTPUT)

    existing_rows, existing_ids = load_existing(OUTPUT)
    print(f"📂 {len(existing_rows)} activité(s) déjà en base")

    # 2. Login Garmin
    client = Garmin(EMAIL, PASSWORD)
    login_with_retry(client)

    # 3. Trouver la date de la première activité manquante
    oldest_missing = find_oldest_missing_date(client, existing_ids)

    if oldest_missing is None:
        print("✅ Tout est à jour, aucune nouvelle activité.")
        return

    print(f"📅 Première activité manquante détectée : {oldest_missing}")

    # 4. Fetch depuis cette date uniquement
    new_rows = fetch_activities_since(client, oldest_missing, existing_ids)

    if not new_rows:
        print("ℹ️  Aucune nouvelle activité après filtrage.")
        return

    print(f"✅ {len(new_rows)} nouvelle(s) activité(s) à ajouter")

    # 5. Merger, trier, sauvegarder
    all_rows = existing_rows + new_rows
    all_rows.sort(key=lambda r: r.get("startTimeLocal", ""), reverse=True)
    save_csv(OUTPUT, all_rows)
    print(f"💾 CSV sauvegardé ({len(all_rows)} activités au total)")


if __name__ == "__main__":
    main()
