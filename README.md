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
- **Mähmodus** (`cutMode`)
- **Hinderniserkennung** (`obstacleHeight`)
- **Mährichtung** (`angle`)
- **Mähen starten** — startet genau diese Zone

sowie **„&lt;Mäher&gt; Zonensteuerung"** mit **Zonenmähen stoppen** und einem
**Mähstatus**-Sensor (aktuelle Zone, Akku, Ladezustand). Beide hängen im
Gerätebaum unter dem Mäher.

Zonen, die später in der Ecovacs-App dazukommen, erscheinen beim nächsten
Aktualisierungslauf automatisch.

### Zonennamen

Das Geräteprotokoll kennt **keine** Zonennamen — nur numerische `areaID`s. Am
Gerät abgefragt (GOAT A1600 LiDAR Pro, Firmware 1.11.31):

| Kommando | Ergebnis |
| --- | --- |
| `getAreaParameter` | nur `areaID` + die vier Mähparameter, kein Name |
| `getCachedMapInfo` | antwortet; `name` ist bei allen Karten leer, und es ist ohnehin der Kartenname |
| `getAreaSet` `{type: "ar", aid: N}` | antwortet; `subsets` entpackt zu **0 Byte**, für jede `aid` identisch |
| `getMapSet`, `getMapSet_V2`, `getMapSubSet` | keine Antwort (`errno 500`, „wait for response timed out") |

Die Namen liegen also nicht auf dem Mäher, sondern im Ecovacs-Konto. Sie zu
holen hieße, die App-REST-API mitzuschneiden — ein anderer Angriffspunkt als der
Gerätekanal, über den diese Integration läuft. Die App selbst vergibt ohnehin
nur generische Namen („Mähfläche 1", „Mähfläche 2"), solange man sie nicht
umbenennt.

**Zuordnung von Hand:** Setze in Home Assistant für eine Zone eine auffällige
Schnitthöhe und sieh in der App nach, welche Mähfläche sich geändert hat
(Zonendialog schließen und neu öffnen, die App cacht). Achtung: die Nummern
stimmen nicht überein — im Testgerät war `areaID 1` die „Mähfläche 2" und
`areaID 2` die „Mähfläche 1". Danach das Gerät in Home Assistant umbenennen; die
Entity-IDs hängen an der `did` und der `areaID`, Umbenennen bricht also nichts.

### Zonen, die es nicht mehr gibt

`getAreaParameter` liefert offenbar auch Einträge gelöschter Zonen: Im Testgerät
kamen drei Datensätze zurück, obwohl in der App nur zwei Zonen angelegt waren.
Alle drei nennen `mid: "0"`, während die aktive Karte `mid: "1"` ist. Die
Integration kann echte nicht von verwaisten Zonen unterscheiden und legt für
jeden Datensatz ein Gerät an. Überzählige Zonen-Geräte lassen sich in Home
Assistant deaktivieren.

### Wertebereiche

Die echten Grenzen der Ecovacs-App sind nicht bekannt. Die Min-/Max-Werte sind
vorsichtig geschätzt; das Attribut `beobachteter_bereich` an jeder
Number-Entity zeigt, was in der Aufzeichnung real vorkam:

| Parameter | Eingestellt | Beobachtet |
| --- | --- | --- |
| `mowHeightLevel` (cm) | 1–11 | 3–7 |
| `cutMode` | 1–10 | 4 / 7 |
| `obstacleHeight` | 0–3 | 1–2 |
| `angle` | 0–360 | 90–268 |

Werte außerhalb des beobachteten Bereichs sind ungetestet. Anpassbar in
`const.py` (`ZONE_FIELD_SPECS`).

### Ungeklärt: wirkt setAreaParameter überhaupt?

**Die Zonenparameter sind nicht als wirksam bestätigt.** Am Testgerät gilt:

* `setAreaParameter` wird mit `code 0` quittiert, und `mowHeightLevel` bleibt
  über Stunden und viele Abfragen hinweg stehen — geschrieben wird also etwas.
* In der Ecovacs-App ändert sich dadurch **nichts**, weder Schnitthöhe noch
  Winkel.
* `angle` bleibt nicht stehen: für den beschriebenen Bereich wanderte er von 180
  über 20 auf 50, während der Mäher angedockt war. Die anderen Bereiche
  behielten ihre Werte.
* `getAreaSet` meldet für alle Bereiche `mid: "0"`, aktiv ist laut
  `getCachedMapInfo` aber `mid: "1"`. Ein `mid` im Aufruf von
  `getAreaParameter` wird ignoriert.

Das deutet darauf hin, dass diese Tabelle zu einer **älteren Karte** gehört und
nicht die ist, aus der die App und der laufende Mähauftrag ihre Werte nehmen.
Bestätigt ist das nicht.

Der entscheidende Test steht aus: eine Schnitthöhe **in der App** ändern und
danach `getAreaParameter` lesen. Folgt der Gerätewert, ist es dieselbe Tabelle
und die App zeigt nur veraltet an; ändert sich nichts, schreibt die App
woandershin und die Zonenparameter dieser Integration laufen ins Leere.

Unberührt davon sind Start und Stopp einzelner Zonen (`clean` mit `spotArea`) —
die stammen aus einer MQTT-Aufzeichnung eines echten App-Vorgangs.

Ob `mowHeightLevel` Zentimeter meint, ist damit ebenfalls offen: die App zeigte
„5cm" und „7cm" bei gespeicherten 5 und 7, was passt, aber ohne die
Gegenprobe Zufall sein kann. Die Entity trägt die Einheit vorerst aus.

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

Der Status kommt aus `getCleanInfo`, `getBattery` und `getChargeState`. Schlägt
eines fehl, bleibt nur dessen Wert leer.

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
