import os
import time
import csv
import pickle
import sys
import requests
import garminconnect
from pathlib import Path

# ======================
# CONFIG
# ======================

GARMIN_USERNAME = os.getenv("GARMIN_USERNAME")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")

BASE_URL = "https://SitePaul.pythonanywhere.com"
DOWNLOAD_URL = f"{BASE_URL}/download/garmin_activities.csv"
UPLOAD_URL = f"{BASE_URL}/upload"

SESSION_FILE = Path("garmin_session.pkl")
LOCAL_CSV = "garmin_activities.csv"
LOCK_FILE = "/tmp/garmin_job.lock"

RATE_LIMIT_FILE = "garmin_rate_limit.lock"

PAGE_LIMIT = 20

# ======================
# RATE LIMIT HANDLING
# ======================

def is_rate_limited():
    if not os.path.exists(RATE_LIMIT_FILE):
        return False

    try:
        with open(RATE_LIMIT_FILE, "r") as f:
            ts = float(f.read())
        return (time.time() - ts) < 3600  # 1h cooldown
    except:
        return False


def set_rate_limited():
    with open(RATE_LIMIT_FILE, "w") as f:
        f.write(str(time.time()))


# ======================
# LOCK
# ======================

def acquire_lock():
    if os.path.exists(LOCK_FILE):
        print("Job already running — exit")
        sys.exit(0)
    open(LOCK_FILE, "w").close()


def release_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)


# ======================
# DOWNLOAD CSV (source of truth)
# ======================

def download_existing_csv():
    try:
        r = requests.get(DOWNLOAD_URL, timeout=30)

        if r.status_code == 200:
            with open(LOCAL_CSV, "wb") as f:
                f.write(r.content)
            print("CSV downloaded")
        else:
            print("No remote CSV found — starting fresh")

    except Exception as e:
        print(f"Download error: {e}")


def load_existing_ids():
    ids = set()

    if not os.path.exists(LOCAL_CSV):
        return ids

    with open(LOCAL_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ids.add(str(row["Activity ID"]))

    print(f"{len(ids)} existing activities loaded")
    return ids


# ======================
# GARMIN SESSION (STABLE)
# ======================

def get_garmin_client():
    if is_rate_limited():
        print("🚫 Global rate limit active — skipping Garmin")
        return None

    client = garminconnect.Garmin(GARMIN_USERNAME, GARMIN_PASSWORD)

    # reuse session
    if SESSION_FILE.exists():
        try:
            with open(SESSION_FILE, "rb") as f:
                client = pickle.load(f)
            print("Session reused")
            return client
        except:
            print("Session invalid")

    # only minimal login attempts
    for _ in range(2):  # VERY IMPORTANT: low retry
        try:
            client.login()

            with open(SESSION_FILE, "wb") as f:
                pickle.dump(client, f)

            print("Login success")
            return client

        except garminconnect.GarminConnectTooManyRequestsError:
            print("🚫 Garmin SSO blocked (429)")
            set_rate_limited()
            return None

        except Exception as e:
            print(f"Login error: {e}")
            time.sleep(5)

    return None


# ======================
# FETCH INCREMENTAL DATA
# ======================

def fetch_new_activities(existing_ids):
    client = get_garmin_client()

    if client is None:
        print("Skipping fetch (no Garmin access)")
        return []

    start = 0
    new_activities = []

    while True:
        try:
            activities = client.get_activities(start, PAGE_LIMIT)

        except garminconnect.GarminConnectTooManyRequestsError:
            print("🚫 Rate limit during fetch")
            set_rate_limited()
            break

        except Exception as e:
            print(f"Fetch error: {e}")
            break

        if not activities:
            break

        for a in activities:
            aid = str(a.get("activityId"))

            if aid in existing_ids:
                print("Reached known activity — stop")
                return new_activities

            new_activities.append(a)

        start += PAGE_LIMIT

    print(f"{len(new_activities)} new activities")
    return new_activities


# ======================
# CSV MERGE
# ======================

def merge_csv(new_activities):
    rows = []

    if os.path.exists(LOCAL_CSV):
        with open(LOCAL_CSV, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))

    header = [
        "Activity ID",
        "Activity Name",
        "Start Time",
        "Duration (s)",
        "Distance (m)",
        "Average Speed (m/s)",
        "Calories"
    ]

    if not rows:
        rows.append(header)

    for a in reversed(new_activities):
        rows.append([
            a.get("activityId"),
            a.get("activityName"),
            a.get("startTimeLocal"),
            a.get("duration"),
            a.get("distance"),
            a.get("averageSpeed"),
            a.get("calories")
        ])

    with open(LOCAL_CSV, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

    print("CSV updated")


# ======================
# UPLOAD
# ======================

def upload():
    try:
        with open(LOCAL_CSV, "rb") as f:
            r = requests.post(UPLOAD_URL, files={"file": f}, timeout=30)

        if r.status_code == 200:
            print("Upload OK")
        else:
            print(f"Upload error: {r.text}")

    except Exception as e:
        print(f"Upload failed: {e}")


# ======================
# MAIN
# ======================

def main():
    acquire_lock()

    try:
        download_existing_csv()
        existing_ids = load_existing_ids()

        new_activities = fetch_new_activities(existing_ids)

        if not new_activities:
            print("No update — exit cleanly")
            return

        merge_csv(new_activities)
        upload()

    finally:
        release_lock()


if __name__ == "__main__":
    main()
