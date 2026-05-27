import openmeteo_requests

import pandas as pd
import requests_cache
from retry_requests import retry

# Setup of the Open-Meteo API client with cache and retry on error
cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
openmeteo = openmeteo_requests.Client(session = retry_session)


# The order of variables in hourly or daily is important to assign them correctly below
url = "https://api.open-meteo.com/v1/forecast"
params = {
	"latitude": 45.4112,
	"longitude": -75.6981,
	"daily": "weather_code",
	"hourly": ["temperature_2m", "apparent_temperature", "precipitation", "wind_speed_10m"],
	"timezone": "auto",
}
responses = openmeteo.weather_api(url, params = params)

