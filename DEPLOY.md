# 🚀 AIon Uren online zetten op uren.switchaion.nl

Compleet stappenplan om de uren-app live te krijgen op `uren.switchaion.nl`. Reken op **45-60 minuten** totaal, eenmalig werk.

**Wat we gaan doen:**
1. GitHub account aanmaken en code uploaden (10 min)
2. Render.com account aanmaken en app deployen (15 min)
3. DNS-record bij TransIP toevoegen (5 min)
4. Render eigen domein koppelen (5 min)
5. Eerste login en accounts aanmaken (10 min)

Alle stappen gebeuren in de browser. Geen terminal, geen SSH, geen Linux nodig.

---

## Stap 0 — Bestanden klaarzetten

Pak `uren_app.zip` uit op je computer. Je krijgt een map `uren_app` met:

```
uren_app/
├── app.py
├── requirements.txt
├── render.yaml         ← Render-config (automatisch gelezen)
├── wsgi.py
├── .gitignore          ← Verbergt gevoelige bestanden voor GitHub
├── README.md
├── DEPLOY.md
├── static/style.css
└── templates/...
```

> **Belangrijk:** De `.gitignore` is een verborgen bestand. Op Mac/Windows is hij standaard onzichtbaar maar wel aanwezig — laat hem staan, hij zorgt dat je SQLite database NIET op GitHub komt.

---

## Stap 1 — GitHub account & repository (10 min)

GitHub is de gratis opslagplek waar je code komt te staan. Render gebruikt dit om automatisch te deployen.

### 1.1 — Account aanmaken

1. Ga naar [github.com/signup](https://github.com/signup)
2. Vul je e-mailadres in, kies een wachtwoord, en een gebruikersnaam (bv. `dennis-aion` — wordt onderdeel van je URLs)
3. Bevestig je e-mail

### 1.2 — Repository aanmaken

1. Klik rechtsboven op het **`+`** icoon → **"New repository"**
2. Vul in:
   - **Repository name:** `aion-uren`
   - **Description:** `Uren administratie webapp`
   - Kies **"Private"** — je wilt niet dat iedereen je code kan zien
   - **Vink NIETS aan** bij "Initialize" — leeg laten
3. Klik **"Create repository"**

### 1.3 — Code uploaden

Op de volgende pagina zie je drie opties. Kies **"uploading an existing file"** (de link in de tekst).

1. Open de map `uren_app` op je computer in een venster
2. Selecteer **alle bestanden en mappen** binnen `uren_app` (NIET de map zelf, maar de inhoud — `app.py`, `requirements.txt`, `static/`, `templates/`, etc.)
3. Sleep ze allemaal naar het GitHub upload-venster
4. Scroll naar beneden, in het "Commit changes" vak:
   - **Commit message:** `Eerste versie`
5. Klik **"Commit changes"**

> **Op Mac:** verborgen bestanden zoals `.gitignore` zie je standaard niet. Druk **Cmd+Shift+.** in Finder om ze zichtbaar te maken. Zorg dat `.gitignore` mee in de upload zit.
> 
> **Op Windows:** in Verkenner ga naar tab "Beeld" → vink "Verborgen items" aan.

Je code staat nu op GitHub. ✅

---

## Stap 2 — Render.com deployment (15 min)

### 2.1 — Account aanmaken

1. Ga naar [render.com](https://render.com)
2. Klik op **"Get Started"** rechtsboven
3. Kies **"Sign up with GitHub"** — eenvoudiger, want Render moet toch toegang krijgen tot je GitHub
4. Autoriseer Render om je GitHub repositories te zien

### 2.2 — Nieuwe Blueprint aanmaken

Render leest het bestand `render.yaml` automatisch en configureert alles voor je.

1. Op je Render dashboard, klik **"New +"** rechtsboven → **"Blueprint"**
2. **"Connect a repository"** → kies `aion-uren`
3. Render scant je repo en vindt `render.yaml` — je ziet "1 service to deploy"
4. **Blueprint name:** `aion-uren`
5. Klik **"Apply"**

### 2.3 — Environment variables instellen

Render vraagt nu om twee waardes die je zelf moet invullen:

1. **ADMIN_EMAIL:** je eigen e-mailadres, bv. `dennis@switchaion.nl`
2. **ADMIN_PASSWORD:** een sterk wachtwoord (minimaal 12 tekens, mix van letters/cijfers). **Schrijf dit ergens veilig op!**

Klik **"Apply"** of **"Save and deploy"**.

### 2.4 — Wachten op de eerste build

Render gaat nu:
- Je code ophalen van GitHub
- Python installeren
- Pakketten installeren via `requirements.txt`
- Gunicorn starten

Dit duurt **3-5 minuten**. Je ziet de logs live in je browser. Wanneer je bovenaan **"Live"** ziet met groene status, is je app online.

### 2.5 — Test de tijdelijke URL

Render geeft je een tijdelijke URL: iets als `https://aion-uren.onrender.com`. Klik erop, log in met:
- E-mail: het adres dat je bij ADMIN_EMAIL hebt ingevuld
- Wachtwoord: het wachtwoord dat je hebt ingevuld

Werkt het? ✅ — dan gaan we door naar het eigen domein.

> **Eerste klik kan 30 seconden duren** — gratis Render-apps "slapen" na 15 min inactiviteit. Dit is geen probleem voor dagelijks gebruik (eerste medewerker 's ochtends wekt 'm wakker).

---

## Stap 3 — DNS bij TransIP koppelen (5 min)

We gaan `uren.switchaion.nl` laten wijzen naar je Render-app.

### 3.1 — Inloggen bij TransIP

1. Ga naar [www.transip.nl](https://www.transip.nl) en log in
2. Ga naar **"Mijn account"** → **"Domeinen"** → klik op `switchaion.nl`
3. Klik op tab **"DNS"**

### 3.2 — CNAME-record toevoegen

Je ziet een lijst met bestaande DNS-records. Onderaan kun je een nieuwe toevoegen:

| Veld | Waarde |
|---|---|
| **Naam** | `uren` |
| **TTL** | `5 minuten` (of `300` of standaard) |
| **Type** | `CNAME` |
| **Waarde** | `aion-uren.onrender.com` (vervang door **jouw** Render URL, zonder `https://`!) |

Klik **"Toevoegen"** of **"Opslaan"**.

> **Hoe vind ik mijn precieze Render URL?** In het Render dashboard, bovenaan je service zie je iets als `aion-uren-abc1.onrender.com`. Gebruik dat hele adres, zonder de `https://` ervoor.

### 3.3 — Wachten op DNS-propagatie

Het DNS-record moet zich verspreiden over het internet. Dit duurt meestal **5-30 minuten**, soms tot 24 uur (zeldzaam). Je kunt verder met de volgende stap zonder te wachten.

---

## Stap 4 — Eigen domein activeren op Render (5 min)

### 4.1 — Custom domain toevoegen

1. Ga naar je Render dashboard → klik op je `aion-uren` service
2. Klik tab **"Settings"** → scroll naar **"Custom Domain"**
3. Klik **"Add Custom Domain"**
4. Vul in: `uren.switchaion.nl`
5. Klik **"Save"**

Render verifieert het CNAME-record. Als de DNS al gepropageerd is: meteen ✓ groen. Anders: status "Verifying" — wacht 5-15 minuten en herlaad de pagina.

### 4.2 — HTTPS automatisch

Render regelt zelf een gratis SSL-certificaat via Let's Encrypt. Na 5-10 minuten zie je naast je custom domain een groen vinkje en "Certificate issued". Vanaf dat moment werkt:

🎉 **`https://uren.switchaion.nl`** — je app is live op je eigen subdomein.

---

## Stap 5 — Eerste echte setup (10 min)

### 5.1 — Eerste login

Ga naar `https://uren.switchaion.nl` en log in met je ADMIN_EMAIL + ADMIN_PASSWORD.

### 5.2 — Klant en project aanmaken

1. Klik **"Projecten"** in de bovenbalk
2. Voeg een klant toe (bv. echte klanten van AIon)
3. Voeg projecten toe en koppel aan de juiste klant — zet meteen het uurtarief erbij voor latere facturatie-vergelijking

### 5.3 — Collega-accounts aanmaken

1. Klik **"Gebruikers"** in de bovenbalk
2. Voor elke collega (Benno, Hicham, etc.): vul naam, e-mail, sterk wachtwoord, en rol in (manager of medewerker)
3. Bij medewerkers: koppel ze aan een manager (anders kan niemand hun uren goedkeuren)
4. Mail het wachtwoord veilig naar elke collega — vraag ze het meteen te wijzigen via Gebruikers → eigen rij → nieuw wachtwoord

### 5.4 — Test de hele flow

Doe één testronde met je eigen account:
1. Voeg uren toe via "Mijn uren"
2. Log uit, log in als manager-account, ga naar "Goedkeuring", keur de uren goed
3. Download een CSV en PDF via "Rapportage"

Werkt alles? Dan ben je echt live. 🎉

---

## Updates uitrollen later

Wijzig je later de code? Heel simpel:

1. Open de file op GitHub (of upload een nieuwe versie via de GitHub web-interface)
2. Klik "Edit", maak wijziging, klik "Commit changes" onderaan
3. Render detecteert binnen 30 seconden de wijziging en deployt automatisch (~3 min)
4. Klaar — wijziging is live

---

## Database backup (BELANGRIJK!)

Render's gratis plan heeft een **persistent disk** (in `render.yaml` geconfigureerd) waar je database leeft. Maar:

> ⚠️ **Render bewaart geen automatische backups op het gratis plan.**

**Doe dit elke week:**

1. Ga naar Render dashboard → je service → tab **"Shell"** (in de zijbalk)
2. Type in: `cat instance/uren.db | base64 > /tmp/backup.b64 && cat /tmp/backup.b64` en druk Enter
3. Kopieer de hele output (lange tekstreeks)
4. Plak in een lokaal tekstbestand `uren-backup-YYYY-MM-DD.b64` en bewaar in Dropbox/Drive

Bij dataverlies: ik kan je begeleiden om die backup terug te zetten.

**Slimmere optie voor later:** Render's "Starter" plan ($7/maand) heeft automatische dagelijkse backups. Overweeg dit zodra je serieus afhankelijk bent van de app.

---

## Veelvoorkomende problemen

### "Application failed to respond" of timeout
- Render-app slaapt — eerste request duurt 30 sec. Herlaad de pagina.

### "Module not found" in build log
- Controleer dat `requirements.txt` mee is geüpload naar GitHub
- Controleer dat de bestanden in de **root** van de repo staan, niet in een submap `uren_app/`

### Custom domain blijft "Verifying"
- DNS heeft tijd nodig. Wacht 30 min, max 24 uur
- Check je CNAME-record nog eens — staat de **exacte** Render URL (incl. eventuele random suffix)?

### Eerste login werkt niet
- Environment variables fout ingevuld → Settings → Environment → wijzig → "Manual Deploy" om opnieuw te starten
- Check de logs in Render: tab "Logs" — er staat vaak een duidelijke foutmelding

### Hele app weg / database leeg na nieuwe deploy
- Persistent disk mist of `render.yaml` was niet correct meegegeven bij eerste setup
- Neem contact op — dit is herstelbaar als je backup hebt

---

## Wat je nu hebt

✓ **`https://uren.switchaion.nl`** — eigen subdomein, gratis HTTPS  
✓ **Onbeperkt gebruik** voor je team van 3-10 mensen  
✓ **Updates via één klik** op GitHub  
✓ **Productie-veilig** — secret keys, debug uit, sessie-cookies beveiligd  
✓ **Geen serveronderhoud** — Render doet alles  
✓ **Eigen branding** — matchend met switchaion.nl  

**Totale kosten:** €0 per maand.

**Wanneer upgraden:** als de app cruciaal wordt voor de business, overweeg Render Starter ($7/mnd) voor: geen slaap-modus, automatische backups, snellere response. Anders prima zo.

---

## Hulp nodig?

Loop je tijdens een stap vast? Stuur me:
- Welke stap je deed
- De exacte foutmelding (screenshot of tekst)
- Wat je verwachtte vs. wat er gebeurde

Dan help ik je verder. Succes!
