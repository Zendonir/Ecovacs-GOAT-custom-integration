# Ecovacs GOAT — Home Assistant

Zwei Custom Integrations für den **Ecovacs GOAT A1600 LiDAR Pro**, die beide auf
der offiziellen [Ecovacs-Integration](https://www.home-assistant.io/integrations/ecovacs/)
aufsetzen und deren bestehende Verbindung mitbenutzen. Keine baut eine zweite
Anmeldung am Ecovacs-Konto auf.

| Integration | Zweck |
| --- | --- |
| `ecovacs_goat` | Bringt den Mäher überhaupt erst zum Vorschein — meldet die Geräteklasse `e4gqia` bei `deebot-client` an |
| `ecovacs_zones` | Ergänzt Zonensteuerung: Parameter je Zone, gezieltes Starten einzelner oder mehrerer Zonen |

Beide sind unabhängig voneinander installierbar. Erscheint der Mäher in Home
Assistant bereits, wird `ecovacs_goat` nicht gebraucht.

---

## 1. `ecovacs_goat` — Gerät sichtbar machen

Die Ecovacs-Integration löst die Fähigkeiten eines Geräts über dessen
**Geräteklasse** auf. Für ein Modell ohne Definition erscheint im Log

```
Device class 'e4gqia' not recognized. Please add support for it
```

und es entstehen **gar keine Entities**. `e4gqia` ist der GOAT A1600 LiDAR Pro
(`GOAT_INT_A1600_LIDAR_PLUS_EU`).

Alle GOAT-Definitionen in `deebot-client` sind bis auf ihren Docstring
byte-identisch — `51rcxt` (A3000 LiDAR Pro) und `xmp9ds` (A1600 RTK)
unterscheiden sich in genau einer Kommentarzeile. Ein unbekanntes GOAT-Modell
lässt sich also über eine vorhandene Definition bedienen.

Die Integration trägt die fehlende Geräteklasse in die Registry von
`deebot-client` ein, zeigt dabei auf eine Schwester-Definition und lädt
anschließend die Ecovacs-Integration neu. Sie **verweist** auf die vorhandene
Definition, statt sie zu kopieren, und bleibt damit korrekt, wenn `deebot-client`
die GOAT-Fähigkeiten ändert. Sobald die Geräteklasse dort offiziell unterstützt
wird, erkennt sie das, tritt beiseite und kann entfernt werden.

Eigene Entities liefert sie keine — Mäher, Sensoren und Schalter kommen alle von
der offiziellen Integration.

### Weitere unbekannte GOAT-Modelle

Nennt dein Log eine andere Geräteklasse, trag sie unter *Konfigurieren* ein
(mit Leerzeichen oder Komma getrennt). Bitte melde sie zusätzlich hier und
[upstream](https://github.com/DeebotUniverse/client.py/issues).

---

## 2. `ecovacs_zones` — Zonensteuerung

Die offizielle Integration kennt keine zonenspezifische Steuerung. Diese
Integration ergänzt sie um Kommandos, die `deebot-client` nicht als eigene
Klassen kennt, und schickt sie über denselben authentifizierten Kanal
(`Device.execute_command()` → `iot/devmanager.do`).

### Entities

Je erkannter Zone ein eigenes Gerät **„Mäher Zone N"** mit

- **Schnitthöhe** (`mowHeightLevel`)
- **Mähmodus** (`cutMode`)
- **Hinderniserkennung** (`obstacleHeight`)
- **Mährichtung** (`angle`)
- **Mähen starten** — startet genau diese Zone

sowie ein Gerät **„Mäher Zonensteuerung"** mit globalem **Stopp**-Button und
einem **Zonen-Mähstatus**-Sensor (aktuelle Zone, Akku, Ladezustand).

Zonen, die später in der Ecovacs-App dazukommen, erscheinen beim nächsten
Aktualisierungslauf automatisch.

### Zonennamen

Das Geräteprotokoll kennt **keine** Zonennamen — nur numerische `areaID`s. Namen
wie „Vorgarten" müssen in Home Assistant manuell vergeben werden (Entity bzw.
Gerät umbenennen).

### Wertebereiche

Die tatsächlichen Grenzen der Ecovacs-App sind nicht bekannt. Die Min-/Max-Werte
der Number-Entities sind vorsichtig geschätzt; das Attribut
`beobachteter_bereich` an jeder Entity zeigt, welche Werte in der Aufzeichnung
real vorkamen:

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

- Bewusst auf **ein** Ecovacs-Gerät ausgelegt. Bei mehreren Geräten grenzt das
  Feld *Gerätename* ein; Entity- und Geräte-IDs sind nicht mehrgerätefähig, ein
  zweiter Eintrag wird deshalb abgelehnt.
- Kartendarstellung/Geometrie (`getAreaSet`) wird nicht dekodiert.

---

## Voraussetzungen

- Home Assistant 2024.12 oder neuer
- Die offizielle **Ecovacs**-Integration, eingerichtet und verbunden

## Installation

Den gewünschten Ordner aus `custom_components/` (komplett, inklusive
`translations/`) nach `<HA-Config>/custom_components/` kopieren und Home
Assistant neu starten. Danach *Einstellungen → Geräte & Dienste → Integration
hinzufügen*:

- **Ecovacs GOAT Support** — nichts zu konfigurieren
- **Ecovacs GOAT Zonensteuerung** — Gerätefeld leer lassen, wenn nur ein
  Ecovacs-Gerät im Konto ist

Ist die Ecovacs-Integration beim Start noch nicht bereit, greift
`ConfigEntryNotReady` — Home Assistant wiederholt die Einrichtung selbstständig.

> **HACS:** Das Repository enthält zwei Integrationen. HACS erwartet in der
> Kategorie *Integration* genau eine pro Repository, daher ist der Weg oben die
> manuelle Installation.

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
    custom_components.ecovacs_zones: debug
    deebot_client: debug
```

`deebot-client` fängt Fehler in `Command.execute()` ab und liefert dann eine
leere Antwort — die eigentliche Ursache steht deshalb nur im `deebot_client`-Log.
