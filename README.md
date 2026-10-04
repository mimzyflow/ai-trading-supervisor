# AI Trading Supervisor

Laboratoire personnel de trading Kraken spot EUR, en simulation uniquement.
Portefeuille 100 EUR, deux positions de 20 EUR maximum. Aucune stratégie de ce
dépôt n'est validée pour le réel.

Le moteur Freqtrade Oracle est figé à 2026.9 et son digest vérifié. Le superviseur
lit seulement des endpoints GET bornés et la base SQLite en lecture seule.
Rapport local/Jarvis toutes les 5 minutes, archives horaires, expiration après
15 minutes. API/base invalides => données indisponibles, jamais faux zéro.

La simulation utilise des données publiques, sans clé Kraken autorisant les
ordres. Frais nouveaux trades : 0,80 % par côté. Les secrets UI restent dans
`.env` hors Git. La publication GitHub nécessite un jeton dédié limité aux
issues de ce dépôt ; son absence est un état explicite `not_configured`.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_simulation.py
sh scripts/deploy-oracle.sh
```

Le déploiement exporte exclusivement le code committé, teste avant activation,
conserve les données et prépare un rollback. L'accès SSH privé est essayé puis
le SSH direct documenté dans Jarvis, avec vérification stricte de la clé hôte.

Voir `docs/RUNBOOK.md` et `docs/RESEARCH_PROTOCOL.md` pour l'exploitation et les
expériences. Les résultats simulés ne garantissent pas les résultats réels.

## Recherche automatique, actions et ETF

`research_lab` est un moteur séparé de Freqtrade, uniquement recherche/simulation.
Il explore quatre variantes figées, réserve un contrôle futur de 126 séances
et conserve les décisions dans SQLite. Il ne réécrit pas son code ni ses limites.
Un garde surveille la simulation existante toutes les cinq minutes et peut arrêter
uniquement le conteneur confirmé DRY-RUN à 5 % de baisse du portefeuille.

Le simulateur actions/ETF modélise ouverture suivante, coûts, quantités entières,
splits et dividendes non encaissés. Un adaptateur Alpaca **papier uniquement** est
préparé, avec hôte fixe, horaires, ordres limités, plafonds et identifiants de reprise.
Il n'est pas connecté ni activé faute de compte, clés et univers de données validé.

```sh
python3 scripts/simulate_equities.py --data /chemin/equities.bundle.json
python3 -m research_lab.worker --diagnostic-only
```

La fabrique est limitée à trois profils de recherche et deux générations.
Un ×10 de gains réalisés ne suffit pas : validation et observations prospectives
contrôlées sont requises. Aucun argent ni clé courtier n'est transmis à un enfant.
Voir `docs/AUTONOMOUS_RESEARCH.md` pour les critères, limites et branchement papier.

## Simulations actions sans compte

Le laboratoire local collecte un univers exploratoire fixe SOFI/U en données
publiques et publie 72 calculs rétrospectifs, quatre variantes, cash/passif et
trois scénarios de coûts. Il conserve les réponses originales, préinscrit le
plan avant calcul et refuse tout écrasement. Aucun compte ni ordre courtier.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-equity-research.txt
.venv/bin/python scripts/download_equity_diagnostics.py --name equity-diagnostics-NOUVEL-ESSAI
.venv/bin/python scripts/run_equity_experiment.py --data research_results/equity-diagnostics-NOUVEL-ESSAI/equities.bundle.json --output research_results/equity-experiment-NOUVEL-ESSAI
```

Python 3.10 minimum pour le calendrier optionnel. Un nouveau dossier conserve
une nouvelle archive ; il ne transforme pas une période déjà vue en validation
indépendante. Les résultats bruts et détaillés restent hors Git.

Premier essai du 4 octobre : **aucune variante retenue**, source unique et
transactions trop rares. Voir [le protocole](docs/EQUITY_SIMULATIONS.md) et
[les 72 résultats](docs/EQUITY_SIMULATION_RESULTS_2026-10-04.md).
