from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# Instantiate extensions without app context; they will be configured in create_app
# Use naming that matches Flask community conventions to simplify future integration.
db = SQLAlchemy()
migrate = Migrate()
