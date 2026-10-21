# Plan papier actions `market_room_schb_slow_trend_v1` (22/10/2026) — SIMULATION UNIQUEMENT

Le compte papier de 100 € suit uniquement SCHB : au-dessus de sa SMA200 daily à la 1re séance du mois, il est investi en parts entières ; sinon il est en cash.
L'ordre est exécuté à l'ouverture suivante (0,10 % de commission, 0,10 % de glissement, minimum 0). Les alertes 5 % / 10 % sont `notify_only`.
Code : `research_lab/schb_trend_paper.py` (règle `slow_trend.choose`).

## Gel des plans (docs/RESEARCH_RESUME.md)
Le protocole interdit de réécrire un plan figé : son JSON, son résultat, ses fenêtres et ses événements sont conservés.
On ne modifie donc ni `equity_data.SYMBOLS` (univers SOFI/U/PLUG/OPEN/FUBO/NIO/MARA/RIOT du plan de recherche actions), ni le témoin `equity_paper.json`, ni les ombres V3.
On crée un **nouveau plan versionné** dans un nouveau fichier d'état, `research_state/equity_<policy>_market_room_schb_slow_trend_v1.json`.
L'ancien `equity_<policy>.json` n'est plus avancé et n'est jamais modifié ni supprimé.
Le nouveau plan en garde un résumé en lecture seule (`supersedes`). Les anciennes positions ne sont pas reprises : elles sont fictives et hors règle.

## Données
`scripts/collect_equity_paper.py` télécharge aussi SCHB (Yahoo, 2 ans daily, au moins 210 séances closes, divisions avec ratio) dans `research_state/schb.bundle.json`.
Un échec SCHB n'affecte ni l'univers figé ni la crypto.

## État existant
Aucune réinitialisation manuelle : le nouveau fichier est créé au premier cycle avec 100 € au change du jour, puis il prend la décision initiale sur la dernière séance close.
Limites : source Yahoo unique, dividendes ignorés, prix ajustés des divisions (les divisions futures multiplient les parts détenues).
