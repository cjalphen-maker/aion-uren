# Uren Administratie Webapp

Een complete webapplicatie voor urenregistratie met rolgebaseerde toegang, gebouwd met **Python (Flask)** en **SQLite**.

## Functies

- **Drie rollen** met verschillende rechten:
  - **Admin** — beheert gebruikers, klanten, projecten en heeft volledig overzicht
  - **Manager** — keurt uren goed/af voor het eigen team, beheert projecten, ziet teamrapportages
  - **Medewerker** — registreert eigen uren, ziet eigen overzicht
- **Uren registreren** — handmatig invoeren of met live timer (start/stop)
- **Klanten en projecten** — koppel uren aan klant/project, optioneel uurtarief
- **Goedkeuringsflow** — uren krijgen status `ingediend` → `goedgekeurd` of `afgewezen`
- **Rapportage** — filter op periode, project en medewerker; visualisatie per project en per medewerker
- **Export** — download als **CSV** (Excel-vriendelijk, met `;` als scheidingsteken) of **PDF**

## Installatie

```bash
# 1. Virtuele omgeving (aanbevolen)
python -m venv venv
source venv/bin/activate          # Linux/Mac
# venv\Scripts\activate           # Windows

# 2. Dependencies installeren
pip install -r requirements.txt

# 3. Starten — database wordt automatisch aangemaakt
python app.py
```

Open vervolgens `http://localhost:5000` in je browser.

## Demo-accounts

Na de eerste start zijn er drie test-accounts:

| Rol         | E-mail              | Wachtwoord    |
|-------------|---------------------|---------------|
| Admin       | `admin@local`       | `admin123`    |
| Manager     | `manager@local`     | `manager123`  |
| Medewerker  | `medewerker@local`  | `medewerker123` |

> Pieter (medewerker) staat onder Marieke (manager). Marieke ziet alleen Pieters uren in de goedkeuringslijst.

## Rechtenstructuur

| Functie                     | Admin | Manager | Medewerker |
|-----------------------------|:-----:|:-------:|:----------:|
| Eigen uren registreren      | ✓     | ✓       | ✓          |
| Eigen uren wijzigen         | ✓     | ✓       | ✓          |
| Uren goedkeuren (eigen team)| ✓     | ✓       | —          |
| Uren goedkeuren (iedereen)  | ✓     | —       | —          |
| Klanten / projecten beheren | ✓     | ✓       | —          |
| Gebruikers beheren          | ✓     | —       | —          |
| Rapportage eigen uren       | ✓     | ✓       | ✓          |
| Rapportage team             | ✓     | ✓ (eigen team) | — |
| Rapportage organisatie      | ✓     | —       | —          |

Rechten worden afgedwongen via twee decorators:

```python
@login_required          # alleen ingelogd
@role_required("admin")  # alleen specifieke rol(len)
```

## Productie-checklist

Deze app is geschikt voor intern gebruik na een paar aanscherpingen:

1. **Stel een veilige `SECRET_KEY` in** via een environment variabele (niet de default!)
2. **Gebruik HTTPS** (bijv. via een reverse proxy zoals Nginx + Let's Encrypt)
3. **Vervang SQLite door PostgreSQL** voor meerdere gelijktijdige gebruikers
4. **Draai met Gunicorn** in plaats van de Flask dev-server:
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```
5. **CSRF-bescherming** toevoegen met `Flask-WTF` (nu nog niet ingebouwd)
6. **Backups** van het `instance/uren.db` bestand inplannen

## Bestandsstructuur

```
uren_app/
├── app.py                # alle Flask routes + database modellen
├── requirements.txt
├── instance/
│   └── uren.db           # SQLite database (auto-aangemaakt)
├── static/
│   └── style.css         # alle styling
└── templates/
    ├── base.html         # gedeelde layout
    ├── login.html
    ├── dashboard.html
    ├── time_entries.html # uren registreren
    ├── approvals.html    # goedkeuringspagina
    ├── reports.html      # rapportages
    ├── users.html        # gebruikersbeheer (admin)
    ├── projects.html     # klanten/projecten
    └── error.html
```
