def fetch_all_activities(client: Garmin) -> list[dict]:
    """Récupère TOUT l'historique Garmin (par batch de 100)."""
    all_activities = []
    start = 0
    batch = 100
    print("🔄 Fetch complet de l'historique...")
    while True:
        chunk = client.get_activities(start, batch)
        if not chunk:
            break
        all_activities.extend(chunk)
        print(f"   → {len(all_activities)} activités récupérées...")
        start += batch
        time.sleep(1)  # évite le rate limit
    return all_activities

def fetch_new_activities(client: Garmin, existing_ids: set) -> list[dict]:
    """Récupère uniquement les activités des 30 derniers jours non connues."""
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

def normalize_activity(act: dict) -> dict:
    row = {f: act.get(f, "") for f in FIELDS}
    if isinstance(row["activityType"], dict):
        row["activityType"] = row["activityType"].get("typeKey", "")
    return row

def main():
    # 1. Récupérer l'historique existant depuis Flask
    if FLASK_URL:
        download_existing_csv(FLASK_URL, OUTPUT)

    existing_rows, existing_ids = load_existing(OUTPUT)
    print(f"📂 {len(existing_rows)} activité(s) déjà en base")

    client = Garmin(EMAIL, PASSWORD)
    login_with_retry(client)

    # 2. Premier run (CSV vide) → fetch complet, sinon fetch 30 jours
    if not existing_ids:
        print("🚀 Premier run détecté — récupération de tout l'historique")
        raw = fetch_all_activities(client)
        new_rows = [normalize_activity(a) for a in raw]
    else:
        new_rows = fetch_new_activities(client, existing_ids)

    # 3. Merger et sauvegarder
    if new_rows:
        print(f"✅ {len(new_rows)} nouvelle(s) activité(s) trouvée(s)")
        all_rows = existing_rows + new_rows
        all_rows.sort(key=lambda r: r.get("startTimeLocal", ""), reverse=True)
        save_csv(OUTPUT, all_rows)
    else:
        print("ℹ️  Aucune nouvelle activité.")

if __name__ == "__main__":
    main()
