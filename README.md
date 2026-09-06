# Deutsche Übersetzungen für RimWorld-Mods

Dieses Projekt ergänzt fehlende deutsche Übersetzungen aktiver RimWorld-Mods
in einem separaten Mod (`elhanko.rimworld.germantranslations`). Er muss **nach
den Quellmods** geladen werden. Unterstützt und bisher getestet ist RimWorld 1.6.
Workshop-Dateien bleiben unverändert. Die Werkzeuge benötigen eine POSIX-Shell
und Python ab 3.9; sie verwenden ausschließlich die Standardbibliothek.

## Aufbau

| Pfad | Bedeutung | Versioniert |
| --- | --- | --- |
| `translations/*.json` | Dauerhafte Wahrheit: Englisch, Deutsch, Identitäten und Bearbeitungszustand | Ja |
| `Languages/German/` | Vollständig und deterministisch aus Drafts generierter Runtime-Bestand | Ja |
| `data/status.json` | Letzte Analyse einschließlich Report-Metadaten, aktiver Mods, Resolver und Runtime-Nachweis | Nein |
| `data/work/*.work.json` | Temporäre Arbeitspakete | Nein |
| `data/` | Reproduzierbare lokale Reports, Analysen und Arbeitsdaten | Nur `.gitkeep` |
| `rwgt.local.json` | Private lokale Pfade | Nein |
| `rwgt.example.json` | Öffentliche Konfigurationsvorlage | Ja |

XML-Dateien nicht von Hand übersetzen. Änderungen gehören in Drafts oder
Arbeitspakete. Ein Build benötigt keine Analyseartefakte: Der Runtime-Bestand
ist allein aus den versionierten Drafts reproduzierbar.

## Setup

```bash
cp rwgt.example.json rwgt.local.json
# Die vier Pfade in rwgt.local.json an die eigene Installation anpassen.
```

Die Konfiguration enthält genau vier absolute Pfade:

- `game`: RimWorld-Installationsverzeichnis.
- `workshop`: Workshop-Verzeichnis für App-ID `294100`.
- `rimworld_home`: RimWorld-Benutzerdaten mit `Config/ModsConfig.xml`.
- `report_dir`: Verzeichnis, in dem RimWorld-TranslationReports abgelegt werden.

`game/Mods` und `rimworld_home/Config/ModsConfig.xml` werden abgeleitet.
Fehlende oder ungültige Konfiguration führt bei allen Workflow-Befehlen zu
einem Fehler mit Hinweis auf die Vorlage. Es gibt keine privaten Standardpfade.
Die gemeinsame Logik liegt in `scripts/config.py`.

Optional bindet dieser Befehl das Repository als lokalen Mod ein:

```bash
./rwgt install
```

Ziel ist `game/Mods/ElHanko-German-Translations`. Ein bereits korrekter Symlink
bleibt bestehen. Ein falscher Symlink oder eine echte Datei/ein Verzeichnis am
Ziel führt zum Abbruch. Nur `install` schreibt in das lokale Mods-Verzeichnis.
Anschließend den Mod in RimWorld aktivieren und Deutsch auswählen.

## Standardworkflow

Zunächst einen deutschen TranslationReport in RimWorld erzeugen und unter
`report_dir` ablegen.

```bash
./rwgt refresh
./rwgt status
./rwgt draft --all
./rwgt progress
./rwgt work --next
# In der ausgegebenen Work-Datei german übersetzen und Reviews prüfen.
./rwgt apply data/work/PACKAGE-ID.work.json
./rwgt build
./rwgt verify
```

`refresh` liest die zuletzt geänderte Datei namens `TranslationReport*.txt`
(ohne Beachtung der Groß-/Kleinschreibung). Es ersetzt lokal
`data/TranslationReport.txt` durch eine Kopie, analysiert aktive Package-IDs,
ordnet Report-Einträge zu und löst Def-Typen anhand der Quellmods auf.
`status` stellt anschließend nur den gespeicherten Status dar; es scannt nichts.
`UNSERE` bezeichnet dabei den Bestand zum Zeitpunkt des letzten Refresh.

Der vorhandene Analyzer bleibt erhalten. Zusätzliche Details stehen in
`data/report-summary.txt`, `report-mapped.jsonl`, `report-ambiguous.txt`,
`report-unmapped.txt` und `analyzer.log`. Die Sprachinventur ist weiterhin mit
`python3 scripts/inventory-languages.py` verfügbar. Externe Quellen werden nur gelesen.

## Befehle

| Befehl | Wirkung |
| --- | --- |
| `./rwgt refresh` | Report und kanonischen Status erneuern |
| `./rwgt status` | Letzten Status anzeigen |
| `./rwgt draft PACKAGE-ID` | Einen dauerhaften Draft aktualisieren |
| `./rwgt draft --all` | Neue Drafts für eindeutig zugeordnete offene Einträge anlegen, alle vorhandenen aktualisieren |
| `./rwgt progress [PACKAGE-ID]` | Benötigt, übersetzt, offen, Review und nicht mehr benötigt anzeigen |
| `./rwgt work [PACKAGE-ID] [--limit N] [--offset N]` | Arbeitspaket erstellen; Standardlimit 25 |
| `./rwgt work --next` | Kleinsten noch offenen/reviewpflichtigen Draft auswählen |
| `./rwgt apply WORK-DATEI` | Vollständig prüfen und Änderungen atomar in den Draft übernehmen |
| `./rwgt build` | Gesamten Runtime-Bestand aus vollständigen Drafts neu erzeugen |
| `./rwgt verify` | Gesamtes Repository und gespeicherte Runtime-Bestätigung prüfen |
| `./rwgt validate` | XML-Struktur und doppelte Runtime-Identitäten prüfen |
| `./rwgt install` | Lokalen Mod-Symlink sicher einrichten |

`work` ohne Auswahl entspricht `work --next`. Gleichstände werden nach Package-ID
aufgelöst. `--offset` zählt innerhalb der aktuell offenen/reviewpflichtigen
Einträge. Nach einem Apply verschiebt sich diese Liste; gewöhnlich beginnt das
nächste Paket wieder bei Offset 0. `build PACKAGE-ID` und `verify PACKAGE-ID`
werden durch die globalen Befehle ersetzt.

## Draft-Zustand und Identitäten

Jeder Eintrag enthält `english`, `german`, `needed` und `review`
sowie `type`, `key` beziehungsweise `path`, Package-/Quellmetadaten und bei
DefInjected `def_name`, `def_type` und `def_resolution`.

- `needed=true`: Dieser Eintrag gehört weiterhin zu unserem deutschen Runtime-Mod.
- `needed=false`: Dieser Eintrag ist stillgelegt. Er bleibt samt deutscher Fassung erhalten.
- `review=true`: Der gemeldete englische Text hat sich geändert. Deutsch bleibt
  erhalten; `previous_english` hält den Text vor dem noch offenen Review fest,
  auch über mehrere Refresh-/Merge-Zyklen hinweg.

**RimWorld-Besonderheit:** Der Report sieht unsere eigenen Übersetzungen. Nach
einem erfolgreichen Build verschwinden diese aus der Fehlstellenliste.
Beim Merge bleibt ein zuvor benötigter Eintrag mit nichtleerem Deutsch daher
`needed=true`, auch bei offenem Review. Ein bisher benötigter, noch unübersetzter
Eintrag wird beim Verschwinden dagegen `needed=false`. Bereits stillgelegte
Einträge bleiben stillgelegt. Erscheint ein Eintrag erneut im Report, erhält er
wieder `needed=true`; vorhandenes Deutsch und offene Reviews bleiben erhalten.

Runtime-Bestätigung ist ausschließlich lokale Evidenz in `data/status.json`
und kein Zustandsfeld im Draft.

Der Report allein unterscheidet nicht sicher zwischen eigener erfolgreicher
Übersetzung, neuer Upstream-Übersetzung und entferntem Quell-Key. Eine bewusst
stillgelegte Übersetzung erhält im Draft `needed=false`. Der deutsche Text
bleibt archiviert; der Build schließt nicht mehr benötigte Einträge aus.

Keyed-Identitäten bestehen aus dem Key. DefInjected verwendet den Def-Pfad;
der vollständige Typ ist korrigierbares Metadatum. Bei tatsächlich mehrfach
verwendeten Pfaden in verschiedenen Def-Klassen ergänzt der Status
`identity_scope` aus dem kurzen Klassennamen. Diese Kennung bleibt im Draft
stabil. Eine nicht eindeutig mögliche Zuordnung alter Übersetzungen bricht ab.

## Arbeitspakete und Apply

Ein Arbeitspaket enthält nur benötigte Einträge mit leerem Deutsch oder offenem
Review, dazu Package-ID, Draft-Dateiname, Offset und Identitätsschutz.
`original_german` schützt zwischenzeitliche deutsche Änderungen. Identitäts-
und Quellfelder einschließlich dieses Schutzfeldes nicht bearbeiten.

Nach dem Übersetzen oder bewussten Bestätigen einer bestehenden Review-Fassung:

```bash
./rwgt apply data/work/PACKAGE-ID.work.json
```

Apply prüft alle Einträge vor dem ersten Schreibzugriff: Draft-Zuordnung,
Package-ID, eindeutige vorhandene Identität, weiterhin `needed=true`, exakt
passendes Englisch und ursprüngliches Deutsch, String-Typ und Placeholder.
Unbekannte oder doppelte Einträge führen zum Abbruch ohne Teilübernahme.
Leeres Deutsch wird übersprungen. Übernommene Einträge erhalten `review=false`;
`previous_english` entfällt und `needed=true` bleibt bestehen.

Ein bestehendes Arbeitspaket wird nicht überschrieben. Nach erfolgreicher
Übernahme kann es lokal entfernt oder umbenannt werden, bevor für denselben
Mod ein neues Paket erzeugt wird. Apply selbst lässt das Paket zur Kontrolle stehen.

## Globaler Build und Verify

Ein Draft ist vollständig, wenn alle benötigten Einträge übersetzt, ohne Review,
mit passenden Placeholdern und eindeutig aufgelösten Def-Typen vorliegen.
Unvollständige Drafts werden als Ganzes ausgeschlossen. Vollständige Drafts
liefern ausschließlich benötigte, technisch gültige und fertige Einträge.

Der Build berechnet zuerst den gesamten erwarteten Bestand, validiert XML und
Text-Roundtrips und schreibt ein temporäres Verzeichnis unter `Languages/`.
Erst anschließend ersetzt er `Languages/German/`, mit Rücknahme bei einem
fehlgeschlagenen Austausch. Veraltete Dateien bleiben nicht liegen.
Ein byteidentischer Bestand wird nicht neu geschrieben. Bei einem Prozess- oder
Stromausfall während des Verzeichnistauschs kann der Sicherungsordner
`Languages/.rwgt-build-*/previous` zur Wiederherstellung erforderlich sein.

Ausgabeziele sind `Keyed/PACKAGE-ID.xml` und
`DefInjected/FULL.DEF.TYPE/PACKAGE-ID.xml`. Namespaces wie
`HugsLib.UpdateFeatureDef` und `ModSettingsFramework.ModOptionCategoryDef`
bleiben exakt erhalten. Def-Quellen unter **`Defs/` und `News/`** werden weiterhin
berücksichtigt; alte Versionsordner, Sprachdateien und Patches werden nicht für
die statische Typauflösung verwendet.

Globale doppelte Keyed-Keys beziehungsweise DefInjected-Identitäten werden nur
bei exakt gleichem Englisch und Deutsch dedupliziert. Widersprüche brechen den
Build vor Änderungen ab. Innerhalb eines Drafts sind doppelte Identitäten Fehler.
Die vorhandene Placeholder-Prüfung zählt `{0}`, `{1}`, `{name}` usw. einschließlich
Mehrfachvorkommen. Sie ist keine vollständige RimWorld-Grammatikprüfung.

`verify` prüft Draft-Struktur, Pflichtfelder, Duplikate und Placeholder, vergleicht
Drafts mit `data/status.json` und berechnet denselben erwarteten XML-Bestand wie
Build. Fehlende, unerwartete, veränderte und falsch einsortierte Dateien werden
als Fehler gemeldet. Unvollständige Drafts allein sind kein Fehler.

## Update- und Übersetzungszyklus

Nach Workshop-/RimWorld-Updates:

```bash
./rwgt refresh
./rwgt draft --all
./rwgt progress
./rwgt verify
```

Wenn sich der erwartete Runtime-Bestand geändert hat, anschließend `build` und
`verify` ausführen. Neue oder geänderte Texte bearbeiten:

```bash
./rwgt work --next --limit 25
# german ausfüllen, Reviews prüfen
./rwgt apply data/work/PACKAGE-ID.work.json
./rwgt progress
./rwgt build
./rwgt verify
```

## Runtime-Test mit RimWorld

Lokale Konsistenz und Runtime-Bestätigung sind getrennte Aussagen. Ein neuer
Build kann lokal korrekt sein und trotzdem `Runtime: ausstehend` anzeigen.

1. RimWorld mit Quellmods und Übersetzungsmod neu starten.
2. Einen neuen deutschen TranslationReport erzeugen.
3. `./rwgt refresh` ausführen.
4. `./rwgt verify` ausführen.

Erfolgreich übersetzte Einträge bleiben nach verschwundenen Fehlstellen benötigt;
dies allein verursacht keinen Synchronitätsfehler. Neue oder geänderte
Fehlstellen weiterhin mit `./rwgt draft --all` synchronisieren.

Refresh speichert je Runtime-Paket einen semantischen Fingerabdruck im Status.
Eine Bestätigung setzt voraus, dass der Report keine entsprechenden Fehlstellen
oder zuordenbaren Ladefehler nennt, beide Mods in passender Reihenfolge aktiv
sind und der Report mindestens so neu wie XMLs und Modkonfiguration ist.
Ein bereits bestätigter, semantisch unveränderter Bestand behält seine Bestätigung
bei reinem Neuformatieren mit demselben Report. Geänderte Texte, Keys oder
Def-Ordner passen nicht mehr zum Fingerabdruck und sind zunächst ausstehend.

Die Bestätigung gilt für den gespeicherten Report. RimWorld wird nicht automatisch
gestartet. Der Report dokumentiert nicht vollständig die beim Spielstart geladene
Modkonfiguration; die Reihenfolge wird gegen die lokale `ModsConfig.xml` geprüft.
Nach verlorenen lokalen Analyseartefakten und neu geschriebenen XMLs kann der
Nachweis erneut ausstehen. Übersetzungs- und Build-Daten bleiben reproduzierbar.

## Grenzen und Tests

- Runtime-generierte Defs sowie mehrdeutige Zuordnungen lassen sich nicht immer
  statisch auflösen. Der Status unterscheidet `resolved`, `ambiguous`, `missing`.
- Die statische Analyse ist auf 1.6 zugeschnitten und bildet keine vollständige
  RimWorld-LoadFolders-/Patch-/Vererbungsengine nach.
- Englisch-Reviews beziehen sich auf die im Report gemeldeten Quelltexte.
  Nicht mehr gemeldete Texte lassen sich anhand dieses Reports nicht auf
  englische Upstream-Änderungen prüfen.
- Ein Report ohne Fehlstelle beweist nicht für sich allein, warum sie fehlt.
  Entfernte Keys und offizielle deutsche Ergänzungen benötigen gegebenenfalls
  eine bewusste Stilllegung der alten Runtime-Fassung.
- Hardcodierte C#-Strings ohne Translation Key werden nicht übersetzt.
- Gleichzeitige schreibende CLI-Aufrufe werden nicht unterstützt.

```bash
python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 -m py_compile scripts/*.py
git diff --check
./rwgt status
./rwgt progress
./rwgt build
./rwgt verify
```

Die Tests verwenden temporäre Verzeichnisse und verändern keine Steam- oder
RimWorld-Dateien. Sie prüfen Config, Merge, Identitäten, Work-Auswahl, Apply,
Placeholder, globalen Build samt Rollback, Verify und Runtime-Nachweise.

## Lizenz

Eigener Code und eigene Übersetzungen stehen unter der [MIT-Lizenz](LICENSE).
RimWorld sowie die übersetzten Mods und deren ursprüngliche Inhalte unterliegen
den Rechten ihrer jeweiligen Urheber.
