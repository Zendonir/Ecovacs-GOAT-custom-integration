# Ecovacs GOAT — Home Assistant

Custom Integration für den **Ecovacs GOAT A1600 LiDAR Pro**. Sie setzt auf der
offiziellen [Ecovacs-Integration](https://www.home-assistant.io/integrations/ecovacs/)
auf und nutzt deren bestehende Verbindung mit — es wird **keine zweite Anmeldung**
am Ecovacs-Konto aufgebaut.

Sie erledigt zwei Dinge, die aufeinander aufbauen:

1. **Gerät sichtbar machen** — meldet GOAT-Geräteklassen bei `deebot-client` an,
   die die Bibliothek noch nicht kennt.
2. **Zonensteuerung** — Parameter je Zone und gezieltes Starten einzelner oder
   mehrerer Zonen.

---

## 1. Gerät sichtbar machen

Die Ecovacs-Integration löst die Fähigkeiten eines Geräts über dessen
**Geräteklasse** auf. Für ein Modell ohne Definition erscheint im Log

```
Device class 'e4gqia' not recognized. Please add support for it
```

und es entstehen **gar keine Entities** — die Integration legt für so ein Gerät
nicht einmal ein `Device`-Objekt an. `e4gqia` ist der GOAT A1600 LiDAR Pro
(`GOAT_INT_A1600_LIDAR_PLUS_EU`).

Alle GOAT-Definitionen in `deebot-client` sind bis auf ihren Docstring
byte-identisch — `51rcxt` (A3000 LiDAR Pro) und `xmp9ds` (A1600 RTK)
unterscheiden sich in genau einer Kommentarzeile. Ein unbekanntes GOAT-Modell
lässt sich also über eine vorhandene Definition bedienen.

Die Integration trägt die fehlende Geräteklasse in die Registry von
`deebot-client` ein und lädt anschließend die Ecovacs-Integration einmal neu,
damit diese das Gerät anlegt. Sie **verweist** auf die vorhandene Definition,
statt sie zu kopieren, und bleibt damit korrekt, wenn `deebot-client` die
GOAT-Fähigkeiten ändert. Sobald die Geräteklasse dort offiziell unterstützt
wird, erkennt sie das und tritt beiseite.

Mäher, Akku, Fehler und die übrigen Standard-Entities kommen weiterhin von der
offiziellen Integration.

### Weitere unbekannte GOAT-Modelle

Nennt dein Log eine andere Geräteklasse, trag sie unter *Konfigurieren* ein
(mit Leerzeichen oder Komma getrennt). Bitte melde sie zusätzlich
[upstream](https://github.com/DeebotUniverse/client.py/issues).

---

## 2. Zonensteuerung

Die offizielle Integration kennt keine zonenspezifische Steuerung. Diese
Integration ergänzt Kommandos, die `deebot-client` nicht als eigene Klassen
kennt, und schickt sie über denselben authentifizierten Kanal
(`Device.execute_command()` → `iot/devmanager.do`).

### Entities

Je erkannter Zone ein eigenes Gerät **„&lt;Mäher&gt; Zone N"** mit

- **Schnitthöhe** (`mowHeightLevel`)
- **Mähmodus** (`cutMode`)
- **Hinderniserkennung** (`obstacleHeight`)
- **Mährichtung** (`angle`)
- **Mähen starten** — startet genau diese Zone

sowie ein Gerät **„&lt;Mäher&gt; Zonensteuerung"** mit globalem
**Zonenmähen stoppen** und einem **Mähstatus**-Sensor (aktuelle Zone, Akku,
Ladezustand).

Zonen, die später in der Ecovacs-App dazukommen, erscheinen beim nächsten
Aktualisierungslauf automatisch — ebenso, wenn beim Einrichten noch keine Zonen
abrufbar waren.

### Zonennamen

Das Geräteprotokoll kennt **keine** Zonennamen — nur numerische `areaID`s. Namen
wie „Vorgarten" müssen in Home Assistant manuell vergeben werden (Gerät bzw.
Entity umbenennen).

### Wertebereiche

Die tatsächlichen Grenzen der Ecovacs-App sind nicht bekannt. Die Min-/Max-Werte
sind vorsichtig geschätzt; das Attribut `beobachteter_bereich` an jeder
Number-Entity zeigt, welche Werte in der Aufzeichnung real vorkamen:

| Parameter | Eingestellt | Beobachtet |
| --- | --- | --- |
| `mowHeightLevel` | 1–11 | 3–5 |
| `cutMode` | 1–10 | 4 / 7 |
| `obstacleHeight` | 0–3 | 1–2 |
| `angle` | 0–360 | 90–268 |

Werte außerhalb des beobachteten Bereichs sind ungetestet. Anpassbar in
`const.py` (`FIELD_SPECS`).

### Verifiziertes Protokoll

Aus einer echten MQTT-Aufzeichnung abgeleitet:

```jsonc
// setAreaParameter — immer alle Pflichtfelder senden
{"areaID": "2", "mowHeightLevel": 4, "cutMode": 4, "obstacleHeight": 1, "angle": 152}

// getAreaParameter — Request {} , Antwort:
{"areaParameters": [{"areaID": "1", "mowHeightLevel": 4, "cutMode": 7,
                     "obstacleHeight": 2, "angle": 180}, ...]}

// clean — Zonen starten/stoppen
{"act": "start", "content": {"type": "spotArea", "value": "2"}}
{"act": "start", "content": {"type": "spotArea", "value": "3,2"}}   // mehrere
{"act": "stop",  "content": {"type": "spotArea"}}
```

Der Status kommt aus den drei einzeln belegten Kommandos `getCleanInfo`,
`getBattery` und `getChargeState`. Schlägt eines fehl, bleibt nur dessen Wert
leer.

### Grenzen

- Ausgelegt auf **ein** Ecovacs-Gerät; bei mehreren grenzt das Feld
  *Gerätename* ein. Es ist nur ein Eintrag möglich.
- Kartendarstellung/Geometrie (`getAreaSet`) wird nicht dekodiert.

---

## Voraussetzungen

- Home Assistant 2024.12 oder neuer
- Die offizielle **Ecovacs**-Integration, eingerichtet und verbunden

## Installation

### HACS

1. HACS → Dreipunktmenü → *Benutzerdefinierte Repositories*
2. `https://github.com/Zendonir/Ecovacs-GOAT-custom-integration` hinzufügen,
   Kategorie *Integration*
3. **Ecovacs GOAT** installieren und Home Assistant neu starten

### Manuell

`custom_components/ecovacs_goat` (komplett, inklusive `translations/`) nach
`<HA-Config>/custom_components/` kopieren und Home Assistant neu starten.

### Einrichten

*Einstellungen → Geräte & Dienste → Integration hinzufügen → **Ecovacs GOAT***.
Das Gerätefeld leer lassen, wenn nur ein Ecovacs-Gerät im Konto ist.

Beim Einrichten wird die Ecovacs-Integration einmal neu geladen. Ist sie beim
Start noch nicht bereit, greift `ConfigEntryNotReady` — Home Assistant wiederholt
die Einrichtung selbstständig.

Einmal angemeldete Geräteklassen werden nicht wieder entfernt; nach dem
Entfernen der Integration wirkt das erst mit dem nächsten Neustart.

## Tests

```bash
pip install deebot-client pytest pytest-asyncio
pytest
```

Die Tests laufen ohne Home-Assistant-Installation: geprüft werden die
Registry-Anmeldung gegen ein echtes `deebot-client` und die Zonen-Protokoll-
schicht gegen ein Fake-Device (gesendete Kommandos und Antwortauswertung).

## Fehlersuche

```yaml
logger:
  logs:
    custom_components.ecovacs_goat: debug
    deebot_client: debug
```

`deebot-client` fängt Fehler in `Command.execute()` ab und liefert dann eine
leere Antwort — die eigentliche Ursache steht deshalb nur im `deebot_client`-Log.
