# Slotfinity – Fusion add-in

Een Fusion-add-in die **WaveGrid-compatibele** trays (goten), gesloten bakken en
dividers maakt op het Gridfinity-raster (42 × 42 × 7 mm). Je kiest de maat in
rastereenheden of in millimeters en de add-in bouwt het model in een nieuw
component, met alle stappen in de tijdlijn.

## Installeren

1. Download deze repository (groene knop **Code → Download ZIP**) en pak hem uit.
2. Start Fusion en open **Utilities → Add-Ins → Scripts and Add-Ins** (sneltoets `Shift+S`).
3. Klik op het tabblad **Add-Ins** op het **+**-icoon (*My Add-Ins*) en kies de map
   `Slotfinity` (de map met `Slotfinity.py` erin).
4. Selecteer **Slotfinity** en klik op **Run**. Vink **Run on Startup** aan als je hem
   altijd beschikbaar wilt hebben.

De knop **Slotfinity tray** staat daarna in de Design-werkruimte onder
**Solid → Create**.

## Gebruik

| Instelling | Uitleg |
|---|---|
| Onderdeel | *Open tray (goot)*, *Gesloten bak* (met voor- en achterwand) of *Divider*. |
| Maatvoering | *Rastereenheden*: breedte en lengte in eenheden van 42 mm (stappen van ½), hoogte in eenheden van 7 mm. *Millimeters*: exacte buitenmaat, bijvoorbeeld om een lade precies te vullen. |
| Aantal goten naast elkaar | Verdeelt de breedte in meerdere goten. Is het aantal goten gelijk aan de breedte in eenheden (bijv. 3 goten in een tray van 3 breed), dan komen de tussenwanden precies op het 42 mm-raster en is elke goot even breed als een 1U-tray. Met *Stapelrand* krijgt elke tussenwand dan bovenop het stapelprofiel aan twee kanten, zodat losse bakjes van elke rastermaat (bijv. 1×1) erop staan: zijwaarts vast, in de lengte schuifbaar. Bij een ander aantal (bijv. 3 goten in 2 eenheden) worden de goten gelijk verdeeld en zit de stapelrand alleen op de buitenwanden. |
| Gootradius | Radius tussen wand en bodem (standaard 14 mm). Wordt automatisch kleiner als de goot te smal of te laag is. |
| Onderkant | *Gridfinity-voetjes* (past op een Gridfinity-baseplate) of *Vlak*. |
| Dividersleuven | Sleuven in de wanden om de 21 mm (½ eenheid). |
| Klikgaten in de bodem | Gat onder elke sleuf waar de klikpootjes van een divider in vallen. |
| Stapelrand | Gridfinity-stapelrand van 4,4 mm op de buitenwanden, zodat je een tray op een andere kunt zetten. Bij een open tray alleen langs de lange zijden, bij een bak rondom. De rand komt bovenop de gekozen hoogte. De dividersleuven lopen door de rand heen. |
| Dikte eindwanden | Alleen voor een gesloten bak. |
| Divider → Label | *Geen*, *Plat label* (14 mm diep) of *Schuin label (45°)*. Het schuine label is massief: onder het labelvlak loopt een schuine onderkant van 45° terug naar de divider, zodat hij zonder support rechtop te printen is. |
| Divider → Labeltekst | Tekst op het label, te lezen vanaf de kant waar het label naartoe wijst. Op het platte label wordt hij erin gegraveerd, op het schuine label staat hij in reliëf. Te lange tekst wordt automatisch kleiner gemaakt zodat hij past. |
| Divider → Teksthoogte / Tekstdiepte | Lettergrootte (standaard 5 mm) en hoe diep de letters erin gaan (plat label, max. 1,4 mm) of hoe ver ze uitsteken (schuin label); standaard 0,6 mm. |
| Divider → Klikpootjes | Pootjes met weerhaakjes die in de klikgaten klikken. |
| Divider → Speling per kant | Ruimte tussen divider en sleuf (standaard 0,2 mm). Zit hij te strak of te los, pas dit aan. |
| Geavanceerd | Wanddikte (2,4 mm) en sleufafstand (21 mm). |

Een divider maak je met dezelfde breedte, hoogte, gootradius en het aantal goten
als de tray waar hij in moet. Bij meerdere goten past de divider in één goot.

In millimeter-modus begint het voetjesraster aan de voorkant/linkerkant van de
tray. Een restant van minstens 21 mm krijgt een half voetje; een kleiner restant
krijgt geen voetje.

## Maten

De maten zijn opgemeten uit de WaveGrid *Classic Trays starter pack*:

- Tray 1U = 41,5 mm breed (42 − 0,5), lengte n × 42 − 0,5 mm, hoogte n × 7 mm.
- Gridfinity-voetjes per vak: 0,8 + 1,8 + 2,15 mm (totaal 4,75 mm), bovenaan
  41,5 mm met radius 3,75 mm.
- Wanden 2,4 mm, bodem bovenkant op 5,8 mm, gootradius 14 mm.
- Sleuven 2,2 mm breed, 1,4 mm diep, om de 21 mm (eerste op 10,25 mm van de rand).
- Klikgat 6 × 3,3 mm met een lip van 5 × 2,3 mm.
- Stapelrand 4,4 mm hoog: 45° van 2,4 naar 1,9 mm, recht tot 2,9 mm, dan 45° naar een
  vlakje van 0,4 mm. Een gestapelde tray rust op die bovenste schuine kant.
- Divider 2 mm dik, 0,2 mm speling per kant, klikpootjes 4,6 mm lang.

Het nagebouwde model wijkt minder dan 0,1 % in volume af van het origineel.

## Ontwikkeling

De geometrie staat los van Fusion in `Slotfinity/lib/geometry.py` en is te testen
zonder Fusion:

```
pip install pytest
python -m pytest
```

`tests/test_fusion_smoke.py` draait de Fusion-code tegen een nagebootste API, zodat
programmeerfouten vroeg opvallen. Of het model in Fusion goed wordt opgebouwd,
moet je in Fusion zelf controleren.

Structuur:

```
Slotfinity/
  Slotfinity.py         start/stop van de add-in
  Slotfinity.manifest
  lib/command.py        dialoog en invoer
  lib/fusion_build.py   bouwt het model met schetsen en features
  lib/geometry.py       alle maten en contouren (in mm)
  resources/            pictogrammen
tests/
```
