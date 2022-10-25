import vimeo
from glob import glob
from decouple import config
import requests


client = vimeo.VimeoClient(
    token=config("VIMEO_TOKEN"),
    key=config("CLIENT_ID"),
    secret=config("CLIENT_SECRET")
)

