"""Source for flightframe/data/airframes.json.

Edit the TYPES table here, then run:

    python3 tools/build_airframes.py

Dimensions are approximate published figures in metres, rounded: plenty for a
silhouette. Keys:

  family      jet | turboprop | light | heli | tandem | fighter | balloon | glider
  like        inherit everything from another type, then override
  length      fuselage length
  diameter    fuselage height (side view)
  fin         fin height above the fuselage top; fin_chord, fin_sweep (degrees)
  span, sweep, wing_chord, wing_x (root leading edge as a fraction of length)
  winglet     none | fence | sharklet | blended | split | raked | a330 | a350 | a380 | small
  nose        airbus | a220 | a350 | a380 | boeing | b737 | b757 | b787 | b747 | embraer | crj | bizjet | dc9 | military
  tail        low | t | cruciform
  eng_mount   wing | rear | none; eng_n, eng_dia, eng_len, eng_x, eng_style (round | flat | chevron)
  hump        [end of upper deck as fraction of length, height] (747)
  decks       2 for the A380
"""
import json
import os
from datetime import date

T = {}


def add(code, name, **kw):
    T[code] = dict(name=name, **kw)


# ------------------------------------------------------------- Airbus narrowbody
add("A320", "Airbus A320", family="jet", length=37.6, diameter=4.1, fin=5.9, fin_chord=6.0, fin_sweep=34,
    span=34.1, sweep=25, wing_chord=6.1, wing_x=0.36, winglet="fence", nose="airbus",
    eng_dia=2.3, eng_len=4.4, eng_x=0.27)
add("A319", "Airbus A319", like="A320", length=33.8)
add("A318", "Airbus A318", like="A320", length=31.4, fin=6.5)
add("A321", "Airbus A321", like="A320", length=44.5, wing_x=0.37)
add("A20N", "Airbus A320neo", like="A320", winglet="sharklet", span=35.8, eng_dia=2.6, eng_len=4.9, eng_x=0.26)
add("A19N", "Airbus A319neo", like="A20N", length=33.8)
add("A21N", "Airbus A321neo", like="A20N", length=44.5, wing_x=0.37)
add("BCS3", "Airbus A220-300", family="jet", length=38.7, diameter=3.7, fin=6.0, fin_chord=5.6, fin_sweep=38,
    span=35.1, sweep=25, wing_chord=5.2, wing_x=0.40, winglet="raked", nose="a220",
    eng_dia=2.3, eng_len=4.6, eng_x=0.31)
add("BCS1", "Airbus A220-100", like="BCS3", length=35.0)
# ------------------------------------------------------------- Airbus widebody
add("A332", "Airbus A330-200", family="jet", length=58.8, diameter=5.6, fin=9.3, fin_chord=9.0, fin_sweep=40,
    span=60.3, sweep=30, wing_chord=10.5, wing_x=0.34, winglet="a330", nose="airbus",
    eng_dia=3.1, eng_len=5.6, eng_x=0.29)
add("A333", "Airbus A330-300", like="A332", length=63.7)
add("A338", "Airbus A330-800neo", like="A332", winglet="sharklet", span=64.0, eng_dia=3.5, eng_len=6.2)
add("A339", "Airbus A330-900neo", like="A338", length=63.7)
add("A342", "Airbus A340-200", like="A332", length=59.4, eng_n=4, eng_dia=2.4, eng_len=4.9)
add("A343", "Airbus A340-300", like="A342", length=63.7)
add("A345", "Airbus A340-500", like="A343", length=67.9, eng_dia=2.9, eng_len=5.4)
add("A346", "Airbus A340-600", like="A345", length=75.4)
add("A359", "Airbus A350-900", family="jet", length=66.8, diameter=6.1, fin=9.6, fin_chord=10.0, fin_sweep=42,
    span=64.8, sweep=32, wing_chord=11.5, wing_x=0.33, winglet="a350", nose="a350",
    eng_dia=3.6, eng_len=6.2, eng_x=0.28)
add("A35K", "Airbus A350-1000", like="A359", length=73.8)
add("A388", "Airbus A380-800", family="jet", length=72.7, diameter=8.4, fin=12.0, fin_chord=15.0, fin_sweep=40,
    span=79.8, sweep=33, wing_chord=16.0, wing_x=0.31, winglet="a380", nose="a380", decks=2,
    eng_n=4, eng_dia=3.6, eng_len=6.6, eng_x=0.27)
add("A306", "Airbus A300-600", family="jet", length=54.1, diameter=5.6, fin=8.6, fin_chord=8.6, fin_sweep=40,
    span=44.8, sweep=28, wing_chord=9.0, wing_x=0.36, winglet="fence", nose="airbus",
    eng_dia=2.9, eng_len=5.2, eng_x=0.30)
add("A310", "Airbus A310", like="A306", length=46.7)
add("A3ST", "Airbus Beluga", like="A306", length=56.2, diameter=7.7, hump=[0.75, 2.6])
# ------------------------------------------------------------- Boeing narrowbody
add("B738", "Boeing 737-800", family="jet", length=39.5, diameter=4.0, fin=7.1, fin_chord=6.4, fin_sweep=35,
    dorsal=3.0, span=35.8, sweep=25, wing_chord=6.0, wing_x=0.38, winglet="blended", nose="b737",
    eng_dia=2.1, eng_len=4.3, eng_x=0.30, eng_style="flat", upsweep=2.6)
add("B737", "Boeing 737-700", like="B738", length=33.6)
add("B736", "Boeing 737-600", like="B738", length=31.2, winglet="none")
add("B739", "Boeing 737-900", like="B738", length=42.1)
add("B734", "Boeing 737-400", like="B738", length=36.4, winglet="none", eng_dia=2.0, eng_len=4.0)
add("B733", "Boeing 737-300", like="B734", length=33.4)
add("B735", "Boeing 737-500", like="B734", length=31.0)
add("B38M", "Boeing 737 MAX 8", like="B738", winglet="split", eng_dia=2.3, eng_len=4.8, eng_x=0.28,
    eng_style="chevron")
add("B37M", "Boeing 737 MAX 7", like="B38M", length=35.6)
add("B39M", "Boeing 737 MAX 9", like="B38M", length=42.2)
add("B3XM", "Boeing 737 MAX 10", like="B38M", length=43.8)
add("P8", "Boeing P-8 Poseidon", like="B738", winglet="raked")
add("B752", "Boeing 757-200", family="jet", length=47.3, diameter=4.0, fin=7.8, fin_chord=7.0, fin_sweep=39,
    span=38.1, sweep=25, wing_chord=7.4, wing_x=0.36, winglet="none", nose="b757",
    eng_dia=2.9, eng_len=5.0, eng_x=0.27)
add("B753", "Boeing 757-300", like="B752", length=54.5)
# ------------------------------------------------------------- Boeing widebody
add("B762", "Boeing 767-200", family="jet", length=48.5, diameter=5.4, fin=8.6, fin_chord=8.0, fin_sweep=40,
    span=47.6, sweep=31, wing_chord=8.6, wing_x=0.36, winglet="none", nose="boeing",
    eng_dia=2.8, eng_len=5.0, eng_x=0.30)
add("B763", "Boeing 767-300", like="B762", length=54.9)
add("B764", "Boeing 767-400", like="B762", length=61.4, winglet="raked")
add("B772", "Boeing 777-200", family="jet", length=63.7, diameter=6.2, fin=10.0, fin_chord=9.5, fin_sweep=40,
    span=60.9, sweep=31, wing_chord=11.0, wing_x=0.33, winglet="none", nose="boeing",
    eng_dia=3.7, eng_len=6.5, eng_x=0.28)
add("B77L", "Boeing 777-200LR", like="B772", winglet="raked", span=64.8, eng_dia=4.0, eng_len=7.0)
add("B773", "Boeing 777-300", like="B772", length=73.9)
add("B77W", "Boeing 777-300ER", like="B77L", length=73.9)
add("B778", "Boeing 777-8", like="B77L", length=70.9, eng_dia=4.4, eng_len=7.3)
add("B779", "Boeing 777-9", like="B778", length=76.7)
add("B788", "Boeing 787-8", family="jet", length=56.7, diameter=5.9, fin=9.6, fin_chord=9.0, fin_sweep=40,
    span=60.1, sweep=32, wing_chord=10.0, wing_x=0.35, winglet="raked", nose="b787",
    eng_dia=3.3, eng_len=5.7, eng_x=0.30, eng_style="chevron")
add("B789", "Boeing 787-9", like="B788", length=62.8)
add("B78X", "Boeing 787-10", like="B788", length=68.3)
add("B744", "Boeing 747-400", family="jet", length=70.7, diameter=6.5, fin=10.5, fin_chord=11.0, fin_sweep=45,
    span=64.4, sweep=37, wing_chord=14.0, wing_x=0.33, winglet="a330", nose="b747", hump=[0.36, 2.2],
    eng_n=4, eng_dia=2.9, eng_len=5.5, eng_x=0.27)
add("B748", "Boeing 747-8", like="B744", length=76.3, hump=[0.40, 2.2], winglet="raked", span=68.4,
    eng_dia=3.3, eng_len=6.3, eng_style="chevron")
add("MD11", "McDonnell Douglas MD-11", like="B772", length=61.6, diameter=6.0, eng_n=2, winglet="fence",
    tail_engine=True)
add("B712", "Boeing 717", family="jet", length=37.8, diameter=3.6, fin=5.3, fin_chord=5.0, fin_sweep=45,
    tail="t", span=28.4, sweep=24, wing_chord=5.5, wing_x=0.42, winglet="none", nose="dc9",
    eng_mount="rear", eng_dia=1.8, eng_len=4.2, eng_x=0.66)
# ------------------------------------------------------------- Embraer, Bombardier, regional jets
add("E190", "Embraer E190", family="jet", length=36.2, diameter=3.4, fin=5.0, fin_chord=5.0, fin_sweep=40,
    span=28.7, sweep=23, wing_chord=5.0, wing_x=0.40, winglet="small", nose="embraer",
    eng_dia=2.0, eng_len=4.0, eng_x=0.32)
add("E195", "Embraer E195", like="E190", length=38.7)
add("E170", "Embraer E170", like="E190", length=29.9)
add("E75L", "Embraer E175", like="E190", length=31.7)
add("E75S", "Embraer E175", like="E75L")
add("E290", "Embraer E190-E2", like="E190", winglet="raked", span=33.7, eng_dia=2.3, eng_len=4.5)
add("E295", "Embraer E195-E2", like="E290", length=41.5)
add("E145", "Embraer ERJ-145", family="jet", length=29.9, diameter=2.3, fin=4.0, fin_chord=4.0, fin_sweep=40,
    tail="t", span=20.0, sweep=22, wing_chord=3.6, wing_x=0.40, winglet="small", nose="bizjet",
    eng_mount="rear", eng_dia=1.3, eng_len=3.2, eng_x=0.63)
add("E135", "Embraer ERJ-135", like="E145", length=26.3)
add("E35L", "Embraer Legacy 600", like="E135", oval_windows=True)
add("CRJ2", "Bombardier CRJ200", family="jet", length=26.8, diameter=2.7, fin=4.2, fin_chord=4.0, fin_sweep=40,
    tail="t", span=21.2, sweep=26, wing_chord=3.6, wing_x=0.42, winglet="small", nose="crj",
    eng_mount="rear", eng_dia=1.4, eng_len=3.3, eng_x=0.62)
add("CRJ7", "Bombardier CRJ700", like="CRJ2", length=32.5, span=23.2)
add("CRJ9", "Bombardier CRJ900", like="CRJ7", length=36.4, span=24.9)
add("CRJX", "Bombardier CRJ1000", like="CRJ9", length=39.1)
add("SU95", "Sukhoi Superjet 100", like="E190", length=29.9, eng_dia=2.2)
add("C919", "COMAC C919", like="A20N", length=38.9)
add("B461", "BAe 146-100", family="jet", length=26.2, diameter=3.6, fin=5.3, fin_chord=5.5, fin_sweep=40,
    tail="t", wing_mount="high", span=26.3, sweep=15, wing_chord=4.5, wing_x=0.40, nose="airbus",
    eng_n=4, eng_dia=1.4, eng_len=3.2, eng_x=0.36)
add("RJ85", "Avro RJ85", like="B461", length=28.6)
# ------------------------------------------------------------- Business jets
add("C68A", "Cessna Citation Latitude", family="jet", length=19.0, diameter=2.3, fin=3.6, fin_chord=3.6,
    fin_sweep=40, tail="t", span=22.0, sweep=16, wing_chord=3.2, wing_x=0.40, winglet="none", nose="bizjet",
    eng_mount="rear", eng_dia=1.2, eng_len=3.2, eng_x=0.68, oval_windows=True, window_pitch=1.3)
add("C700", "Cessna Citation Longitude", like="C68A", length=22.3, winglet="small")
add("C680", "Cessna Citation Sovereign", like="C68A", length=19.4, tail="cruciform")
add("C56X", "Cessna Citation Excel", like="C68A", length=15.8, tail="cruciform", sweep=6)
add("C560", "Cessna Citation V", like="C56X", length=14.9)
add("C25A", "Cessna Citation CJ2", like="C56X", length=14.3, tail="low", sweep=2)
add("C25B", "Cessna Citation CJ3", like="C25A", length=15.6)
add("C25C", "Cessna Citation CJ4", like="C25B", length=16.3, sweep=12)
add("C525", "Cessna CitationJet", like="C25A", length=13.0)
add("C510", "Cessna Citation Mustang", like="C25A", length=12.4)
add("C750", "Cessna Citation X", like="C68A", length=22.0, sweep=37)
add("CL35", "Bombardier Challenger 350", like="C68A", length=20.9, winglet="small", sweep=27)
add("CL30", "Bombardier Challenger 300", like="CL35")
add("CL60", "Bombardier Challenger 650", like="CL35", length=20.9, diameter=2.6)
add("GLEX", "Bombardier Global Express", like="CL35", length=30.3, diameter=2.6, winglet="blended", sweep=35)
add("GL5T", "Bombardier Global 5000", like="GLEX", length=29.5)
add("GL6T", "Bombardier Global 6500", like="GLEX")
add("GL7T", "Bombardier Global 7500", like="GLEX", length=33.8, winglet="small")
add("GLF4", "Gulfstream IV", like="C68A", length=26.9, diameter=2.4, winglet="blended", sweep=27,
    window_pitch=1.6)
add("GLF5", "Gulfstream V", like="GLF4", length=29.4)
add("GLF6", "Gulfstream G650", like="GLF4", length=30.4, diameter=2.6, winglet="small", sweep=36)
add("GA6C", "Gulfstream G600", like="GLF6", length=29.4)
add("GA7C", "Gulfstream G700", like="GLF6", length=33.5)
add("G280", "Gulfstream G280", like="C68A", length=20.4, winglet="small", sweep=27)
add("FA7X", "Dassault Falcon 7X", like="C68A", length=23.2, tail="low", tail_engine=True, sweep=34)
add("FA8X", "Dassault Falcon 8X", like="FA7X", length=24.5)
add("F900", "Dassault Falcon 900", like="FA7X", length=20.2, winglet="blended")
add("FA50", "Dassault Falcon 50", like="F900", length=18.5, winglet="none")
add("F2TH", "Dassault Falcon 2000", like="F900", tail_engine=False)
add("FA6X", "Dassault Falcon 6X", like="F2TH", length=25.7, diameter=2.7)
add("LJ45", "Learjet 45", like="C68A", length=17.7, sweep=13, winglet="small")
add("LJ75", "Learjet 75", like="LJ45")
add("LJ35", "Learjet 35", like="LJ45", length=14.8, diameter=1.9)
add("PC24", "Pilatus PC-24", like="C68A", length=16.9, sweep=4)
add("E55P", "Embraer Phenom 300", like="C68A", length=15.9, sweep=27, winglet="small")
add("E50P", "Embraer Phenom 100", like="E55P", length=12.8)
add("E545", "Embraer Praetor 500", like="C68A", length=19.7, winglet="small", sweep=27)
add("E550", "Embraer Praetor 600", like="E545", length=20.7)
add("H25B", "Hawker 800", like="C68A", length=15.6, tail="cruciform", sweep=20)
add("HDJT", "HondaJet", like="E50P", length=13.0)
# ------------------------------------------------------------- Turboprops
add("AT76", "ATR 72-600", family="turboprop", length=27.2, diameter=2.6, fin=3.9, fin_chord=4.4, fin_sweep=34,
    dorsal_frac=0.5, tail="t", wing="high", wing_x=0.38, wing_chord=2.3, nacelle_len=4.6, nacelle_dia=1.2,
    eng_x=0.33, prop=3.9)
add("AT75", "ATR 72-500", like="AT76")
add("AT72", "ATR 72", like="AT76")
add("AT45", "ATR 42-500", like="AT76", length=22.7)
add("AT43", "ATR 42-300", like="AT45")
add("AT46", "ATR 42-600", like="AT45")
add("DH8D", "De Havilland Dash 8-400", family="turboprop", length=32.8, diameter=2.7, fin=5.4, fin_chord=4.8,
    fin_sweep=36, tail="t", wing="high", wing_x=0.37, wing_chord=2.6, nacelle_len=7.0, nacelle_dia=1.5,
    eng_x=0.32, prop=4.1)
add("DH8C", "De Havilland Dash 8-300", like="DH8D", length=25.7, prop=3.7, nacelle_len=6.0)
add("DH8A", "De Havilland Dash 8-100", like="DH8C", length=22.3)
add("DH8B", "De Havilland Dash 8-200", like="DH8A")
add("SF34", "Saab 340", family="turboprop", length=19.7, diameter=2.3, fin=3.4, fin_chord=3.6, fin_sweep=35,
    tail="low", wing="low", wing_x=0.40, wing_chord=2.4, nacelle_len=4.0, nacelle_dia=1.0, eng_x=0.35, prop=3.4)
add("SB20", "Saab 2000", like="SF34", length=27.3, prop=3.8)
add("JS41", "BAe Jetstream 41", like="SF34", length=19.3, tail="cruciform")
add("JS32", "BAe Jetstream 32", like="JS41", length=14.4, diameter=1.9, prop=2.7)
add("D328", "Dornier 328", like="AT45", length=21.3, prop=3.6)
add("BE20", "Beechcraft King Air 200", family="turboprop", length=13.3, diameter=1.8, fin=2.6, fin_chord=2.6,
    fin_sweep=40, tail="t", wing="low", wing_x=0.38, wing_chord=2.0, nacelle_len=3.6, nacelle_dia=0.9,
    eng_x=0.30, prop=2.5)
add("B350", "Beechcraft King Air 350", like="BE20", length=14.2)
add("BE9L", "Beechcraft King Air 90", like="BE20", length=10.8)
add("PC12", "Pilatus PC-12", family="turboprop", length=14.4, diameter=1.8, fin=2.6, fin_chord=2.6,
    fin_sweep=40, tail="t", wing="low", wing_x=0.38, wing_chord=2.0, nose_len=2.0, eng_n=1,
    nacelle_len=0.1, nacelle_dia=0.1, eng_x=0.0, prop=2.7)
add("DHC6", "De Havilland Twin Otter", family="turboprop", length=15.8, diameter=1.9, fin=3.0, fin_chord=2.8,
    fin_sweep=10, tail="low", wing="high", wing_x=0.34, wing_chord=2.0, nacelle_len=3.0, nacelle_dia=0.8,
    eng_x=0.30, prop=2.6)
add("BN2P", "Britten-Norman Islander", like="DHC6", length=10.9, diameter=1.5, prop=2.0, fin=2.0, fin_chord=2.2)
add("C130", "Lockheed C-130 Hercules", family="turboprop", length=29.8, diameter=4.3, fin=7.0, fin_chord=6.0,
    fin_sweep=30, tail="low", wing="high", wing_x=0.37, wing_chord=4.2, nacelle_len=5.5, nacelle_dia=1.4,
    eng_x=0.32, prop=4.1, eng_n=4, ramp=True, upsweep=2.6, windows=False)
add("C30J", "Lockheed C-130J Hercules", like="C130", length=34.4)
add("A400", "Airbus A400M Atlas", like="C130", length=45.1, diameter=5.6, fin=9.5, fin_chord=8.0, tail="t",
    prop=5.3, nacelle_len=6.5, nacelle_dia=1.6)
add("C295", "Airbus C295", like="AT45", length=24.5, ramp=True, tail="low", windows=False)
# ------------------------------------------------------------- Military jets
add("C17", "Boeing C-17 Globemaster", family="jet", length=53.0, diameter=6.9, fin=9.5, fin_chord=9.0,
    fin_sweep=38, tail="t", wing_mount="high", span=51.8, sweep=25, wing_chord=10.0, wing_x=0.33,
    winglet="small", nose="military", eng_n=4, eng_dia=2.6, eng_len=5.5, eng_x=0.28, upsweep=2.8,
    oval_windows=True, window_pitch=30)
add("K35R", "Boeing KC-135 Stratotanker", family="jet", length=41.5, diameter=3.9, fin=8.5, fin_chord=7.0,
    fin_sweep=35, span=39.9, sweep=35, wing_chord=7.0, wing_x=0.36, nose="boeing", eng_n=4, eng_dia=2.0,
    eng_len=4.2, eng_x=0.30)
add("E3TF", "Boeing E-3 Sentry", like="K35R", length=46.6, rotodome=0.62)
add("E3CF", "Boeing E-3 Sentry", like="E3TF")
add("E737", "Boeing E-7 Wedgetail", like="B737", winglet="blended", rotodome=0.58)
add("EUFI", "Eurofighter Typhoon", family="fighter", length=16.0, shape="delta")
add("F35", "Lockheed Martin F-35", family="fighter", length=15.7, shape="stealth")
add("HAWK", "BAE Hawk", family="fighter", length=11.9, shape="trainer")
add("TEX2", "Beechcraft Texan II", family="light", length=10.2, diameter=1.6, fin=1.8, fin_chord=1.8,
    wing="low", wing_x=0.40, wing_chord=2.0)
# ------------------------------------------------------------- Helicopters
# length = fuselage nose to tail; cabin_len = fraction of length that is cabin; cabin_h = cabin height
add("EC35", "Airbus H135", family="heli", length=10.2, cabin_len=0.42, cabin_h=1.75, nose="standard",
    cowl_h=0.55, boom_h=0.75, fin=1.5, rotor=10.2, tail_rotor="fenestron", tail_rotor_dia=1.0,
    gear="skids", windows=1)
add("EC45", "Airbus H145", like="EC35", length=11.6, cabin_len=0.46, cabin_h=1.95, rotor=11.0, windows=2,
    tail_rotor_dia=1.2)
add("EC30", "Airbus H130", like="EC35", length=10.7, cabin_len=0.44, cabin_h=1.9, nose="bubble", rotor=10.7)
add("H160", "Airbus H160", like="EC45", length=12.6, nose="pointed", gear="wheels", rotor=13.4, windows=2)
add("AS65", "Airbus AS365 Dauphin", like="H160", length=11.6, rotor=11.9, cabin_h=1.8)
add("EC55", "Airbus H155", like="AS65", length=12.7, rotor=12.6)
add("AS50", "Airbus AS350 Squirrel", family="heli", length=10.9, cabin_len=0.40, cabin_h=1.8, nose="bubble",
    cowl_h=0.6, boom_h=0.7, fin=1.6, rotor=10.7, tail_rotor="rotor", tail_rotor_dia=1.9, gear="skids", windows=1)
add("AS55", "Airbus AS355 Twin Squirrel", like="AS50")
add("H125", "Airbus H125", like="AS50")
add("EC75", "Airbus H175", family="heli", length=15.7, cabin_len=0.52, cabin_h=2.3, nose="blunt", cowl_h=0.8,
    boom_h=1.0, fin=2.4, rotor=14.8, tail_rotor="rotor", tail_rotor_dia=3.0, gear="sponsons", windows=3)
add("A109", "Leonardo AW109", family="heli", length=11.4, cabin_len=0.46, cabin_h=1.6, nose="pointed",
    cowl_h=0.55, boom_h=0.7, fin=1.7, rotor=11.0, tail_rotor="rotor", tail_rotor_dia=2.0, gear="wheels",
    windows=2)
add("A119", "Leonardo AW119 Koala", like="A109", gear="skids", skid_h=0.5)
add("A169", "Leonardo AW169", like="A109", length=12.8, cabin_len=0.48, cabin_h=1.9, nose="standard",
    rotor=12.1, gear="sponsons", windows=2)
add("A139", "Leonardo AW139", family="heli", length=13.8, cabin_len=0.50, cabin_h=2.1, nose="blunt",
    cowl_h=0.75, boom_h=0.95, fin=2.2, rotor=13.8, tail_rotor="rotor", tail_rotor_dia=2.7, gear="sponsons",
    windows=3)
add("A189", "Leonardo AW189", like="A139", length=14.6, rotor=14.6)
add("S92", "Sikorsky S-92", like="A139", length=17.1, cabin_len=0.54, cabin_h=2.4, rotor=17.2,
    tail_rotor_dia=3.4)
add("S76", "Sikorsky S-76", like="A109", length=13.2, rotor=13.4, cabin_h=1.8)
add("EH10", "Leonardo AW101 Merlin", like="S92", length=19.5, cabin_h=2.6, rotor=18.6, cowl_h=1.0, windows=4)
add("NH90", "NH90", like="A139", length=16.1, cabin_h=2.4, rotor=16.3)
add("LYNX", "Westland Lynx", family="heli", length=12.1, cabin_len=0.44, cabin_h=1.9, nose="blunt",
    cowl_h=0.6, boom_h=0.8, fin=1.9, rotor=12.8, tail_rotor="rotor", tail_rotor_dia=2.2, gear="wheels",
    windows=1)
add("B06", "Bell 206 JetRanger", family="heli", length=9.5, cabin_len=0.40, cabin_h=1.6, nose="bubble",
    cowl_h=0.5, boom_h=0.55, fin=1.4, rotor=10.2, tail_rotor="rotor", tail_rotor_dia=1.65, gear="skids",
    windows=1)
add("B407", "Bell 407", like="B06", length=10.6, rotor=10.7, windows=2)
add("B429", "Bell 429", like="A169", length=11.6, rotor=11.0, gear="skids")
add("R44", "Robinson R44", family="heli", length=8.9, cabin_len=0.34, cabin_h=1.5, nose="bubble", cowl_h=0.3,
    boom_h=0.35, fin=1.2, rotor=10.1, tail_rotor="rotor", tail_rotor_dia=1.5, gear="skids", windows=0,
    mast_h=0.9, skid_h=0.45)
add("R22", "Robinson R22", like="R44", length=6.3, cabin_h=1.35, rotor=7.7, tail_rotor_dia=1.1)
add("R66", "Robinson R66", like="R44", length=9.1, cabin_len=0.38, rotor=10.1)
add("H47", "Boeing Chinook", family="tandem", length=15.9)
# ------------------------------------------------------------- Light aircraft
add("C172", "Cessna 172 Skyhawk", family="light", length=8.3, diameter=1.5, fin=1.5, fin_chord=1.4,
    wing="high", wing_x=0.28, wing_chord=1.5)
add("C152", "Cessna 152", like="C172", length=7.3, diameter=1.4)
add("C150", "Cessna 150", like="C152")
add("C182", "Cessna 182 Skylane", like="C172", length=8.8)
add("C206", "Cessna 206", like="C182", length=8.6)
add("C208", "Cessna Caravan", like="C182", length=11.5, diameter=1.8)
add("PA18", "Piper Super Cub", like="C172", length=6.9, diameter=1.2)
add("P28A", "Piper PA-28 Cherokee", family="light", length=7.3, diameter=1.5, fin=1.4, fin_chord=1.3,
    wing="low", wing_x=0.28, wing_chord=1.6)
add("P28R", "Piper PA-28R Arrow", like="P28A")
add("P28B", "Piper PA-28 Dakota", like="P28A")
add("PA32", "Piper PA-32", like="P28A", length=8.4)
add("P46T", "Piper Malibu Meridian", like="P28A", length=8.8)
add("SR22", "Cirrus SR22", like="P28A", length=7.9)
add("SR20", "Cirrus SR20", like="SR22")
add("DA40", "Diamond DA40", like="P28A", length=8.0, tail="t")
add("DA20", "Diamond DA20", like="DA40", length=7.2)
add("G115", "Grob Tutor", like="P28A", length=7.6)
add("DR40", "Robin DR400", like="P28A", length=7.0)
add("TB20", "Socata TB-20", like="P28A", length=7.7)
add("BE36", "Beechcraft Bonanza", like="P28A", length=8.4)
add("M20P", "Mooney M20", like="P28A", length=7.5)
add("PA34", "Piper Seneca", like="P28A", length=8.7, eng_n=2)
add("PA44", "Piper Seminole", like="PA34", tail="t")
add("BE58", "Beechcraft Baron", like="PA34", length=9.1)
add("DA42", "Diamond DA42", like="DA40", length=8.6, eng_n=2)
add("DA62", "Diamond DA62", like="DA42", length=9.2)
add("P68", "Vulcanair P68", like="C172", length=9.4, eng_n=2, strut=False)
add("EXTR", "Extra 300", like="P28A", length=7.1)
add("GLID", "Glider", family="glider", length=7.0)
add("BALL", "Hot air balloon", family="balloon", length=20.0)

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "flightframe", "data", "airframes.json")
    data = {"version": 2, "updated": date.today().isoformat(),
            "about": "Aircraft drawings for flightframe: approximate dimensions in metres. Edit tools/build_airframes.py.",
            "types": T}
    with open(out, "w") as f:
        json.dump(data, f, indent=1, sort_keys=False)
        f.write("\n")
    print(f"wrote {len(T)} types to {os.path.normpath(out)}")
