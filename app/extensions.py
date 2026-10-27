from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Initialize Flask extensions
cors = CORS()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "60 per hour"],
    storage_uri="memory://"
)
