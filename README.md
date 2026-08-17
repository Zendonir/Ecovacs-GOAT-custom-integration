# Ecovacs GOAT — Home Assistant

Eigenständige Custom Integration für **Ecovacs-Mähroboter**, entwickelt für den
**GOAT A1600 LiDAR Pro**.

Sie ist ein Fork der offiziellen
[Ecovacs-Integration](https://www.home-assistant.io/integrations/ecovacs/),
meldet sich **selbst** am Ecovacs-Konto an und baut eine **eigene**
MQTT-Verbindung auf. Die offizielle Integration wird nicht gebraucht.

Ergänzt gegenüber dem Original: **Zonensteuerung** — Mähparameter je Zone und
gezieltes Starten einzelner oder mehrerer Zonen.

## Unterschiede zum Original

| | Original | Dieser Fork |
| --- | --- | --- |
| Anmeldung | eigene | eigene, unabhängig |
| Legacy-Geräte (XMPP, `py-sucks`) | unterstützt | entfernt |
| Vacuum-Plattform | ja | entfernt |
| Zonensteuerung | — | **ja** |
| Unbekannte Geräteklassen nachtragen | — | ja (`registry.py`) |

Der Legacy-Pfad fliegt raus, weil ein GOAT JSON über MQTT spricht; das spart die
`py-sucks`-Abhängigkeit und rund 700 Zeilen Code. Wer daneben einen alten Deebot
betreibt, nutzt dafür weiter die offizielle Integration.

## Zonensteuerung

Je erkannter Zone ein eigenes Gerät **„&lt;Mäher&gt; Zone N"** mit

- **Schnitthöhe** (`mowHeightLevel`)
- **Geschwindigkeit** (`cutMode`)
- **Umgebung** (`obstacleHeight`, Auswahlfeld)
- **Mährichtung** (`angle`)
- **Mähen starten** — startet genau diese Zone

sowie **„&lt;Mäher&gt; Zonensteuerung"** mit

- **Kantenschnitt starten** — der „Trimmer-Schnitt" der App
- **Mähen stoppen** — stoppt Zonenmähen und Kantenschnitt gleichermaßen
- **Mähstatus** (Auftragsart, aktuelle Zone, Akku, Ladezustand)

Beide Geräte hängen im Gerätebaum unter dem Mäher.

**Andocken** braucht keine eigene Entity: das erledigt `lawn_mower.dock` am
Mäher selbst (es sendet `charge {"act": "go"}`).

Zonen, die später in der Ecovacs-App dazukommen, erscheinen beim nächsten
Aktualisierungslauf automatisch.

### Gesperrt, solange der Mäher fährt

Parameter lassen sich nur ändern, wenn der Mäher **pausiert oder angedockt**
ist — während der Fahrt übernimmt er sie nicht zuverlässig. Betroffen sind alle
schreibbaren Entities: Schnitthöhe, Geschwindigkeit, Umgebung, Mährichtung
sowie Regenverzögerung, Tierschutz und Richtungswechsel.

Als „unterwegs" gilt `getCleanInfo` mit `state` `clean` (mähen) oder
`goCharging` (Rückfahrt), sofern `motionState` nicht `pause` ist. Die Entities
werden dann ausgegraut; ein trotzdem abgesetzter Dienstaufruf wird mit einer
Meldung abgelehnt, denn vor jedem Schreiben wird der Zustand frisch abgefragt.
Ist der Status ausnahmsweise nicht lesbar, wird **nicht** gesperrt — sonst wäre
bei einem Aussetzer nichts mehr einstellbar.

Start- und Stopp-Buttons aktualisieren den Zustand sofort, die Sperre greift
also nicht erst beim nächsten regulären Lauf.

### Zonennamen

Die Namen kommen automatisch aus der Karte. `getAreaParameter` kennt nur
`areaID`s, aber `getAreaSet` liefert die Bereichstabelle der aktiven Karte:

```jsonc
// getAreaSet  {"mid": "<aktive mid>", "aid": "0", "type": "ar"}
// -> subsets, base64 + LZMA, entpackt:
[["1","1","",           "","-1000", "0",    "0-0"],
 ["2","2","Mähfläche 1","","-4150", "7900", "0-0"],
 ["3","3","Mähfläche 2","","-12800","-9200","0-0"]]
```

Je Zeile: `areaID`, mssid, **Name**, ?, x, y, ?. Entscheidend sind die `mid` der
aktiven Karte (aus `getCachedMapInfo`, Eintrag mit `using: 1`) und `aid: "0"`
für „alle Bereiche" — genau so fragt die Ecovacs-App. Mit einer konkreten `aid`
oder ohne `mid` antwortet der Mäher mit einem leeren Datensatz.

Die Zonen-Geräte heißen deshalb „&lt;Mäher&gt; Mähfläche 1" statt „Zone 2". In
Home Assistant umbenennen geht weiterhin und überschreibt das dauerhaft.

### Verwaiste Bereiche

`getAreaParameter` liefert auch Datensätze gelöschter Flächen. Sie sind an dem
**leeren Namen** in der Kartentabelle zu erkennen (oben `areaID 1`) und bekommen
keine Entities.

Am Testgerät kamen drei Datensätze für zwei Mähflächen zurück, und
Schreibvorgänge auf den verwaisten blieben folgenlos: der Mäher speichert sie,
aber weder App noch Mähauftrag beachten sie. Ein Gegentest bestätigte das — nach
einer Änderung in der App bewegten sich `areaID 2` und `3`, während `areaID 1`
den Wert behielt, den diese Integration Stunden zuvor gesetzt hatte.

Kann die Karte nicht gelesen werden, gilt vorsichtshalber niemand als verwaist
und alle Bereiche erscheinen wie bisher unter ihrer Nummer.

### Push statt Warten

Der Mäher meldet jede Änderung der Zonenparameter von sich aus als
`onAreaParameter` — auch die, die in der Ecovacs-App gemacht wurde.
deebot-client kennt diese Nachricht nicht; die Integration ergänzt sie in dessen
Nachrichten-Registry (`deebot_client.messages.json.MESSAGES`) und legt daraus
ein eigenes Event auf den Event-Bus des Geräts.

Die Entities stehen damit sofort auf dem neuen Wert statt erst beim nächsten
Abfragelauf. Das reguläre Abfragen alle zwei Minuten bleibt als Rückfallebene
bestehen; kennt deebot-client die Nachricht eines Tages selbst, bleibt dessen
Eintrag unangetastet.

### Stufen und angezeigte Werte

Der Mäher speichert **Stufen**, die App zeigt physikalische Werte — und alle drei
Skalen laufen **gegenläufig** zur Stufe. Die Entities zeigen und nehmen den Wert
der App, umgerechnet über `Anzeige = offset + faktor × Stufe` (`scale.py`).

| Feld | Entity | Umrechnung | Grenzen des Geräts |
| --- | --- | --- | --- |
| `mowHeightLevel` | Schnitthöhe | `cm = 10 − Stufe` | **3–9 cm** |
| `cutMode` | Geschwindigkeit | `m/s = 0,75 − 0,05 × Stufe` | **0,40–0,70 m/s** |
| `angle` | Mährichtung | `° = 270 − Stufe` | **0–180°** |

Die Grenzen sind die des Geräts, nicht geschätzt: schneller als 0,7 m/s,
langsamer als 0,4 m/s, höher als 9 cm oder tiefer als 3 cm nimmt es nicht an.

Belegt gegen die App-Anzeige zweier Flächen desselben Mähers:

| | Gespeichert | Formel | App zeigte |
| --- | --- | --- | --- |
| Mähfläche 1 (`areaID 2`) | 5 / 7 / 152 | 5 cm, 0,40 m/s, 118° | 5cm, 0.4m/s, 118° |
| Mähfläche 2 (`areaID 3`) | 3 / 4 / 268 | 7 cm, 0,55 m/s, 2° | 7cm, 0.55m/s, 2° |

`cutMode` heißt im Protokoll nach dem Mähmodus, steuert aber die
Fahrgeschwindigkeit — die Entity heißt deshalb **Geschwindigkeit**.

### Umgebung statt Hindernishöhe

`obstacleHeight` klingt nach einer Länge, wählt aber die Umgebung. Stufe 0 nimmt
das Gerät nicht an, deshalb ist es ein Auswahlfeld mit drei Möglichkeiten:

| Stufe | Auswahl |
| --- | --- |
| 1 | Flacher Untergrund, kurzes Gras |
| 2 | Normale Umgebung |
| 3 | Hohes Gras |

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

// clean — Kantenschnitt („Trimmer-Schnitt")
{"act": "start", "content": {"type": "borderrotate",
                             "value": "reid:1;reid:3;reid:4;reid:5;reid:2"}}
{"act": "stop",  "content": {"type": "borderrotate"}}

// charge — andocken (deckt lawn_mower.dock ab)
{"act": "go"}
```

Die `reid`-Liste des Kantenschnitts steht nicht in einem eigenen Kommando: die
Integration liest sie aus dem Mähplan (`getSchedules`, Eintrag mit
`"mowType": 3`, Feld `ids`) und lässt dessen zusätzliches `vid:`-Element weg —
genau so schickt die App das clean-Kommando. Wer in der App noch nie einen
Kantenschnitt im Zeitplan angelegt hat, bekommt beim Drücken des Buttons einen
entsprechenden Hinweis.

Beim Stoppen erwartet der Mäher denselben `type`, mit dem gestartet wurde.
**Mähen stoppen** fragt deshalb erst `getCleanInfo` ab (`cleanState.content.type`)
und schickt den passenden Stopp; ist nichts ermittelbar, bleibt es bei
`spotArea`.

Der Status kommt aus `getCleanInfo`, `getBattery` und `getChargeState`. Schlägt
eines fehl, bleibt nur dessen Wert leer.

## Mäher-Einstellungen

Kommandos, die `deebot-client` nicht kennt; Namen aus einer MQTT-Aufzeichnung
der App, Antwortformate am Gerät abgefragt (Firmware 1.11.31).

| Entity | Kommando | Antwort |
| --- | --- | --- |
| **Regenverzögerung** (Schalter) + **Wartezeit** (Minuten) | `getRainDelay` / `setRainDelay` | `{"enable": 1, "delay": 150}` |
| **Tierschutz** (Schalter) + **Zeitfenster** (Sensor) | `getAnimProtect` / `setAnimProtect` | `{"enable": 1, "start": "19:0", "end": "7:15"}` |
| **Richtung wöchentlich wechseln** (Schalter) | `getAutoCutDirection` / `setAutoCutDirection` | `{"enable": 1}` |
| **Mähplan** (Sensor) | `getSchedules` | `{"list": [{"sid", "name", "subsets": <lzma>}]}` |
| **Position** (Sensor, standardmäßig aus) | `getPos` `{"type": "deebotPos"}` | `{"deebotPos": {"x", "y", "a", "invalid"}, …}` |

Die `set`-Kommandos erwarten wie `setAreaParameter` immer den vollständigen
Datensatz; die Integration ergänzt die unveränderten Felder selbst.

Der Mähplan steckt wie die Bereichsnamen in einem LZMA-Feld:

```jsonc
[{"ssid":"1","sDay":0,"eDay":0,"sTime":"10:00","eTime":"16:00",
  "mowType":1,"workType":1,"isOpen":1}, …,
 {"ssid":"8","sDay":1,"sTime":"16:00","eTime":"17:15","mowType":3,
  "ids":"reid:1;reid:3;…;vid:1","duration":900,"isOpen":1}]
```

`sDay` zählt ab Montag, `mowType` 1 ist Flächenmähen und 3 Kantenmähen. Der
Sensor zeigt die Zahl der aktiven Einträge und den ganzen Plan als Attribut.
Schreiben ist nicht umgesetzt — dafür fehlt eine Aufzeichnung von `setSchedules`.

**Der automatische Richtungswechsel erklärt wandernde Winkel:** Ist er aktiv,
setzt der Mäher `angle` selbst um, und ein in Home Assistant gesetzter Wert hält
nicht. Wer die Mährichtung fest vorgeben will, schaltet ihn zuerst ab.

## Karte: Sachstand

Eine Kartendarstellung ist noch nicht möglich. Am Gerät abgefragt:

| Kommando | Ergebnis |
| --- | --- |
| `getAreaSet` `{mid, aid, type: "ar"}` | Namen und **je einen Punkt** pro Fläche — keine Umrisse. `aid` wird ignoriert, sobald `mid` gesetzt ist |
| `getMapTrack` | `code 10000 "getMapTrack fail"` im Dock; die Fahrspur gibt es offenbar nur während des Mähens |
| `getSpecialContour` `{mid}` | antwortet mit `code 0`, aber ohne Daten |
| `getMI` | verlangt einen `type`, den keine Aufzeichnung nennt |
| `getMapSet`, `getMapSet_V2`, `getMapSubSet` | keine Antwort (`errno 500`, Zeitüberschreitung) |

Damit fehlt die Geometrie: Flächenumrisse und Hintergrundbild. Was es gibt, sind
Mittelpunkte und die Position des Mähers — zu wenig für eine Karte, die diesen
Namen verdient.

Der aussichtsreiche Weg ist derselbe, der die Bereichsnamen gebracht hat: eine
MQTT-Aufzeichnung, **während die App die Karte anzeigt**. Die Kartenansicht
schickt `getMapTrack`, `onMapTrack` und `getAreaSet` in Serie; daraus wären die
richtigen Parameter und das Format des Bilddatenstroms ablesbar.

## Unbekannte Geräteklassen

deebot-client löst die Fähigkeiten über die **Geräteklasse** auf. Fehlt eine
Definition, erscheint `Device class '...' not recognized` und es entstehen gar
keine Entities.

Der GOAT A1600 LiDAR Pro (`e4gqia`) ist davon **nicht** betroffen: deebot-client
pflegt Modelle mit geteiltem Capability-Satz über Symlinks (198 der 244 Einträge
im `hardware`-Verzeichnis), `e4gqia.py` → `aadham.py` → `51rcxt.py`.

Nennt dein Log dennoch eine unbekannte Klasse, trag sie in `const.py` unter
`UNSUPPORTED_CLASSES` ein — sie wird dann zur Laufzeit mit dem Capability-Satz
eines Schwestermodells angemeldet. Bitte melde sie zusätzlich
[upstream](https://github.com/DeebotUniverse/client.py/issues).

## Installation

### HACS

1. HACS → Dreipunktmenü → *Benutzerdefinierte Repositories*
2. `https://github.com/Zendonir/Ecovacs-GOAT-custom-integration` hinzufügen,
   Kategorie **Integration**
3. **Ecovacs GOAT** installieren und Home Assistant neu starten

> Nicht zu verwechseln mit *Einstellungen → Add-ons → Add-on-Store →
> Repositories*: der erwartet Add-on-Repositories und lehnt dieses hier mit
> „is not a valid app repository" ab.

### Manuell

`custom_components/ecovacs_goat` (komplett, inklusive `translations/`) nach
`<HA-Config>/custom_components/` kopieren und Home Assistant neu starten.

### Einrichten

*Einstellungen → Geräte & Dienste → Integration hinzufügen → **Ecovacs GOAT***.

Abgefragt werden **Benutzername, Passwort und Land** deines Ecovacs-Kontos —
dieselben wie in der App. Seit Juli 2026 verlangt Ecovacs zusätzlich einen
**Bestätigungscode per E-Mail** für jede neue Client-ID; der Dialog fragt ihn ab,
sobald er nötig ist.

## Wichtig beim Umstieg

- **Nicht beide Integrationen parallel betreiben.** Sonst bekommst du jede
  Entity doppelt. Entferne die offizielle Ecovacs-Integration (oder diese hier),
  wenn du dich entschieden hast.
- **Zwei Sitzungen am Konto.** Läuft beides gleichzeitig, hältst du zwei
  MQTT-Verbindungen zum Ecovacs-Konto offen.
- **`deebot-client`-Version.** Dieser Fork verlangt `18.5.1`; die offizielle
  Integration pinnt eine andere Version (z. B. `18.4.0`). Home Assistant
  installiert Anforderungen **global** — bei parallelem Betrieb gewinnt beim
  Neustart eine davon, und die andere Integration bricht. Symptom:

  ```
  Setup failed for custom integration 'ecovacs_goat': Unable to import
  component: cannot import name 'DeviceVerificationRequiredError' from
  'deebot_client.exceptions'
  ```

  `DeviceVerificationRequiredError` gibt es erst ab `deebot-client` 18.5.0.
  Erscheint das, wurde die Bibliothek von der anderen Integration
  heruntergestuft: eine der beiden entfernen und neu starten. Die Zugangsdaten
  im Config Entry bleiben davon unberührt — der Eintrag lädt nach dem Neustart
  von selbst wieder.
- **Alte Einträge dieser Integration.** Fassungen vor 2.0 setzten auf der
  offiziellen Integration auf und hatten keine eigenen Zugangsdaten. Solche
  Einträge lassen sich nicht migrieren: entfernen und neu hinzufügen.

## Tests

```bash
pip install deebot-client pytest pytest-asyncio
pytest
```

Die Tests laufen ohne Home-Assistant-Installation und decken die
Zonen-Protokollschicht (gesendete Kommandos und Antwortauswertung gegen ein
Fake-Device) sowie die Registry-Anmeldung gegen ein echtes `deebot-client` ab.
Sie sind bewusst unabhängig von der `deebot-client`-Version gehalten.

## Fehlersuche

```yaml
logger:
  logs:
    custom_components.ecovacs_goat: debug
    deebot_client: debug
```

`deebot-client` fängt Fehler in `Command.execute()` ab und liefert dann eine
leere Antwort — die eigentliche Ursache steht deshalb nur im `deebot_client`-Log.

## Lizenz

Apache-2.0. Der Code unter `custom_components/ecovacs_goat/` stammt aus
[home-assistant/core](https://github.com/home-assistant/core) (Tag `2026.8.2`);
Einzelheiten zu den Änderungen stehen in [NOTICE](NOTICE).
