# Salle des marchés supervisée

TradingAgents est une couche d'analyse consultative séparée des deux moteurs.
Son code et ses dépendances sont épinglés, dans un environnement Python dédié.
Source : https://github.com/TauricResearch/TradingAgents, version 0.6.0,
commit `1394a3f72aa4393e1a98f51b382434c4b4c2d972`, licence Apache-2.0.
Le nombre d'étoiles et les démonstrations du projet ne valident pas une rentabilité.

## Desks et rapports

- Crypto : état Kraken EUR observé, historique cumulé et V2 distingués.
- Actions : témoin et trois V3 brokerless USD, sans somme des comptes fictifs.
- Recherche : résultats historiques et refus V3, jamais assimilés au paper futur.
- Risque : garde déterministe existant, prioritaire sur tout avis IA.
- TradingAgents : analystes marché et actualités, débat haussier/baissier,
  contradicteurs de risque et avis final à examiner. Aucun raccordement courtier.

La salle déterministe est actualisée avec le rapport toutes les cinq minutes.
`user_data/reports/market-room.md` et `latest.json` en sont les sources Oracle.
Les avis détaillés résident dans `tradingagents.json` et `tradingagents.md`.
Les rapports précédents sont archivés avant remplacement. Jarvis reçoit une
copie privée fixe `room-analysis.json`, distincte de la télémétrie générale.
Jarvis : **Plus → Trading IA → Lire le rapport de la salle des marchés**.
Route privée authentifiée : `/api/trading/room-report`, texte non interprété,
sans paramètres de chemin. Commander `trading_status` expose les états et avis
bornés ; les textes des modèles ne deviennent jamais des instructions d'outil.

## Coût et limites

Le connecteur accepte seulement l'accès Gemini déjà présent dans Jarvis et
explicitement marqué gratuit, sans secours payant. La présence de ce marqueur
n'est pas une nouvelle vérification de la facturation du compte fournisseur.
Absence du marqueur/de la clé, refus ou quota atteint : analyse indisponible.
Les variables privées restent dans `.runtime/`, jamais dans Git.

Pilote fixe : **BTC-USD et SOFI**, un seul passage quotidien après clôture,
20:20 UTC. Il ne couvre pas encore chaque actif de l'univers des bots.
Maximum 16 appels par instrument, 240 000 caractères de contexte cumulés,
1 024 tokens de sortie par appel, un tour de débat/risque/outils, zéro retry
SDK et 180 secondes maximum par instrument. La tentative est réservée avant
calcul ; un échec consomme aussi la journée. Les prompts et mémoires internes
sont temporaires, isolés par run ; aucun apprentissage automatique ne change
une stratégie. Les SDK restent confinés au processus dédié.

BTC-USD est une analyse externe en USD, pas la mesure du compte Kraken EUR.
Le portefeuille n'est pas transmis : aucun compte n'est supposé vide et aucune
conversion EUR/USD n'est inventée. Les données Yahoo/news du framework peuvent
inclure la séance en cours lors d'un essai manuel avant clôture. Les dates
d'analyse et la dernière séance clôturée du bot sont distinctes. Ce pilote
n'effectue aucun backtest IA ni calcul de performance de ses avis. Un avis
Buy/Sell n'est pas un ordre et ne devient pas une nouvelle stratégie.

Les extraits de rôle sont bornés à 700 caractères ; les avis doivent être
recoupés avec les sources avant décision humaine. Aucun résultat IA ne remplace
les coûts stressés, fenêtres indépendantes et 126 séances futures requises.
L'historique actions actuel est une fenêtre glissante de deux ans : attendre
ne suffit pas pour atteindre 600 séances. Étendre cet historique et examiner
ses biais reste une tâche distincte ; aucun gel antérieur n'est antidaté.

## Arrêt existant et installation

Le 9 octobre à 14:48:23 UTC, le registre a fixé `paused_risk` pour drawdown,
avec dernière equity vérifiée **94,7907 EUR**, soit environ -5,21 % depuis
100 EUR. Le moteur a ensuite été stoppé ; ces chiffres sont un checkpoint,
pas une observation actuelle. Le registre, la base et les portefeuilles sont
préservés. Un déploiement et son rollback doivent conserver cet arrêt, avec
`up --no-deps supervisor` uniquement. Une base/API indisponible reste masquée.

Le code principal suit `scripts/deploy_oracle.py` et sa validation simulation.
L'installation optionnelle isolée suit `sudo -n python3 scripts/install_market_room.py`.
`--activate` configure le timer et lance la première tentative bornée. Aucune
configuration Freqtrade, clé exchange, ordre, portefeuille ni gel n'est modifié.

Validation source : 185 tests trading réussis ; paquet amont réellement
installé et graphe marché/news construit sans appel IA. Les preuves de
déploiement et de première analyse doivent être consignées après vérification.
