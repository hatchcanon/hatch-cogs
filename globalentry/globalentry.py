import asyncio
import traceback
from datetime import datetime
import time
import requests
import argparse
import discord
from redbot.core import Config, checks, commands
from redbot.core.utils.chat_formatting import humanize_list, inline

# Imported from (https://github.com/jamescalixto/global-entry-scraper)

REQUEST_DELAY = 2
TIMESLOT_URL = "https://ttp.cbp.dhs.gov/schedulerapi/slots?orderBy=soonest&limit={limit}&locationId={location_id}&minimum=1"
MAPPING_URL = "https://ttp.cbp.dhs.gov/schedulerapi/locations/?temporary=false&inviteOnly=false&operational=true&serviceName=Global%20Entry"

def import_mapping_from_url() -> dict:
    """Get mapping of location ids to location names from the TTP website."""
    r = requests.get(MAPPING_URL)
    return {
        location["id"]: "{} ({}, {})".format(
            location["name"], location["city"], location["state"]
        )
        for location in r.json()
    }

def get_timeslots_for_location_id(location_id: int, limit: int) -> set:
    """Get list of objects representing open slots for a certain location."""
    r = requests.get(TIMESLOT_URL.format(location_id=location_id, limit=limit))
    timeslots = [parse_timeslot_datetime(timeslot) for timeslot in r.json()]
    return sorted(list(set(timeslots)))


def get_timeslots_for_location_ids(
        location_ids: list, before: str = None, limit: int = 10
) -> list:
    """Get a mapping of location ids to open timeslots. Takes in an optional YYYY-MM-DD
    parameter to filter the results."""
    all_timeslots = {}
    for index, location_id in enumerate(location_ids):
        timeslots = [
            timeslot
            for timeslot in get_timeslots_for_location_id(location_id, limit)
            if before is None or datetime.strptime(before, "%Y-%m-%d") > timeslot
        ]
        all_timeslots[location_id] = timeslots
        if index < len(location_ids) - 1:  # delay between requests.
            time.sleep(REQUEST_DELAY)
    return all_timeslots