import os
import csv
import time
import requests
from pathlib import Path
from datetime import date, timedelta
from garminconnect import Garmin

EMAIL    = os.environ["GARMIN_EMAIL"]
PASSWORD = os.environ["GARMIN_PASSWORD"]
FLASK_URL = os.environ.get("FLASK_UPLOAD_URL", "")  # ajout

OUTPUT = Path("data/garmin_activities.csv")
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

FIELDS = [
    "activityId", "activityName", "activityType",
    "startTimeLocal", "distance", "duration",
    "averageHR", "maxHR", "calories",
    "averageSpeed", "maxSpeed", "elevationGain",
]

def download_existing_csv(url: str, path: Path):
    """Récupère le CSV actuel depuis Flask pour ne pas perdre l'historique."""
    try:
        r = requests.get(f"{url}/download/garmin_activities.csv", timeout=15)
        if r.status_code == 200:
            path.write_bytes(r.content)
            print(f"📥 CSV existant récupéré ({len(r.content)} bytes)")
        elif r.status_code == 404:
            print("ℹ️  Pas de CSV existant sur le serveur, premier run.")
        else:
            print(f"⚠️  Réponse inattendue : {r.status_code}")
    except Exception as e:
        print(f"⚠️  Impossible de récupérer le CSV existant : {e}")

def load_existing(path: Path) -> tuple[list[dict], set]:
    if not path.exists():
        return [], set()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    ids = {r["activityId"] for r in rows}
    return rows, ids

def fetch_new_activities(client: Garmin, existing_ids: set) -> list[dict]:
    start = date.today() - timedelta(days=30)
    activities = client.get_activities_by_date(start.isoformat(), date.today().isoformat())
    new = []
    for act in activities:
        aid = str(act.get("activityId", ""))
        if aid and aid not in existing_ids:
            row = {f: act.get(f, "") for f in FIELDS}
            if isinstance(row["activityType"], dict):
                row["activityType"] = row["activityType"].get("typeKey", "")
            new.append(row)
    return new

def save_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

def login_with_retry(client: Garmin, retries: int = 3, delay: int = 10):
    for attempt in range(retries):
        try:
            client.login()
            return
        except Exception as e:
            if "429" in str(e) and attempt < retries - 1:
                print(f"⚠️  Rate limited, retry dans {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                raise

def main():
    # 1. Récupérer l'historique existant depuis Flask
    if FLASK_URL:
        download_existing_csv(FLASK_URL, OUTPUT)

    # 2. Charger les IDs déjà connus
    existing_rows, existing_ids = load_existing(OUTPUT)
    print(f"📂 {len(existing_rows)} activité(s) déjà en base")

    # 3. Login Garmin et fetch des nouvelles
    client = Garmin(EMAIL, PASSWORD)
    login_with_retry(client)
    new_rows = fetch_new_activities(client, existing_ids)

    # 4. Merger et sauvegarder
    if new_rows:
        print(f"✅ {len(new_rows)} nouvelle(s) activité(s) trouvée(s)")
        all_rows = existing_rows + new_rows
        all_rows.sort(key=lambda r: r.get("startTimeLocal", ""), reverse=True)
        save_csv(OUTPUT, all_rows)
    else:
        print("ℹ️  Aucune nouvelle activité.")

if __name__ == "__main__":
    main()
