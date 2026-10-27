
import csv
import sys
import json
import os
import shutil
import unicodedata
from datetime import datetime


# ==================================================
# BARVY
# ==================================================

FIALOVA = "\033[95m"
MODRA = "\033[94m"
TYRKYSOVA = "\033[96m"
ZELENA = "\033[92m"
ZLUTA = "\033[93m"
CERVENA = "\033[91m"
RESET = "\033[0m"
TUCNE = "\033[1m"


# ==================================================
# POMOCNÉ FUNKCE
# ==================================================

def normalizuj(text):
    """Odstraní diakritiku a převede text na malá písmena."""
    text = str(text or "").strip().lower()
    text = unicodedata.normalize("NFD", text)

    return "".join(
        znak for znak in text
        if unicodedata.category(znak) != "Mn"
    )


def najdi_sloupec(sloupce, moznosti):
    """Najde sloupec podle názvu nebo jeho části."""
    normalizovane = {
        normalizuj(sloupec): sloupec
        for sloupec in sloupce
        if sloupec
    }

    for moznost in moznosti:
        klic = normalizuj(moznost)

        if klic in normalizovane:
            return normalizovane[klic]

    for puvodni in sloupce:
        klic = normalizuj(puvodni)

        for moznost in moznosti:
            hledany = normalizuj(moznost)

            if hledany in klic:
                return puvodni

    return None


def preved_cas(hodnota):
    """Převede datum a čas z CSV na objekt datetime."""
    if not hodnota:
        return None

    hodnota = hodnota.strip()

    formaty = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ]

    for format_casu in formaty:
        try:
            return datetime.strptime(hodnota, format_casu)
        except ValueError:
            pass

    return None


# ==================================================
# NAČTENÍ CSV
# ==================================================

def nacti_data(cesta):
    """Načte CSV a sjednotí názvy důležitých sloupců."""

    if not os.path.isfile(cesta):
        raise FileNotFoundError(
            f"Soubor '{cesta}' nebyl nalezen."
        )

    posledni_chyba = None

    for kodovani in ("utf-8-sig", "cp1250", "utf-8"):
        try:
            with open(
                cesta,
                "r",
                encoding=kodovani,
                newline=""
            ) as soubor:

                vzorek = soubor.read(8192)
                soubor.seek(0)

                try:
                    oddelovac = csv.Sniffer().sniff(
                        vzorek,
                        delimiters=";,\t"
                    ).delimiter
                except csv.Error:
                    oddelovac = ";"

                ctecka = csv.DictReader(
                    soubor,
                    delimiter=oddelovac
                )

                if not ctecka.fieldnames:
                    raise ValueError(
                        "CSV soubor neobsahuje hlavičku."
                    )

                sloupce = [
                    s.strip() if s else s
                    for s in ctecka.fieldnames
                ]
                ctecka.fieldnames = sloupce

                sloupec_cipu = najdi_sloupec(
                    sloupce,
                    [
                        "číslo čipu",
                        "cislo cipu",
                        "čip",
                        "cip",
                        "číslo",
                        "id zaměstnance",
                    ]
                )

                sloupec_jmena = najdi_sloupec(
                    sloupce,
                    [
                        "zaměstnanec",
                        "jméno zaměstnance",
                        "jméno",
                        "jmeno",
                        "employee",
                        "name",
                    ]
                )

                sloupec_prichodu = najdi_sloupec(
                    sloupce,
                    [
                        "příchod",
                        "čas příchodu",
                        "cas prichodu",
                        "arrival",
                        "check in",
                    ]
                )

                sloupec_odchodu = najdi_sloupec(
                    sloupce,
                    [
                        "odchod",
                        "čas odchodu",
                        "cas odchodu",
                        "departure",
                        "check out",
                    ]
                )

                nalezene = {
                    "číslo čipu": sloupec_cipu,
                    "zaměstnanec": sloupec_jmena,
                    "příchod": sloupec_prichodu,
                    "odchod": sloupec_odchodu,
                }

                chybejici = [
                    nazev
                    for nazev, sloupec in nalezene.items()
                    if sloupec is None
                ]

                if chybejici:
                    raise ValueError(
                        "V CSV chybí potřebné sloupce: "
                        + ", ".join(chybejici)
                        + ". Nalezené sloupce: "
                        + ", ".join(sloupce)
                    )

                data = []

                for radek in ctecka:
                    data.append({
                        "číslo čipu": str(
                            radek.get(sloupec_cipu, "") or ""
                        ).strip(),

                        "zaměstnanec": str(
                            radek.get(sloupec_jmena, "") or ""
                        ).strip(),

                        "příchod": preved_cas(
                            radek.get(sloupec_prichodu, "")
                        ),

                        "odchod": preved_cas(
                            radek.get(sloupec_odchodu, "")
                        ),
                    })

                return data

        except UnicodeDecodeError as chyba:
            posledni_chyba = chyba

    raise ValueError(
        f"Soubor se nepodařilo dekódovat: {posledni_chyba}"
    )


# ==================================================
# VÝPOČET STATISTIK
# ==================================================

def vypocitej_statistiky(data):
    """Spočítá počet dnů, celkový čas a průměrnou směnu."""

    zamestnanci = {}

    for radek in data:
        cip = radek["číslo čipu"]
        jmeno = radek["zaměstnanec"]
        prichod = radek["příchod"]
        odchod = radek["odchod"]

        if not cip:
            continue

        if cip not in zamestnanci:
            zamestnanci[cip] = {
                "číslo čipu": cip,
                "zaměstnanec": jmeno,
                "dny": set(),
                "celkem_minut": 0.0,
            }

        if jmeno:
            zamestnanci[cip]["zaměstnanec"] = jmeno

        if prichod is None or odchod is None:
            continue

        delka_minut = (
            odchod - prichod
        ).total_seconds() / 60

        if delka_minut < 0:
            continue

        zamestnanci[cip]["celkem_minut"] += delka_minut
        zamestnanci[cip]["dny"].add(prichod.date())

    vysledky = []

    for zam in zamestnanci.values():
        pocet_dni = len(zam["dny"])

        celkem_hodin = round(
            zam["celkem_minut"] / 60,
            2
        )

        prumerna_smena = (
            round(celkem_hodin / pocet_dni, 2)
            if pocet_dni
            else 0.0
        )

        vysledky.append({
            "číslo čipu": zam["číslo čipu"],
            "zaměstnanec": zam["zaměstnanec"],
            "počet_dní": pocet_dni,
            "celkem_hodin": celkem_hodin,
            "průměrná_směna": prumerna_smena,
        })

    return vysledky


# ==================================================
# ULOŽENÍ JSON
# ==================================================

def uloz_json(statistiky, cesta):
    with open(cesta, "w", encoding="utf-8") as soubor:
        json.dump(
            statistiky,
            soubor,
            ensure_ascii=False,
            indent=4,
        )


# ==================================================
# VÝPIS TABULKY DOCHÁZKY
# ==================================================

def vypis_tabulku(data):
    if not data:
        print(f"{ZLUTA}Žádná data k zobrazení.{RESET}")
        return

    hlavicky = [
        "Číslo čipu",
        "Zaměstnanec",
        "Příchod",
        "Odchod",
        "Délka (h)",
    ]

    radky = []

    for radek in data:
        prichod = radek["příchod"]
        odchod = radek["odchod"]

        if prichod and odchod and odchod >= prichod:
            delka = round(
                (odchod - prichod).total_seconds() / 3600,
                2
            )
            delka_text = f"{delka:.2f}"
        else:
            delka_text = "-"

        radky.append([
            radek["číslo čipu"],
            radek["zaměstnanec"],
            prichod.strftime("%d.%m.%Y %H:%M")
            if prichod else "-",
            odchod.strftime("%d.%m.%Y %H:%M")
            if odchod else "-",
            delka_text,
        ])

    sirky = [
        max(
            len(hlavicky[i]),
            *(len(radek[i]) for radek in radky)
        )
        for i in range(len(hlavicky))
    ]

    oddelovac = "+" + "+".join(
        "-" * (sirka + 2)
        for sirka in sirky
    ) + "+"

    print(f"\n{FIALOVA}{TUCNE}{oddelovac}{RESET}")

    print(
        f"{FIALOVA}{TUCNE}| "
        + " | ".join(
            hlavicky[i].ljust(sirky[i])
            for i in range(len(hlavicky))
        )
        + " |"
        + RESET
    )

    print(f"{FIALOVA}{TUCNE}{oddelovac}{RESET}")

    for i, radek in enumerate(radky):
        barva = MODRA if i % 2 == 0 else TYRKYSOVA

        print(
            f"{barva}| "
            + " | ".join(
                radek[j].ljust(sirky[j])
                for j in range(len(hlavicky))
            )
            + " |"
            + RESET
        )

    print(f"{FIALOVA}{TUCNE}{oddelovac}{RESET}")


# ==================================================
# ZAROVNANÉ STATISTIKY
# ==================================================

def vypis_statistiky(statistiky):
    if not statistiky:
        print(f"{ZLUTA}Žádné statistiky k zobrazení.{RESET}")
        return

    hlavicky = [
        "Číslo čipu",
        "Zaměstnanec",
        "Počet dnů",
        "Celkem hodin",
        "Průměrná směna",
    ]

    serazene = sorted(
        statistiky,
        key=lambda zam: zam["zaměstnanec"].casefold()
    )

    radky = []

    for zam in serazene:
        radky.append([
            str(zam["číslo čipu"]),
            str(zam["zaměstnanec"]),
            str(zam["počet_dní"]),
            f'{zam["celkem_hodin"]:.2f}',
            f'{zam["průměrná_směna"]:.2f}',
        ])

    sirky = [
        max(
            len(hlavicky[i]),
            *(len(radek[i]) for radek in radky)
        )
        for i in range(len(hlavicky))
    ]

    oddelovac = "+" + "+".join(
        "-" * (sirka + 2)
        for sirka in sirky
    ) + "+"

    print(f"\n{FIALOVA}{TUCNE}STATISTIKY ZAMĚSTNANCŮ{RESET}")
    print(f"{FIALOVA}{oddelovac}{RESET}")

    print(
        f"{FIALOVA}{TUCNE}| "
        + " | ".join(
            hlavicky[i].ljust(sirky[i])
            for i in range(len(hlavicky))
        )
        + " |"
        + RESET
    )

    print(f"{FIALOVA}{oddelovac}{RESET}")

    for i, radek in enumerate(radky):
        barva = MODRA if i % 2 == 0 else TYRKYSOVA

        zarovnane = [
            radek[0].ljust(sirky[0]),
            radek[1].ljust(sirky[1]),
            radek[2].rjust(sirky[2]),
            radek[3].rjust(sirky[3]),
            radek[4].rjust(sirky[4]),
        ]

        print(
            f"{barva}| "
            + " | ".join(zarovnane)
            + " |"
            + RESET
        )

    print(f"{FIALOVA}{oddelovac}{RESET}")


# ==================================================
# GRAF CELKOVÝCH HODIN
# ==================================================

def vykresli_graf(statistiky):
    if not statistiky:
        print(f"{ZLUTA}Žádná data pro graf.{RESET}")
        return

    serazene = sorted(
        statistiky,
        key=lambda zam: zam["celkem_hodin"],
        reverse=True
    )

    sirka_terminalu = shutil.get_terminal_size(
        fallback=(100, 20)
    ).columns

    sirka_jmena = min(
        max(len(zam["zaměstnanec"]) for zam in serazene),
        22
    )

    sirka_grafu = max(
        10,
        min(40, sirka_terminalu - sirka_jmena - 18)
    )

    maximum = max(
        zam["celkem_hodin"]
        for zam in serazene
    )

    print(
        f"\n{FIALOVA}{TUCNE}"
        "GRAF CELKOVÝCH ODPRACOVANÝCH HODIN"
        f"{RESET}"
    )

    for zam in serazene:
        jmeno = zam["zaměstnanec"][:sirka_jmena]
        hodiny = zam["celkem_hodin"]

        delka = (
            round(hodiny / maximum * sirka_grafu)
            if maximum > 0
            else 0
        )

        sloupec = "█" * delka

        print(
            f"{MODRA}{jmeno:<{sirka_jmena}}{RESET} "
            f"{TYRKYSOVA}{sloupec:<{sirka_grafu}}{RESET} "
            f"{ZELENA}{hodiny:>7.2f} h{RESET}"
        )


# ==================================================
# MENU
# ==================================================

def menu(data, statistiky, json_soubor):
    while True:
        print(f"\n{FIALOVA}{TUCNE}===== MENU DOCHÁZKY ====={RESET}")
        print("1. Zobrazit docházku")
        print("2. Seřadit docházku podle jména")
        print("3. Seřadit docházku podle čísla čipu")
        print("4. Seřadit docházku podle délky směny")
        print("5. Seřadit statistiky podle celkových hodin")
        print("6. Zobrazit statistiky")
        print("7. Uložit statistiky do JSON")
        print("8. Zobrazit graf odpracovaných hodin")
        print("0. Konec")

        volba = input("Vyber možnost: ").strip()

        if volba == "1":
            vypis_tabulku(data)

        elif volba == "2":
            vypis_tabulku(sorted(
                data,
                key=lambda r: r["zaměstnanec"].casefold()
            ))

        elif volba == "3":
            vypis_tabulku(sorted(
                data,
                key=lambda r: r["číslo čipu"]
            ))

        elif volba == "4":
            vypis_tabulku(sorted(
                data,
                key=lambda r: (
                    (r["odchod"] - r["příchod"]).total_seconds()
                    if r["příchod"] and r["odchod"]
                    and r["odchod"] >= r["příchod"]
                    else -1
                ),
                reverse=True
            ))

        elif volba == "5":
            vypis_statistiky(sorted(
                statistiky,
                key=lambda zam: zam["celkem_hodin"],
                reverse=True
            ))

        elif volba == "6":
            vypis_statistiky(statistiky)

        elif volba == "7":
            uloz_json(statistiky, json_soubor)
            print(
                f"{ZELENA}Statistiky uloženy do "
                f"{json_soubor}.{RESET}"
            )

        elif volba == "8":
            vykresli_graf(statistiky)

        elif volba == "0":
            print(f"{FIALOVA}Program ukončen.{RESET}")
            break

        else:
            print(f"{CERVENA}Neplatná volba. Zkus to znovu.{RESET}")


# ==================================================
# HLAVNÍ PROGRAM
# ==================================================

def main():
    # CSV lze zadat jako argument:
    # python main.py "dochazka.csv"
    if len(sys.argv) >= 2:
        csv_soubor = sys.argv[1]
    else:
        csv_soubor = "dochazka.csv"

    # JSON dostane stejné jméno jako vstupní CSV.
    zaklad = os.path.splitext(
        os.path.basename(csv_soubor)
    )[0]

    json_soubor = f"{zaklad}.json"

    try:
        data = nacti_data(csv_soubor)
    except (FileNotFoundError, ValueError, OSError, csv.Error) as chyba:
        print(f"{CERVENA}Chyba: {chyba}{RESET}")
        sys.exit(1)

    statistiky = vypocitej_statistiky(data)

    try:
        uloz_json(statistiky, json_soubor)
    except OSError as chyba:
        print(f"{CERVENA}Chyba při ukládání JSON: {chyba}{RESET}")
        sys.exit(1)

    print(f"{ZELENA}Načten soubor: {csv_soubor}{RESET}")
    print(f"{ZELENA}JSON uložen do: {json_soubor}{RESET}")
    print(f"Počet načtených záznamů: {len(data)}")

    menu(data, statistiky, json_soubor)


if __name__ == "__main__":
    main()
