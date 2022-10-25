from decouple import config
from glob import glob
from zoom_downloader import ZoomDownloader
from upload_vimeo import client
from time import sleep
from os import mkdir
import shutil


if __name__ == "__main__":
    zoom_downloader = ZoomDownloader(config("JWT_TOKEN"), development=False)
    zoom_downloader.main()

    client = client

    mkdir("clases_subidas")

    for pth in glob(f"{zoom_downloader.DOWNLOAD_DIRECTORY}/*/*.mp4"):
        name = pth.split("\\")[-1][:-32]
        print(f"Subiendo el video {name}")
        try:
            uri = client.upload(filename=pth, data={"name": str(name)})
            print("Cargado "+uri+" con nombre "+name)
        except:
            uri = client.upload(filename=pth)
            print("Cargado "+uri+" sin nombre")
        # father_dir = "/".join(pth.split("\\")[:2])
        print("Moviendo",name,"hacia","clases_subidas/")
        shutil.move(pth, "clases_subidas/")
        print("")
    shutil.rmtree("clases_subidas")
