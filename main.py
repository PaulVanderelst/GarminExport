import garminconnect
import csv
import requests

# Define your Garmin credentials
GARMIN_USERNAME = "paul.vanderelst@hotmail.com"
GARMIN_PASSWORD = "Polar7500"

# Define the Flask upload endpoint on PythonAnywhere
PYTHONANYWHERE_UPLOAD_URL = "https://SitePaul.pythonanywhere.com/upload"


def export_garmin_activities():
    try:
        # Authenticate with Garmin
        client = garminconnect.Garmin(GARMIN_USERNAME, GARMIN_PASSWORD)
        client.login()
        print("Login successful!")

        # Fetch activities
        activities = client.get_activities(0, 1000)  # Adjust range as needed (start=0, limit=1000)

        # Define the local output file
        output_file = "garmin_activities.csv"

        # Export activities to a CSV file
        with open(output_file, mode="w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            # Write header
            writer.writerow([
                "Activity ID", "Activity Name", "Start Time", "Duration (s)",
                "Distance (m)", "Average Speed (m/s)", "Calories"
            ])
            # Write activity data
            for activity in activities[:-1]:
                writer.writerow([
                    activity["activityId"],
                    activity["activityName"],
                    activity["startTimeLocal"],
                    activity["duration"],
                    activity["distance"],
                    activity["averageSpeed"],
                    activity["calories"]
                ])

        print(f"Activities exported successfully to {output_file}")

        # Upload the file to PythonAnywhere
        upload_to_pythonanywhere(output_file)

    except garminconnect.GarminConnectConnectionError as conn_err:
        print(f"Error connecting to Garmin: {conn_err}")
    except garminconnect.GarminConnectTooManyRequestsError:
        print("Too many requests, slow down!")
    except Exception as e:
        print(f"An error occurred: {e}")


def upload_to_pythonanywhere(file_path):
    try:
        with open(file_path, 'rb') as file:
            # Send the file to the PythonAnywhere upload endpoint
            files = {'file': file}
            response = requests.post(PYTHONANYWHERE_UPLOAD_URL, files=files)

            if response.status_code == 200:
                print("File uploaded successfully!")
            else:
                print(f"Failed to upload file. Response: {response.text}")

    except Exception as e:
        print(f"An error occurred during file upload: {e}")


if __name__ == "__main__":
    export_garmin_activities()
