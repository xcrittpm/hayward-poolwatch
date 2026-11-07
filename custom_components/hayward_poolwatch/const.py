"""Constants for the Hayward Poolwatch integration."""

DOMAIN = "hayward_poolwatch"

# Public Firebase settings used by the poolwatch.hayward.fr web app.
FIREBASE_API_KEY = "AIzaSyBLaxiyZ2nS1KgRBqWe-NY4EG7OzG5fKpE"
FIREBASE_PROJECT = "hayward-europe"
# The API key only accepts requests that come from the Poolwatch website.
REFERER = "https://poolwatch.hayward.fr/"

AUTH_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
REFRESH_URL = "https://securetoken.googleapis.com/v1/token"
FIRESTORE_URL = (
    f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT}"
    "/databases/(default)/documents"
)
COMMAND_URL = "https://europe-west1-hayward-europe.cloudfunctions.net/sendPoolCommand"

DEFAULT_SCAN_INTERVAL = 30  # seconds
# Time the pool needs to apply a command before we read it back.
COMMAND_REFRESH_DELAY = 15  # seconds (the pool takes ~10 s to confirm)

FILTRATION_MODES = {
    0: "manual",
    1: "auto",
    2: "heating",
    3: "smart",
    4: "intel",
}
