# Import TQDM progress bar library
from tqdm import tqdm

# Import app environment variables
from decouple import config
from sys import exit
from signal import signal, SIGINT
from dateutil.parser import parse
from datetime import date, timedelta
from urllib.parse import quote
import requests
import os


# define class for text colouring and highlighting
class color:
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    DARKCYAN = "\033[36m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


class ZoomDownloader:
    def __init__(self, jwt_token, download_dir="downloads", development=True) -> None:
        self.JWT_TOKEN = jwt_token
        self.DEVELOPMENT = development
        self.ACCESS_TOKEN = "Bearer " + self.JWT_TOKEN
        self.AUTHORIZATION_HEADER = {"Authorization": self.ACCESS_TOKEN}
        self.API_ENDPOINT_USER_LIST = "https://api.zoom.us/v2/users"
        self.DOWNLOAD_DIRECTORY = download_dir
        self.COMPLETED_MEETING_IDS_LOG = "completed-downloads.log"
        self.COMPLETED_MEETING_IDS = set()

        # Start date now split into YEAR, MONTH, and DAY variables (Within 6 month range)
        self.RECORDING_START_YEAR = date.today().year
        self.RECORDING_START_MONTH = date.today().month
        self.RECORDING_START_DAY = date.today().day - 1
        self.RECORDING_END_DATE = date.today()

    def API_ENDPOINT_RECORDING_LIST(self, email):
        self.API_ENDPOINT = "https://api.zoom.us/v2/users/" + email + "/recordings"
        return self.API_ENDPOINT

    def API_ENDPOINT_DELETE_RECORDINGS(self, meeting_uuid: str):
        API_ENDPOINT = f"https://api.zoom.us/v2/meetings/{quote(quote(meeting_uuid, safe=''), safe='')}/recordings"
        return API_ENDPOINT

    def get_credentials(self, host_id, page_number, rec_start_date):
        self.CREDENTIALS = {
            "host_id": host_id,
            "page_number": page_number,
            "from": rec_start_date,
        }
        return self.CREDENTIALS

    def get_user_ids(self):
        # get total page count, convert to integer, increment by 1
        response = requests.get(
            url=self.API_ENDPOINT_USER_LIST, headers=self.AUTHORIZATION_HEADER
        )
        if not response.ok:
            print(response)
            print("Is your JWT still valid?")
            exit(1)
        page_data = response.json()
        total_pages = int(page_data["page_count"]) + 1

        # results will be appended to this list
        all_entries = []

        # loop through all pages and return user data
        for page in range(1, total_pages):
            url = self.API_ENDPOINT_USER_LIST + "?page_number=" + str(page)
            user_data = requests.get(url=url, headers=self.AUTHORIZATION_HEADER).json()
            user_ids = [
                (user["email"], user["id"], user["first_name"], user["last_name"])
                for user in user_data["users"]
            ]
            all_entries.extend(user_ids)
            data = all_entries
            page += 1
        return data

    def format_filename(
        self, recording, file_type, file_extension, recording_type, recording_id
    ):
        uuid = recording["uuid"]
        topic = recording["topic"].replace("/", "&")
        rec_type = recording_type.replace("_", " ").title()
        meeting_time = parse(recording["start_time"]).strftime(
            "%Y.%m.%d - %I.%M %p UTC"
        )
        return "{} - {} - {}.{}".format(
            meeting_time, topic + " - " + rec_type, recording_id, file_extension.lower()
        ), "{} - {}".format(topic, meeting_time)

    def get_downloads(self, recording):
        self.downloads = []
        for download in recording["recording_files"]:
            file_extension = download["file_extension"]
            if file_extension != "MP4":
                continue
            file_type = download["file_type"]
            recording_id = download["id"]
            if file_type == "":
                recording_type = "incomplete"
                # print("\download is: {}".format(download))
            elif file_type != "TIMELINE":
                recording_type = download["recording_type"]
            else:
                recording_type = download["file_type"]
            # must append JWT token to download_url
            download_url = (
                download["download_url"] + "?access_token=" + config("JWT_TOKEN")
            )
            self.downloads.append(
                (file_type, file_extension, download_url, recording_type, recording_id)
            )
        return self.downloads

    def get_recordings(self, email, page_size, rec_start_date, rec_end_date):
        return {
            "userId": email,
            "page_size": page_size,
            "from": rec_start_date,
            "to": rec_end_date,
        }

    # Generator used to create deltas for recording start and end dates
    def perdelta(self, start, end, delta):
        curr = start
        while curr < end:
            yield curr, min(curr + delta, end)
            curr += delta

    def list_recordings(self, email):
        self.recordings = []

        for start, end in self.perdelta(
            date(
                self.RECORDING_START_YEAR,
                self.RECORDING_START_MONTH,
                self.RECORDING_START_DAY,
            ),
            self.RECORDING_END_DATE,
            timedelta(days=30),
        ):
            post_data = self.get_recordings(email, 300, start, end)
            response = requests.get(
                url=self.API_ENDPOINT_RECORDING_LIST(email),
                headers=self.AUTHORIZATION_HEADER,
                params=post_data,
            )
            recordings_data = response.json()
            self.recordings.extend(recordings_data["meetings"])
        return self.recordings

    def download_recording(self, download_url, email, filename, foldername):
        dl_dir = os.sep.join([self.DOWNLOAD_DIRECTORY, foldername])
        full_filename = os.sep.join([dl_dir, filename])
        os.makedirs(dl_dir, exist_ok=True)
        response = requests.get(download_url, stream=True)

        # total size in bytes.
        total_size = int(response.headers.get("content-length", 0))
        block_size = 32 * 1024  # 32 Kibibytes

        # create TQDM progress bar
        t = tqdm(total=total_size, unit="iB", unit_scale=True)
        try:
            # with open(os.devnull, 'wb') as fd:  # write to dev/null when testing
            with open(full_filename, "wb") as fd:
                for chunk in response.iter_content(block_size):
                    t.update(len(chunk))
                    fd.write(chunk)  # write video chunk to disk
            t.close()
            return True
        except Exception as e:
            # if there was some exception, print the error and return False
            print(e)
            return False

    def load_completed_meeting_ids(self):
        try:
            with open(self.COMPLETED_MEETING_IDS_LOG, "r") as fd:
                for line in fd:
                    self.COMPLETED_MEETING_IDS.add(line.strip())
        except FileNotFoundError:
            print(
                "Log file not found. Creating new log file: ",
                self.COMPLETED_MEETING_IDS_LOG,
            )
            print()

    def delete_meeting(self, meeting_uuid):
        response = requests.delete(
            self.API_ENDPOINT_DELETE_RECORDINGS(meeting_uuid),
            headers=self.AUTHORIZATION_HEADER,
        )
        print(response.status_code)

    # ################################################################
    # #                        MAIN                                  #
    # ################################################################

    def main(self):

        # clear the screen buffer
        os.system("cls" if os.name == "nt" else "clear")

        # show the logo
        print(
            """

                                ,*****************.
                                ***********************
                            *****************************
                         **********************************
                        ********               *************
                        *******                .**    *******
                        *******                       ******/
                        *******                       /******
                        ///////                 //    //////
                         ///////              ./////.//////
                         ////////////////////////////////*
                           /////////////////////////////
                             /////////////////////////
                                ,/////////////////

                            Zoom Recording Downloader

    """
        )

        self.load_completed_meeting_ids()

        print(color.BOLD + "Getting user accounts..." + color.END)
        users = self.get_user_ids()

        for email, user_id, first_name, last_name in users:
            print(
                color.BOLD
                + "\nGetting recording list for {} {} ({})".format(
                    first_name, last_name, email
                )
                + color.END
            )
            # wait n.n seconds so we don't breach the API rate limit
            # time.sleep(0.1)
            recordings = self.list_recordings(user_id)
            total_count = len(recordings)
            print("==> Found {} recordings".format(total_count))

            for index, recording in enumerate(recordings):
                success = False
                meeting_id = recording["uuid"]
                if meeting_id in self.COMPLETED_MEETING_IDS:
                    print(
                        "==> Skipping already downloaded meeting: {}".format(meeting_id)
                    )
                    continue

                downloads = self.get_downloads(recording)
                for (
                    file_type,
                    file_extension,
                    download_url,
                    recording_type,
                    recording_id,
                ) in downloads:
                    if recording_type != "incomplete":
                        filename, foldername = self.format_filename(
                            recording,
                            file_type,
                            file_extension,
                            recording_type,
                            recording_id,
                        )
                        # truncate URL to 64 characters
                        truncated_url = download_url[0:64] + "..."
                        print(
                            "==> Downloading ({} of {}) as {}: {}: {}".format(
                                index + 1,
                                total_count,
                                recording_type,
                                recording_id,
                                truncated_url,
                            )
                        )
                        success |= self.download_recording(
                            download_url, email, filename, foldername
                        )
                        # success = True
                        if not self.DEVELOPMENT:
                            self.delete_meeting(meeting_id)
                    else:
                        print(
                            "### Incomplete Recording ({} of {}) for {}".format(
                                index + 1, total_count, recording_id
                            )
                        )
                        success = False

                if success:
                    # if successful, write the ID of this recording to the completed file
                    with open(self.COMPLETED_MEETING_IDS_LOG, "a") as log:
                        self.COMPLETED_MEETING_IDS.add(meeting_id)
                        log.write(meeting_id)
                        log.write("\n")
                        log.flush()

        print(color.BOLD + color.GREEN + "\n*** All done! ***" + color.END)
        save_location = os.path.abspath(self.DOWNLOAD_DIRECTORY)
        print(
            color.BLUE
            + "\nRecordings have been saved to: "
            + color.UNDERLINE
            + "{}".format(save_location)
            + color.END
            + "\n"
        )


if __name__ == "__main__":
    # tell Python to run the handler() function when SIGINT is recieved
    zoom_downloader = ZoomDownloader(config("JWT_TOKEN"))
    signal(SIGINT, zoom_downloader.handler)

    zoom_downloader.main()
