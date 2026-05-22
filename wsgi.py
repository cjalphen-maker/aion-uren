# PythonAnywhere WSGI configuratie
# ----------------------------------
# Dit bestand wijst PythonAnywhere de weg naar je Flask app.
#
# In de PythonAnywhere "Web" tab moet je het pad naar dit bestand
# instellen, of je plakt de inhoud in het automatisch gegenereerde
# WSGI bestand (typisch /var/www/JOUWGEBRUIKERSNAAM_pythonanywhere_com_wsgi.py)
#
# Vergeet niet om JOUWGEBRUIKERSNAAM aan te passen!

import os
import sys

# Pad naar de map waar app.py staat — pas dit aan!
project_home = "/home/JOUWGEBRUIKERSNAAM/uren_app"
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Productie-modus aanzetten + secret key uit environment
os.environ["FLASK_ENV"] = "production"

# Belangrijk: zet deze variabelen ook in de "Web" tab onder "Environment variables":
#   SECRET_KEY        — willekeurige sleutel (zie README)
#   ADMIN_EMAIL       — jouw e-mailadres
#   ADMIN_PASSWORD    — sterk wachtwoord, alleen voor de eerste login

from app import app as application  # noqa
