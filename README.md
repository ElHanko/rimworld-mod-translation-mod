# Deutsche Übersetzungen für RimWorld-Mods

Dieses Projekt ergänzt fehlende deutsche Übersetzungen aktiver RimWorld-Mods,
ohne Steam-Workshop-Dateien direkt zu verändern. Die Übersetzungen liegen in
einem separaten lokalen Mod mit der Package-ID
`elhanko.rimworld.germantranslations`. Dieser muss nach den Quellmods geladen
werden.

Der aktuelle Stand unterstützt **RimWorld 1.6**. Andere Versionen sind nicht als
getestet dokumentiert.

## Aufbau und Git-Bestand

Der Übersetzungsworkflow hat drei Ebenen:

| Pfad | Aufgabe | In Git |
| --- | --- | --- |
| `translations/*.json` | Dauerhafter, bearbeitbarer Übersetzungsbestand mit Englisch, Deutsch, Translation Key bzw. Def-Pfad und Review-Status | Ja |
| `Languages/German/` | Von `./rwgt build PACKAGE-ID` erzeugte RimWorld-XML-Dateien unter `Keyed/` und `DefInjected/` | Ja |
| `data/` | Lokale Reports, Analysen und Arbeitsdateien aus der Installation und dem aktuellen RimWorld-Report | Nur die leere `data/.gitkeep` |

Die JSON-Drafts sind Quellbestand und bleiben auch nach erfolgreicher
Übersetzung erhalten. Aktuell gibt es Drafts für `jaxe.rimhud`,
`vanillaexpanded.vtexe` und `m00nl1ght.worldtechlevel`. Für
`andromeda.niceplantsmenu` liegt derzeit nur die fertige Keyed-XML-Datei vor.

Die XML-Dateien werden ebenfalls versioniert, weil RimWorld sie direkt lädt.
Damit lässt sich ein funktionierender Übersetzungsstand aus Git wiederherstellen,
ohne zunächst die lokale Analyse oder einen Build auszuführen. Vollständig
qualifizierte Def-Typen bleiben als Verzeichnisnamen erhalten, etwa
`Languages/German/DefInjected/ModSettingsFramework.ModOptionCategoryDef/`.

Zum versionierten Projekt gehören außerdem `About/` mit den Mod-Metadaten,
`scripts/` mit den Python-Werkzeugen, der Shell-Starter `rwgt`, diese README
und `.gitignore`.

`data/TranslationReport.txt` ist lokal ein Symlink auf einen von RimWorld
erzeugten Bericht. `data/report-summary.txt`, `data/report-mapped.jsonl`,
`data/report-unmapped.txt` und `data/report-ambiguous.txt` sind daraus erzeugte
Analysen. `data/language-inventory.txt` enthält die lokale Sprachinventur;
`data/work/*.json` sind reproduzierbare Arbeitsdateien. Diese Inhalte können
Installationspfade, die aktive Modliste und andere Rechnerdaten enthalten und
werden ignoriert. Vorhandene lokale Dateien bleiben dabei erhalten.

Auch Python-Caches, virtuelle Umgebungen, temporäre Dateien, Editorreste und
lokale Backups werden ignoriert. Private Konfigurationen gehören beispielsweise
in `.env`, `.env.*`, `*.local` oder `*.local.*`; weitere lokale Arbeitsdaten
gehören unter `data/`.

## Installation und Voraussetzungen

Zum Verwenden der fertigen Übersetzungen werden RimWorld 1.6 und die jeweiligen
Quellmods benötigt. Für die Werkzeuge werden eine POSIX-Shell und Python 3 mit
`xml.etree.ElementTree.indent` (ab Python 3.9) benötigt; externe Python-Pakete
werden nicht verwendet.

Das Repository wird über einen Symlink im lokalen RimWorld-Mod-Verzeichnis
eingebunden. Die folgenden Platzhalter müssen durch die eigenen Pfade ersetzt
werden:

```bash
ln -s /pfad/zum/rimworld-german-translations \
  /pfad/zu/RimWorld/Mods/ElHanko-German-Translations
```

Danach den Übersetzungsmod in RimWorld aktivieren, **nach den Quellmods** laden
und Deutsch als Sprache verwenden. Die Workshop-Mods bleiben unverändert.

Die Analysewerkzeuge sind aktuell auf die bestehende lokale Linux-Installation
zugeschnitten: Steam- und Workshop-Verzeichnisse stehen als Konstanten in
`scripts/rwgt.py`, `scripts/analyze-report.py` und
`scripts/inventory-languages.py`. Die aktive Modliste wird aus der
Linux-Benutzerkonfiguration `ModsConfig.xml` gelesen. `refresh` sucht Berichte
unter `~/Desktop`. Diese Annahmen müssen bei einer anderen Installation geprüft
werden; eine allgemeine Pfadkonfiguration gibt es derzeit nicht.

Der vorhandene Befehl `./rwgt install` legt den Mod-Symlink am im Skript
festgelegten lokalen Steam-Pfad an. Das obige manuelle Beispiel erlaubt es,
den Zielpfad für die eigene Installation ausdrücklich zu wählen.

## Befehle

Alle Beispiele werden im Repository ausgeführt. `PACKAGE-ID` steht für die
Package-ID des Quellmods, beispielsweise `jaxe.rimhud`.

| Befehl | Rolle |
| --- | --- |
| `./rwgt refresh` | Aktuellen RimWorld-Report einlesen, aktive Mods analysieren, fehlende Übersetzungen zuordnen und Def-Typen anhand echter Quell-Defs auflösen; anschließend Status und XML-Validierung ausgeben |
| `./rwgt status` | Fehlende Einträge laut letzter Analyse und bereits vorhandene eigene Übersetzungen je Paket anzeigen |
| `./rwgt validate` | Alle deutschen XML-Dateien auf gültiges XML, den Wurzelknoten `LanguageData` und doppelte Keyed-Schlüssel prüfen |
| `./rwgt work PACKAGE-ID` | Reproduzierbare Arbeitsdatei unter `data/work/` aus den aktuell zugeordneten fehlenden Einträgen erstellen |
| `./rwgt draft PACKAGE-ID` | Arbeitsdatei erneuern und persistenten Übersetzungs-Draft erstellen oder aktualisieren |
| `./rwgt progress PACKAGE-ID` | Anzahl übersetzter, offener und als Review markierter Draft-Einträge anzeigen |
| `./rwgt build PACKAGE-ID` | Vollständig übersetzten, geprüften Draft als RimWorld-XML bauen und XML validieren |
| `./rwgt verify PACKAGE-ID` | Gebauten Bestand und gegebenenfalls Draft-Anzahl mit der letzten Analyse des Runtime-Reports vergleichen |

`refresh` wählt die zuletzt geänderte Datei unter `~/Desktop`, deren Name
`TranslationReport*.txt` oder `translationreport*.txt` entspricht. Es erneuert
den Symlink `data/TranslationReport.txt` und die Report-Analysen. Den Report
selbst muss RimWorld erzeugen. Die Def-Typ-Auflösung liest die statischen
Quell-Defs für den aktuellen 1.6-Stand.

`draft` bewahrt vorhandene deutsche Texte und bereits bearbeitete Einträge,
auch wenn sie nicht mehr als fehlend im Report erscheinen. Wird bei einem
erneut gemeldeten Eintrag ein geänderter englischer Ausgangstext erkannt,
setzt es `review: true` und merkt den vorherigen Text als `previous_english`.
Vollständig qualifizierte Def-Typen werden anhand der Quellmods normalisiert.
Nach inhaltlicher Prüfung wird der deutsche Text angepasst und `review`
wieder auf `false` gesetzt.

`build` erzeugt nur einen vollständig übersetzten und nicht mehr als Review
markierten Paketbestand. Bei leeren deutschen Texten, offenen Reviews,
Placeholder-Abweichungen oder nicht eindeutig auflösbaren Def-Typen bricht
der Befehl ab; es gibt keinen Teilbuild. Er schreibt Keyed-XML und je Def-Typ
eine DefInjected-XML unter `Languages/German/` und führt anschließend
`validate` aus.

`verify` verwendet die durch `refresh` erzeugte Auswertung des aktuellen
RimWorld Translation Reports zur tatsächlichen Laufzeitverifikation. Dazu
müssen Quellmods und Übersetzungsmod aktiv sein und der Report nach dem Laden
des neuen Builds erzeugt worden sein. Der Befehl startet RimWorld nicht und
erneuert den Report nicht selbst. Er prüft offene Zuordnungen je Paket und
die Anzahl gebauter Einträge gegenüber dem Draft; ohne Draft meldet er
„im Report vollständig, aber kein Draft vorhanden“. Ein alter Report oder
eine veränderte aktive Modliste ist keine Bestätigung für einen neuen Build.

Das zusätzliche Skript `scripts/inventory-languages.py` listet die aktiven
Mods und ihre Sprachverzeichnisse auf. Seine Ausgabe kann lokal mit
`python3 scripts/inventory-languages.py > data/language-inventory.txt`
gespeichert werden.

## Typischer Ablauf

Zunächst in RimWorld einen aktuellen Translation Report erzeugen und unter
dem vom Werkzeug erwarteten Desktop-Verzeichnis bereitstellen. Dann:

```bash
./rwgt refresh
./rwgt draft PACKAGE-ID

# translations/PACKAGE-ID.json übersetzen und offene Reviews bearbeiten

./rwgt progress PACKAGE-ID
./rwgt build PACKAGE-ID
```

Danach **RimWorld neu starten und einen neuen Translation Report erzeugen**.
Anschließend:

```bash
./rwgt refresh
./rwgt verify PACKAGE-ID
```

Die bearbeiteten JSON-Drafts und die erzeugten XML-Dateien gehören gemeinsam
in den versionierten Bestand. Die Reports und Arbeitsdateien bleiben lokal.

## Keyed, DefInjected und Platzhalter

**Keyed** übersetzt explizite Translation Keys. **DefInjected** übersetzt
Felder in RimWorld-Defs, beispielsweise `VTE_General.label`. Bei
benutzerdefinierten Def-Klassen muss der vollständige Typname erhalten
bleiben: `ModSettingsFramework.ModOptionCategoryDef` darf im
DefInjected-Verzeichnis nicht auf `ModOptionCategoryDef` verkürzt werden.

Platzhalter wie `{0}`, `{1}` und `{name}` dürfen nicht verändert oder entfernt
werden. Ihre Schreibweise und jeweilige Anzahl müssen mit dem englischen
Text übereinstimmen. Der Build prüft diese einfachen numerischen und benannten
Platzhalter vor der XML-Erzeugung; ihre Position im Satz darf sich ändern.

## Verifizierter Stand als Momentaufnahme

Die folgende Tabelle dokumentiert den zuletzt in RimWorld verifizierten
Stand. Modupdates und Änderungen an der aktiven Modliste können die Zahlen
und die Wirksamkeit verändern.

| Package-ID | Keyed | DefInjected | Laufzeitstand |
| --- | ---: | ---: | --- |
| `andromeda.niceplantsmenu` | 59 | 0 | vollständig wirksam |
| `jaxe.rimhud` | 284 | 0 | vollständig wirksam |
| `vanillaexpanded.vtexe` | 5 | 1 | vollständig wirksam |
| `m00nl1ght.worldtechlevel` | 100 | 1 | vollständig wirksam |
| **Gesamt** | **448** | **2** | **450 Übersetzungseinträge** |

Für Nice Plants Menu fehlt aktuell der JSON-Draft; deshalb kann `verify`
dort nur den vollständigen Report-Stand ohne Draft-Abgleich melden.

Der zuletzt geprüfte RimWorld-Report enthielt insgesamt **1584 fehlende
Keyed-Übersetzungen** und **7853 fehlende DefInjected-Übersetzungen**. Auch
diese Werte sind eine Momentaufnahme der lokalen Modliste, keine feste
Projektkennzahl.

Im bisherigen Workflow wurden Keyed und DefInjected vom Übersetzungsbestand
bis zur Wirksamkeit in RimWorld validiert, einschließlich benutzerdefinierter
Def-Klassen mit Namespace. Ebenso wurde das Erhalten bestehender
Übersetzungen beim Aktualisieren eines Drafts geprüft. Der Runtime-Report
dient zur tatsächlichen Verifikation; reine XML-Validierung bestätigt nur
die technische Dateistruktur.

## Grenzen

- Steam-Workshop-Mods werden nicht verändert.
- Laufzeitgenerierte Defs lassen sich nicht immer direkt einer statischen
  Quelldatei zuordnen.
- Mehrdeutige Zuordnungen müssen gegebenenfalls separat geprüft werden;
  die Analyse hält sie unter `data/report-ambiguous.txt` fest.
- Hardcodierte C#-Strings ohne Translation Key sind mit diesem
  Übersetzungsmod nicht automatisch übersetzbar.
- Vorhandene fehlerhafte Übersetzungen aus anderen Mods gehören nicht
  automatisch zum Umfang dieses Projekts.

## Lokale Validierung

```bash
python3 -m py_compile scripts/*.py
./rwgt validate
git diff --check
git status --short
git status --ignored --short
```

`validate` prüft die XML-Dateien; Placeholder-Prüfung erfolgt beim Build,
Laufzeitverifikation nach einem neuen Report mit `refresh` und `verify`.
