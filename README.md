# iCal feed

Custom Home Assistant integration that exposes a read-only ICS feed for configured calendars. This document contains English instructions first and a Dutch translation afterwards.

---

## English

### Features

- Serves an ICS feed on a secret path (`/ical/<secret>/<slug>.ics`) without authentication.
- Lets you limit the time window (past/future days) that the feed exposes.
- Supports title rewrites and filtering through regular expressions.
- Creates diagnostics and repair issues when previously selected calendars disappear.

### Installation

#### Via HACS

1. Add this repository (`https://github.com/sir-Unknown/ha_ical_feed`) as a custom integration in HACS.
2. Install **iCal feed**, restart Home Assistant, and continue with the configuration flow.

#### Manual

1. Copy `custom_components/ical_feed` to the `custom_components` folder of your Home Assistant installation.
2. Restart Home Assistant so the integration loads.

### Configuration

#### Setup

1. Open **Settings → Devices & Services** and click **Add Integration**.
2. Pick **iCal feed**, select one calendar entity, and set the number of days in the past/future.
3. Complete the wizard; a long secret is generated automatically for the feed URL.

Need multiple calendars? Create another iCal feed entry per calendar or merge them externally.

#### Options

Open the integration and choose **Options** to:

- Copy the final feed URL (read-only field).
- Change the number of days included in the past/future window.
- Provide a regex plus replacement to rewrite event titles.
- Provide a regex that drops events after the title rewrite.
- Regenerate the secret so old URLs stop working.

### Using the feed

The feed lives under `/ical/<secret>/<feed_slug>.ics`. Combine it with your Home Assistant base URL, e.g.:

```
https://example.duckdns.org/ical/SECRET/living-room.ics
```

Each request is generated live, so updates in Home Assistant automatically reach subscribed calendar apps.

### Diagnostics & repairs

- Download the masked feed URL from **Settings → System → Diagnostics** to share troubleshooting details safely.
- If the selected calendar is removed or renamed, Home Assistant raises a repair issue ("Configured calendars are missing") under **Settings → System → Repairs**.

---

## Nederlands

### Functies

- Biedt een ICS-feed aan op een geheim pad (`/ical/<secret>/<slug>.ics`) zonder authenticatie.
- Laat je het tijdvenster beperken (dagen terug/vooruit).
- Ondersteunt het herschrijven en filteren van titels via reguliere expressies.
- Maakt een diagnostisch ZIP-bestand en reparatie-item aan wanneer kalenders verdwijnen.

### Installatie

#### Via HACS

1. Voeg deze repository (`https://github.com/sir-Unknown/ha_ical_feed`) toe als aangepaste integratie in HACS.
2. Installeer **iCal feed**, herstart Home Assistant en vervolg de configuratie.

#### Handmatig

1. Kopieer `custom_components/ical_feed` naar de `custom_components` map van je Home Assistant-installatie.
2. Herstart Home Assistant zodat de integratie actief wordt.

### Configuratie

#### Setup

1. Ga naar **Instellingen → Apparaten & Diensten** en kies **Integratie toevoegen**.
2. Selecteer **iCal feed**, kies één kalender-entiteit en stel het aantal dagen terug/vooruit in.
3. Rond de wizard af; de feed-URL krijgt automatisch een lang geheim.

Wil je meerdere kalenders publiceren? Maak dan een extra iCal feed voor elke kalender of combineer ze extern.

#### Opties

Open de integratie en klik op **Opties** om:

- De feed-link te kopiëren (alleen-lezen).
- Het aantal dagen terug/vooruit aan te passen.
- Een regex plus vervanging voor titelherschrijving op te geven.
- Een regex te plaatsen die events filtert na de titelwijziging.
- Een nieuw geheim te genereren zodat oude links ongeldig worden.

### Feed gebruiken

De feed staat onder `/ical/<secret>/<feed_slug>.ics`. Combineer dit pad met je interne of externe Home Assistant-adres, bijvoorbeeld:

```
https://example.duckdns.org/ical/SECRET/woonkamer.ics
```

Elke aanvraag wordt live opgebouwd, dus wijzigingen in Home Assistant zijn direct zichtbaar voor gekoppelde agenda's.

### Diagnostiek en reparaties

- Via **Instellingen → Systeem → Diagnostiek** download je de gemaskeerde feed-URL voor veilig delen.
- Als een geselecteerde kalender verdwijnt of hernoemd wordt, komt het reparatie-item "Configured calendars are missing" terecht onder **Instellingen → Systeem → Reparaties**.
